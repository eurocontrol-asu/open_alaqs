import csv
import glob
import os
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from qgis.core import QgsMapLayer, QgsProject, QgsSettings, QgsTextAnnotation
from qgis.gui import QgsFileWidget
from qgis.PyQt import QtCore, QtGui, QtWidgets
from qgis.PyQt.QtWidgets import QSpacerItem
from qgis.PyQt.uic import loadUiType

from open_alaqs.core import alaqs, alaqsutils
from open_alaqs.core.alaqsdblite import (
    ProjectDatabase,
    get_inventory_timestamps,
    get_min_max_timestamps,
)
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.EmissionCalculation import EmissionCalculation, GridConfig
from open_alaqs.core.interfaces.Emissions import PollutantType
from open_alaqs.core.modules.ModuleConfigurationWidget import ModuleConfigurationWidget
from open_alaqs.core.modules.ModuleManager import (
    OutputDispersionModuleRegistry,
    SourceModuleRegistry,
)
from open_alaqs.core.tools.austal_csv_generation import generate_austal_from_csv
from open_alaqs.core.tools.Grid3D import Grid3D
from open_alaqs.core.tools.sql_interface import (
    get_grid_3d_definition,
    has_grid_3d_definition,
)
from open_alaqs.ui.styles import (
    STATUS_STYLE_ERROR,
    STATUS_STYLE_INFO,
    STATUS_STYLE_SUCCESS,
    STATUS_STYLE_WARNING,
)

logger = get_logger(__name__)


class Austal2000RunError(Exception):
    pass


def catch_errors(f):
    """
    Decorator to catch all errors when executing the function.
    This decorator catches errors and writes them to the log.

    :param f: function to execute
    :return:
    """

    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            alaqsutils.print_error(f.__name__, Exception, e)
            raise e

    return wrapper


class OpenAlaqsDispersionAnalysis(QtWidgets.QDialog):
    """
    This class provides a dialog that launches the Dispersion Analysis
    """

    settings_schema = {
        "start_dt_inclusive": {
            "label": "Start (incl.)",
            "widget_type": QtWidgets.QDateTimeEdit,
            "initial_value": datetime(2023, 3, 1, 0, 0, 0),
        },
        "end_dt_inclusive": {
            "label": "End (incl.)",
            "widget_type": QtWidgets.QDateTimeEdit,
            "initial_value": datetime(2023, 3, 1, 23, 0, 0),
        },
        "averaging": {
            "label": "Averaging",
            "widget_type": QtWidgets.QComboBox,
            "initial_value": "annual mean",
            "widget_config": {
                "options": [
                    "hourly",
                    "8-hours mean",
                    "daily mean",
                    "annual mean",
                ],
            },
        },
        "pollutant": {
            "label": "Pollutant",
            "widget_type": QtWidgets.QComboBox,
            "initial_value": None,
            "widget_config": {
                "options": list(
                    p.value
                    for p in (
                        PollutantType.CO2,
                        PollutantType.CO,
                        PollutantType.HC,
                        PollutantType.NOx,
                        PollutantType.SOx,
                        PollutantType.PM10,
                    )
                ),
            },
        },
        "is_uncertainty_enabled": {
            "label": "Enable Uncertainty",
            "widget_type": QtWidgets.QCheckBox,
            "initial_value": False,
        },
    }

    def __init__(self, iface=None):
        """
        Initialises QDialog that displays the about UI for the plugin.
        """
        main_window = iface.mainWindow() if iface is not None else None
        QtWidgets.QDialog.__init__(self, main_window)

        # store the pointer to the QGIS interface
        self._iface = iface

        # Setup the user interface from Designer
        Ui_DialogRunAUSTAL, _ = loadUiType(
            os.path.join(os.path.dirname(__file__), "..", "ui", "ui_run_austal.ui")
        )
        self.ui = Ui_DialogRunAUSTAL()
        self.ui.setupUi(self)

        # Set default values for calculation configuration widgets and make
        # them read-only for the moment — they are populated from the loaded file.

        # TODO: Implement the averaging strategy and enable to change the time
        if hasattr(self.ui, "startDtEdit"):
            self.ui.startDtEdit.setDateTime(QtCore.QDateTime(2023, 3, 1, 0, 0, 0))
            self.ui.startDtEdit.setEnabled(False)
        if hasattr(self.ui, "endDtEdit"):
            self.ui.endDtEdit.setDateTime(QtCore.QDateTime(2023, 3, 1, 23, 0, 0))
            self.ui.endDtEdit.setEnabled(False)
        if hasattr(self.ui, "averagingCombo"):
            idx = self.ui.averagingCombo.findText("annual mean")
            if idx >= 0:
                self.ui.averagingCombo.setCurrentIndex(idx)

        # Set locale for coordinate and resolution spinboxes to use point as decimal separator
        c_locale = QtCore.QLocale(QtCore.QLocale.Language.C)
        self.ui.refLatSpinBox.setLocale(c_locale)
        self.ui.refLonSpinBox.setLocale(c_locale)
        self.ui.xResolutionSpinBox.setLocale(c_locale)
        self.ui.yResolutionSpinBox.setLocale(c_locale)
        self.ui.zResolutionSpinBox.setLocale(c_locale)
        self.ui.refAltSpinBox.setLocale(c_locale)

        # Immediately hide gray feedback/summary boxes that appear in collapsible sections
        # These should only be visible when their parent sections are expanded
        self.ui.currentGridSummaryLabel.setVisible(True)
        self.ui.alaqsGridStatusLabel.setVisible(True)

        # Setup collapsible sections
        self._setup_collapsible_sections()

        # Connect grid checkbox from the result visualisation section toggle to update visualisation status
        self.ui.alaqsGridGroupBox.toggled.connect(
            self._update_visualization_status_label
        )

        # initialize calculation
        self._conc_calculation_ = None
        self._concentration_visualization_widget = ModuleConfigurationWidget(
            settings_schema=self.settings_schema
        )
        self.resetConcentrationCalculationConfiguration()
        self.updateMinMaxGUI()

        # Update the averaging option menu such that only the annual mean is enabled
        self._setup_averaging_options()

        # Initialize current grid configuration - stores in-memory grid values
        # These values are updated whenever spinboxes change and are used for calculations
        # until the user closes the dialog
        self._current_grid_config = None

        # G1: Snapshot of the grid as originally loaded from file and used to detect
        # whether the user has modified the spinboxes after loading.
        self._g1_original_grid_config = None
        self._g1_loaded_file_path = None

        # Separate grid loaded from Grid Management in Result Visualisation.
        # This is independent of the spinboxes and overrides the spinbox grid
        # for visualisation purposes only.
        self._visualization_grid_config = None
        self._visualization_grid_file_path = None

        # Track whether results are available (AUSTAL ran or results directory loaded)
        self._results_loaded = False

        # Track whether AUSTAL was actually run (vs results loaded from directory)
        self._austal_ran = False

        # Track whether AUSTAL input files have been successfully generated
        self._austal_input_files_generated = False

        # Track the directory where input files were generated
        self._generated_austal_work_dir = None

        # Snapshot of grid at the moment AUSTAL ran and never read spinboxes
        # dynamically for the visualisation status.
        self._austal_grid_config = None

        s = QgsSettings()
        last_alaqs_file_path = s.value("OpenALAQS/last_alaqs_file_path", "")
        last_work_directory_path = s.value("OpenALAQS/last_work_directory_path", "")
        last_a2k_executable_path = s.value("open_alaqs/a2k_executable_path", "")
        self.ui.a2k_executable_path.setFilter("AUSTAL Executable (austal.exe austal)")
        self.ui.a2k_executable_path.setDialogTitle("Select AUSTAL Executable File")
        self.ui.a2k_executable_path.setFilePath(last_a2k_executable_path)
        self.ui.a2k_executable_path.fileChanged.connect(
            self.a2k_executable_path_file_changed
        )
        # Set initial status for executable if one was saved
        if last_a2k_executable_path and os.path.isfile(last_a2k_executable_path):
            executable_name = os.path.basename(last_a2k_executable_path)
            status_text = f"Executable Loaded. File: {executable_name}"
            self.ui.executableStatusLabel.setText(status_text)
            self.ui.executableStatusLabel.setStyleSheet(STATUS_STYLE_SUCCESS)
        else:
            status_text = "No Executable Loaded\nPlease select the AUSTAL executable file to proceed."
            self.ui.executableStatusLabel.setText(status_text)
            self.ui.executableStatusLabel.setStyleSheet(STATUS_STYLE_WARNING)
        self.ui.work_directory_path.setStorageMode(QgsFileWidget.GetDirectory)
        self.ui.work_directory_path.setDialogTitle(
            "Select AUSTAL Input Files (.txt, .dmna, etc.) Directory"
        )
        self.ui.work_directory_path.setFilePath(last_work_directory_path)
        self.ui.work_directory_path.fileChanged.connect(
            self._on_work_directory_path_changed
        )
        # Set initial status for work directory if one was saved
        if os.path.isdir(last_work_directory_path):
            dir_name = os.path.basename(last_work_directory_path)
            status_text = f"Input Directory Loaded. Directory: {dir_name}"
            self.ui.existingFilesStatusLabel.setText(status_text)
            self.ui.existingFilesStatusLabel.setStyleSheet(STATUS_STYLE_SUCCESS)
        else:
            status_text = "No Input Directory Loaded. Select directory with AUSTAL input files (.txt, .dmna, etc.)"
            self.ui.existingFilesStatusLabel.setText(status_text)
            self.ui.existingFilesStatusLabel.setStyleSheet(STATUS_STYLE_WARNING)
        self.ui.alaqs_file_path.setFilter("ALAQS (*.alaqs)")
        self.ui.alaqs_file_path.setDialogTitle("Select ALAQS Output File")
        self.ui.alaqs_file_path.setFilePath(last_alaqs_file_path)
        self.ui.alaqs_file_path.fileChanged.connect(self.load_alaqs_source_file)

        if os.path.isfile(last_alaqs_file_path):
            self.load_alaqs_source_file(last_alaqs_file_path)

        self.ui.RunA2K.clicked.connect(self.run_austal)

        # Initialize execution status label
        self.ui.executionStatusLabel.setText("Status: Idle")
        self.ui.executionStatusLabel.setStyleSheet(STATUS_STYLE_WARNING)

        # Setup results work directory widget - auto-load when path changes
        self.ui.resultsWorkDirectoryPath.setStorageMode(QgsFileWidget.GetDirectory)
        self.ui.resultsWorkDirectoryPath.setDialogTitle(
            "Select Work Directory with AUSTAL Results"
        )
        self.ui.resultsWorkDirectoryPath.fileChanged.connect(
            self._on_results_directory_changed
        )

        # Setup grid source file widget - auto-load when path changes
        last_grid_file_path = s.value("OpenALAQS/last_grid_file_path", "")
        self.ui.gridSourceFilePath.setFilter(
            "Grid Files (*.csv *.alaqs);;CSV Files (*.csv);;OpenALAQS Files (*.alaqs);;All Files (*)"
        )
        self.ui.gridSourceFilePath.setDialogTitle("Select Grid Configuration File")
        self.ui.gridSourceFilePath.setFilePath(last_grid_file_path)
        self.ui.gridSourceFilePath.fileChanged.connect(
            self._on_grid_source_file_changed
        )

        # If a grid file was saved, load it immediately
        if last_grid_file_path and os.path.isfile(last_grid_file_path):
            self._on_grid_source_file_changed(last_grid_file_path)

        self.ui.ResultsTable.clicked.connect(
            lambda: self.runOutputModule("ComplianceReportDispersionModule")
        )
        self.ui.VisualiseResults.clicked.connect(
            lambda: self.runOutputModule("QGISVectorLayerDispersionModule")
        )
        self.ui.PlotTimeSeries.clicked.connect(
            lambda: self.runOutputModule("TimeSeriesDispersionModule")
        )

        # Add AUSTAL Help Button
        self.ui.austal_help_button = QtWidgets.QPushButton("AUSTAL Help")
        self.ui.austal_help_button.clicked.connect(self.show_austal_help)

        # Find the layout containing the a2k_executable_path and add button next to it
        layout = self.ui.a2k_executable_path.layout()
        if layout is not None:
            layout.addWidget(self.ui.austal_help_button)

        # Setup external CSV file inputs
        self._setup_external_csv_inputs(s)

        # Initialise generation datetime pickers with a generic default
        _default_dt = QtCore.QDateTime(2000, 1, 1, 0, 0, 0)
        self.ui.alaqs_start_dt_edit.setDateTime(_default_dt)
        self.ui.alaqs_end_dt_edit.setDateTime(_default_dt)
        self.ui.csv_start_dt_edit.setDateTime(_default_dt)
        self.ui.csv_end_dt_edit.setDateTime(_default_dt)

        # If an OpenALAQS output file was restored from settings, populate the datetime range now
        if os.path.isfile(
            last_alaqs_output_file := s.value(
                "OpenALAQS/last_alaqs_output_file_path", ""
            )
        ):
            self._on_alaqs_output_file_changed(last_alaqs_output_file)

        # If emissions CSV was restored, populate the CSV datetime range now
        if os.path.isfile(s.value("OpenALAQS/last_emissions_csv_path", "")):
            self._update_csv_datetime_range()

        # Add the save grid as csv button
        self.ui.saveGridCsvBtn.clicked.connect(self.save_grid_as_csv)

        # Add the update file button - gets file path from widget when clicked
        self.ui.updateFileBtn.clicked.connect(
            lambda: self.update_file(self.ui.gridSourceFilePath.filePath())
        )

        # Connect spinbox value changes to update grid status in real-time
        self.ui.xCellsSpinBox.valueChanged.connect(self._update_grid_status_label)
        self.ui.yCellsSpinBox.valueChanged.connect(self._update_grid_status_label)
        self.ui.zCellsSpinBox.valueChanged.connect(self._update_grid_status_label)
        self.ui.xResolutionSpinBox.valueChanged.connect(self._update_grid_status_label)
        self.ui.yResolutionSpinBox.valueChanged.connect(self._update_grid_status_label)
        self.ui.zResolutionSpinBox.valueChanged.connect(self._update_grid_status_label)
        self.ui.refLatSpinBox.valueChanged.connect(self._update_grid_status_label)
        self.ui.refLonSpinBox.valueChanged.connect(self._update_grid_status_label)
        self.ui.refAltSpinBox.valueChanged.connect(self._update_grid_status_label)

        self.resetModuleConfiguration(
            module_names=[
                "CSVDispersionModule",
                "TableViewDispersionModule",
                "TimeSeriesDispersionModule",
                "QGISVectorLayerDispersionModule",
            ]
        )

    def _setup_collapsible_sections(self):
        """Setup collapsible/expandable sections with proper hide/show behavior."""

        # Helper to recursively set visibility on all layout items including nested layouts
        def set_layout_visibility(layout, visible):
            """Recursively set visibility for all items in a layout."""
            if layout is None:
                return

            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item is None:
                    continue

                # Handle widgets
                if item.widget():
                    item.widget().setVisible(visible)
                # Handle nested layouts
                elif item.layout():
                    set_layout_visibility(item.layout(), visible)
                # Handle spacers
                elif isinstance(item, QSpacerItem):
                    item.changeSize(
                        item.sizeHint().width() if visible else 0,
                        item.sizeHint().height() if visible else 0,
                    )

        # Helper to make a groupbox collapsible by toggling its layout visibility
        def make_collapsible(groupbox):
            """Connect groupbox toggle to show/hide its contents."""
            if not hasattr(groupbox, "isCheckable") or not groupbox.isCheckable():
                return

            # Get the layout
            layout = groupbox.layout()
            if layout is None:
                return

            # Set initial visibility based on checked state
            set_layout_visibility(layout, groupbox.isChecked())

            # Connect toggled signal with layout update
            def on_toggle(checked):
                set_layout_visibility(layout, checked)
                # Force layout recalculation and window resize
                self.ui.scrollArea.widget().layout().activate()
                self.ui.scrollArea.updateGeometry()

            groupbox.toggled.connect(on_toggle)

        # Setup collapsible sections
        make_collapsible(self.ui.executableGroupBox)
        make_collapsible(self.ui.visualisationGroupBox)
        make_collapsible(self.ui.gridManagementGroupBox)
        make_collapsible(self.ui.gridDetailsGroupBox)
        make_collapsible(self.ui.alaqsGridGroupBox)
        make_collapsible(self.ui.loadResultsGroupBox)

        # G1 grid status label (currentGridSummaryLabel) should always be visible
        # Refresh status message when grid details section is expanded
        self.ui.gridDetailsGroupBox.toggled.connect(self._update_grid_status_label)

        # G2 grid status label (alaqsGridStatusLabel) hides when section is collapsed
        def toggle_alaqs_grid_visibility(checked):
            self.ui.alaqsGridStatusLabel.setVisible(checked)

        self.ui.alaqsGridGroupBox.toggled.connect(toggle_alaqs_grid_visibility)
        self.ui.alaqsGridStatusLabel.setVisible(self.ui.alaqsGridGroupBox.isChecked())

        # Force hide all feedback labels when their parent sections are collapsed
        # These are specifically the gray boxes that appear as status/feedback
        self.ui.alaqsGridStatusLabel.setVisible(self.ui.alaqsGridGroupBox.isChecked())

        # CSV feedback visibility depends on CSV mode being selected
        self.ui.external_files_feedback.setVisible(self._input_mode() == "csv")

        # Connect CSV mode toggle for feedback visibility
        def toggle_csv_feedback_visibility(*_args):
            self.ui.external_files_feedback.setVisible(self._input_mode() == "csv")

        self.ui.useExistingFilesRadio.toggled.connect(toggle_csv_feedback_visibility)
        self.ui.generateFromAlaqsRadio.toggled.connect(toggle_csv_feedback_visibility)
        self.ui.generateFromCsvRadio.toggled.connect(toggle_csv_feedback_visibility)

        # Connect OpenALAQS feedback visibility
        def toggle_alaqs_feedback_visibility(checked):
            self.ui.alaqsGridStatusLabel.setVisible(checked)

        self.ui.alaqsGridGroupBox.toggled.connect(toggle_alaqs_feedback_visibility)

        # For calculation config, search for any feedback-like labels and hide them when collapsed
        def hide_calc_feedback(checked):
            # Hide any labels with feedback/status in the calculation config
            calc_layout = self.ui.calculationConfigGroupBox.layout()
            if calc_layout:
                for i in range(calc_layout.count()):
                    item = calc_layout.itemAt(i)
                    if (
                        item
                        and item.widget()
                        and "feedback" in item.widget().objectName().lower()
                    ):
                        item.widget().setVisible(checked)

        self.ui.calculationConfigGroupBox.toggled.connect(hide_calc_feedback)
        hide_calc_feedback(self.ui.calculationConfigGroupBox.isChecked())

        # Connect configuration toggles to update button state
        self.ui.loadResultsGroupBox.toggled.connect(self._update_result_buttons_state)
        self.ui.gridManagementGroupBox.toggled.connect(
            self._update_result_buttons_state
        )
        self.ui.alaqsGridGroupBox.toggled.connect(self._update_result_buttons_state)
        self.ui.resultsWorkDirectoryPath.fileChanged.connect(
            self._update_result_buttons_state
        )
        self.ui.alaqs_file_path.fileChanged.connect(self._update_result_buttons_state)
        self.ui.gridSourceFilePath.fileChanged.connect(
            self._update_result_buttons_state
        )
        # Connect spinbox changes for grid management
        self.ui.xCellsSpinBox.valueChanged.connect(self._update_result_buttons_state)
        self.ui.yCellsSpinBox.valueChanged.connect(self._update_result_buttons_state)

    def _update_result_buttons_state(self):
        """Update the enabled state of result visualisation buttons.

        Logic:
        - ResultsTable & PlotTimeSeries: Enable if (AUSTAL completed) OR (output files loaded)
          These don't require grid as they display tabular/time series data
        - VisualiseResults (Vector Layer): Enable if (AUSTAL completed with grid) OR (output files loaded AND grid provided)
          Vector visualisation requires grid for spatial information
        """
        # Check if AUSTAL ran successfully
        austal_completed = "Completed" in self.ui.executionStatusLabel.text()

        # Check if output files are loaded (results work directory selected)
        has_output_files = bool(
            self.ui.loadResultsGroupBox.isChecked()
            and self.ui.resultsWorkDirectoryPath.filePath()
            and os.path.isdir(self.ui.resultsWorkDirectoryPath.filePath())
        )

        # Check if grid is configured
        # Grid can come from: Grid Management spinboxes OR OpenALAQS file OR Grid Source File
        has_grid_from_management = bool(
            int(self.ui.xCellsSpinBox.value()) > 0
            and int(self.ui.yCellsSpinBox.value()) > 0
        )

        has_grid_from_alaqs = bool(
            self.ui.alaqsGridGroupBox.isChecked()
            and self.ui.alaqs_file_path.filePath()
            and os.path.isfile(self.ui.alaqs_file_path.filePath())
        )

        has_grid_from_file = bool(
            self.ui.gridSourceFilePath.filePath()
            and os.path.isfile(self.ui.gridSourceFilePath.filePath())
        )

        has_grid_config = bool(
            has_grid_from_management or has_grid_from_alaqs or has_grid_from_file
        )

        # Logic for table and time series - no grid required
        bool(austal_completed or has_output_files)

        # Logic for vector visualisation - requires grid
        can_visualize_vector = bool(
            (austal_completed and has_grid_config)
            or (has_output_files and has_grid_config)
        )
        self.ui.VisualiseResults.setEnabled(can_visualize_vector)
        if not can_visualize_vector:
            self.ui.VisualiseResults.setToolTip(
                "Disabled: Plot Vector Layer needs both an AUSTAL grid output "
                "(.dmna files) and a configured grid (cells > 0, or grid from "
                "an OpenALAQS file). Run AUSTAL or load existing output files, "
                "and ensure the grid is set."
            )
        else:
            self.ui.VisualiseResults.setToolTip(
                "Click to plot the AUSTAL grid output as a QGIS vector layer."
            )

        # PlotTimeSeries + ResultsTable (Receptor Compliance Report) both
        # need <substance>-tmpa.dmna files in the work directory. TalMon
        # produces those only when AUSTAL runs with (a) receptors defined
        # (xp/yp/hp lines in austal.txt) AND (b) NOTALUFT enabled. If
        # neither was true, both modules have nothing to read.
        work_dir_for_tmpa = None
        try:
            wd = self._get_austal_work_directory()
            if wd is not None:
                work_dir_for_tmpa = str(wd)
        except Exception:
            work_dir_for_tmpa = None
        tmpa_files = []
        if work_dir_for_tmpa and os.path.isdir(work_dir_for_tmpa):
            tmpa_files = glob.glob(os.path.join(work_dir_for_tmpa, "*-tmpa.dmna"))
        has_tmpa = bool(tmpa_files)

        self.ui.PlotTimeSeries.setEnabled(has_tmpa)
        self.ui.ResultsTable.setEnabled(has_tmpa)

        # User feedback on the buttons themselves so the disabled state is
        # self-explanatory.
        if has_tmpa:
            substances = sorted({os.path.basename(p).split("-")[0] for p in tmpa_files})
            tt_enabled = "Receptor results available for: %s." % ", ".join(substances)
            self.ui.PlotTimeSeries.setToolTip(
                tt_enabled + " Click to plot time series at receptors."
            )
            self.ui.ResultsTable.setToolTip(
                tt_enabled + " Click to compute per-receptor TA Luft compliance."
            )
        else:
            tt_disabled = (
                "Disabled: no <substance>-tmpa.dmna files in the AUSTAL "
                "work directory.\n\nTo enable:\n"
                "  1. Add receptor points (CSV picker in OpenALAQS "
                "Generate tab, or shapes_receptor_points in .alaqs)\n"
                "  2. Tick 'Per-hour series (NOTALUFT)' in Output Mode\n"
                "  3. Re-generate AUSTAL inputs and re-run AUSTAL"
            )
            self.ui.PlotTimeSeries.setToolTip(tt_disabled)
            self.ui.ResultsTable.setToolTip(tt_disabled)

        # Status label below the result buttons (if the UI exposes one).
        self._update_receptor_results_status(has_tmpa, tmpa_files)

    def _update_receptor_results_status(self, has_tmpa, tmpa_files):
        """Update the small status label below the result buttons.

        Tells the user, in plain language, whether receptor-based results
        (Plot Time Series, Compliance Report) are available, and what to
        do if not. Silently no-ops if the UI doesn't expose the label
        (older .ui versions without the receptorResultsStatusLabel).
        """
        label = getattr(self.ui, "receptorResultsStatusLabel", None)
        if label is None:
            return
        if has_tmpa:
            substances = sorted({os.path.basename(p).split("-")[0] for p in tmpa_files})
            text = (
                "Receptor results available for: %s. "
                "Plot Time Series and Compliance Report are enabled."
                % ", ".join(substances)
            )
            label.setStyleSheet("color: #1a6e1a; font-size: 10pt; padding: 2px 6px;")
        else:
            text = (
                "No receptor results in this work directory. "
                "To enable Plot Time Series and Compliance Report: add "
                "receptors (CSV in OpenALAQS Generate tab, or "
                "shapes_receptor_points in .alaqs), tick "
                "'Per-hour series (NOTALUFT)', then re-generate AUSTAL "
                "inputs and re-run AUSTAL."
            )
            label.setStyleSheet("color: #8a4a00; font-size: 10pt; padding: 2px 6px;")
        label.setText(text)

    def updateMinMaxGUI(self, db_path_=""):
        time_start_calc_, time_end_calc_ = get_min_max_timestamps(db_path_)
        self.resetConcentrationCalculationConfiguration(
            config={
                "start_dt_inclusive": time_start_calc_,
                "end_dt_inclusive": time_end_calc_,
            }
        )
        # Populate the grayed-out start/end datetime entries with the real timestamps directly from the database.
        if hasattr(self.ui, "startDtEdit"):
            self.ui.startDtEdit.setDateTime(
                QtCore.QDateTime(
                    time_start_calc_.year,
                    time_start_calc_.month,
                    time_start_calc_.day,
                    time_start_calc_.hour,
                    time_start_calc_.minute,
                    time_start_calc_.second,
                )
            )
        if hasattr(self.ui, "endDtEdit"):
            self.ui.endDtEdit.setDateTime(
                QtCore.QDateTime(
                    time_end_calc_.year,
                    time_end_calc_.month,
                    time_end_calc_.day,
                    time_end_calc_.hour,
                    time_end_calc_.minute,
                    time_end_calc_.second,
                )
            )

    def getTimeSeries(self, db_path="") -> list[datetime]:
        time_series_ = get_inventory_timestamps(db_path)
        return time_series_

    def resetModuleConfiguration(self, module_names):
        # Holder for future development
        pass

    def a2k_executable_path_file_changed(self, path):
        """
        Save the selected austal executable file path to restore on dialog
        opening
        """
        if path and os.path.isfile(path):
            settings = QgsSettings()
            settings.setValue("open_alaqs/a2k_executable_path", path)
            # Update status label with success styling and explicit information
            executable_name = os.path.basename(path)
            status_text = f"Executable Loaded. File: {executable_name}"
            self.ui.executableStatusLabel.setText(status_text)
            self.ui.executableStatusLabel.setStyleSheet(STATUS_STYLE_SUCCESS)
            logger.info(f"AUSTAL executable selected: {path}")
        else:
            status_text = "No Executable Loaded\nPlease select the AUSTAL executable file to proceed."
            self.ui.executableStatusLabel.setText(status_text)
            self.ui.executableStatusLabel.setStyleSheet(STATUS_STYLE_WARNING)
            if path:  # Only clear settings if a path was explicitly cleared
                settings = QgsSettings()
                settings.setValue("open_alaqs/a2k_executable_path", "")

    def set_feedback(self, feedback: str, is_success: bool) -> None:
        # Update alaqsGridStatusLabel with feedback styling
        if is_success:
            self.ui.alaqsGridStatusLabel.setText(feedback)
            self.ui.alaqsGridStatusLabel.setStyleSheet(STATUS_STYLE_SUCCESS)
        else:
            self.ui.alaqsGridStatusLabel.setText(feedback)
            self.ui.alaqsGridStatusLabel.setStyleSheet(STATUS_STYLE_ERROR)

        # Update button state based on feedback
        self._update_result_buttons_state()

    def load_alaqs_source_file(self, filename):
        """
        Open a file browse window for the user to be able to locate and load an
         OpenALAQS output file
        """
        path = Path(filename)
        if not filename or not path.is_file() or path.suffix != ".alaqs":
            self.set_feedback("Please select an existing *_out.alaqs file", False)
            self.ui.alaqsGridStatusLabel.setText("No Grid selected")
            self.ui.alaqsGridStatusLabel.setStyleSheet(STATUS_STYLE_WARNING)

            # Clear G2 visualization grid when file is deselected
            self._visualization_grid_config = None
            self._visualization_grid_file_path = None
            self._update_visualization_status_label()
            return

        # Update status to loading state (blue)
        self.ui.alaqsGridStatusLabel.setText(f"Status: Loading {path.name}...")
        self.ui.alaqsGridStatusLabel.setStyleSheet(STATUS_STYLE_INFO)
        QtWidgets.QApplication.processEvents()  # Update UI immediately

        try:
            self.updateMinMaxGUI(filename)

            project_database = ProjectDatabase()
            _original_db_path = getattr(project_database, "path", None)
            project_database.path = filename

            study_data = alaqs.load_study_setup()

            # Read actual grid definition from the database
            conn = sqlite3.connect(filename)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT x_cells, y_cells, z_cells, "
                "x_resolution, y_resolution, z_resolution, "
                "reference_latitude, reference_longitude "
                'FROM "grid_3d_definition"'
            )
            grid_row = cursor.fetchone()
            conn.close()

            if grid_row is not None:
                grid_configuration: GridConfig = {
                    "x_cells": int(grid_row["x_cells"]),
                    "y_cells": int(grid_row["y_cells"]),
                    "z_cells": int(grid_row["z_cells"]),
                    "x_resolution": float(grid_row["x_resolution"]),
                    "y_resolution": float(grid_row["y_resolution"]),
                    "z_resolution": float(grid_row["z_resolution"]),
                    "reference_latitude": float(grid_row["reference_latitude"]),
                    "reference_longitude": float(grid_row["reference_longitude"]),
                    "reference_altitude": study_data.get("airport_elevation", 0.0),
                }
            else:
                # Fallback if grid_3d_definition table is missing/empty
                grid_configuration: GridConfig = {
                    "x_cells": 100,
                    "y_cells": 100,
                    "z_cells": 1,
                    "x_resolution": 250,
                    "y_resolution": 250,
                    "z_resolution": 300,
                    "reference_latitude": study_data.get("airport_latitude", 0.0),
                    "reference_longitude": study_data.get("airport_longitude", 0.0),
                    "reference_altitude": study_data.get("airport_elevation", 0.0),
                }

            # Only proceed with full loading if concentration visualisation widget is initialized
            if self._concentration_visualization_widget is not None:
                # get values from GUI settings
                em_config = self._concentration_visualization_widget.get_values()

                start_dt = datetime.fromisoformat(em_config["start_dt_inclusive"])
                end_dt = datetime.fromisoformat(em_config["end_dt_inclusive"])

                time_series = self.getTimeSeries(filename)

                if len(time_series) < 2:
                    raise ValueError(
                        "OpenALAQS file contains fewer than 2 time steps; "
                        "cannot determine time interval."
                    )

                time_interval = time_series[1] - time_series[0]

                self._conc_calculation_ = EmissionCalculation(
                    db_path=filename,
                    grid_config=grid_configuration,
                    start_dt=start_dt,
                    end_dt=end_dt,
                    time_interval=time_interval,
                )

            # Restore original database path
            if _original_db_path is not None:
                project_database.path = _original_db_path

            s = QgsSettings()
            s.setValue("OpenALAQS/last_alaqs_file_path", filename)

            self.set_feedback("Valid OpenALAQS file selected", True)
            # Update status label with loaded filename and grid parameters - green success
            grid_params = (
                f"Grid: {grid_configuration['x_cells']}×{grid_configuration['y_cells']}×{grid_configuration['z_cells']} cells | "
                f"Res: {grid_configuration['x_resolution']:.0f}×{grid_configuration['y_resolution']:.0f}×{grid_configuration['z_resolution']:.0f}m | "
                f"Ref: ({grid_configuration['reference_latitude']:.4f}°, {grid_configuration['reference_longitude']:.4f}°, {grid_configuration['reference_altitude']:.0f}m)"
            )
            status_text = f"Loaded: {path.name}\n{grid_params}"
            self.ui.alaqsGridStatusLabel.setText(status_text)
            self.ui.alaqsGridStatusLabel.setStyleSheet(STATUS_STYLE_SUCCESS)

            # Store grid into G2 visualization config and update the visualization status label
            self._visualization_grid_config = grid_configuration.copy()
            self._visualization_grid_file_path = filename
            self._update_visualization_status_label()

        except sqlite3.OperationalError as err:
            self.set_feedback(f"Could not open database file: {err}.", False)
            self.ui.alaqsGridStatusLabel.setText("Status: Error loading file")
            self.ui.alaqsGridStatusLabel.setStyleSheet(STATUS_STYLE_ERROR)
        except Exception as err:
            self.set_feedback(f"Error loading file: {err}", False)
            self.ui.alaqsGridStatusLabel.setText("Status: Error loading file")
            self.ui.alaqsGridStatusLabel.setStyleSheet(STATUS_STYLE_ERROR)

    def _on_work_directory_path_changed(self, dirname: str) -> None:
        s = QgsSettings()

        if os.path.isdir(dirname):
            s.setValue("OpenALAQS/last_work_directory_path", dirname)
            # Update status label with success styling and explicit information
            dir_name = os.path.basename(dirname)
            status_text = f"Input Directory Loaded\nDirectory: {dir_name}"
            self.ui.existingFilesStatusLabel.setText(status_text)
            self.ui.existingFilesStatusLabel.setStyleSheet(STATUS_STYLE_SUCCESS)
            logger.info(f"Work directory selected: {dirname}")
        else:
            status_text = "No Input Directory Loaded\nSelect directory with AUSTAL input files (.txt, .dmna, etc.)"
            self.ui.existingFilesStatusLabel.setText(status_text)
            self.ui.existingFilesStatusLabel.setStyleSheet(STATUS_STYLE_WARNING)
            if dirname:  # Only clear settings if a path was explicitly cleared
                s.setValue("OpenALAQS/last_work_directory_path", "")

        # Refresh Run button state. _on_input_mode_changed only fires on
        # radio-button toggles, so without this hook a directory change
        # while already in "Use Existing" mode would leave the button in
        # its previous (possibly stale) enabled/disabled state. The user
        # would then have to toggle radios off and back to refresh.
        if self._input_mode() == "existing":
            self.ui.RunA2K.setEnabled(bool(dirname and os.path.isdir(dirname)))

    def _on_results_directory_changed(self, results_dir: str) -> None:
        """Auto-load AUSTAL results when a valid work directory is selected."""
        if not results_dir or not os.path.isdir(results_dir):
            # Update status label when directory is deselected
            status_text = "No Results Directory Loaded. Select a directory with AUSTAL output files"
            self.ui.resultsStatusLabel.setText(status_text)
            self.ui.resultsStatusLabel.setStyleSheet(STATUS_STYLE_WARNING)
            self._results_loaded = False
            self._austal_ran = False
            self._update_visualization_status_label()
            self._update_result_buttons_state()
            return

        # Set the results directory as the work directory for visualisation
        self.ui.work_directory_path.setFilePath(results_dir)
        s = QgsSettings()
        s.setValue("OpenALAQS/last_work_directory_path", results_dir)

        # Update results status label with success styling and explicit information
        dir_name = os.path.basename(results_dir)
        status_text = f"Results Directory Loaded. Directory: {dir_name}"
        self.ui.resultsStatusLabel.setText(status_text)
        self.ui.resultsStatusLabel.setStyleSheet(STATUS_STYLE_SUCCESS)

        # Mark results as loaded and update visualisation status with grid details
        self._results_loaded = True
        self._austal_ran = False  # Results loaded from directory, not from AUSTAL run
        # Set header first so _update_visualization_status_label can preserve it
        self.ui.visualisationStatusLabel.setText(
            f"Results loaded from {os.path.basename(results_dir)}"
        )
        self._update_visualization_status_label()

        # Auto-detect available pollutants and averaging options from result files
        try:
            self._detect_and_update_pollutants_and_averaging(results_dir)
        except Exception as _e:
            logger.warning(
                "Could not auto-detect pollutants/averaging from results directory: %s",
                _e,
            )

        # Update button state - will check if grid is also available
        self._update_result_buttons_state()

        logger.info(f"Results loaded from: {results_dir}")

    def _update_visualization_status_label(self) -> None:
        """Update the visualization status label.

        Priority for grid display (highest to lowest):
        1. G2 grid loaded from Result Visualisation section (alaqsGridGroupBox)
        2. If AUSTAL ran from OpenALAQS generation -> show G1 from that OpenALAQS file
        3. If AUSTAL ran from CSV generation -> show G1 from spinboxes
        4. If AUSTAL ran from existing files -> show default grid
        5. If results loaded from directory -> show default grid with warning
        6. No results -> show appropriate message
        """
        try:
            has_g2 = bool(
                self._visualization_grid_config
                and self._visualization_grid_file_path
                and self.ui.alaqsGridGroupBox.isChecked()
            )

            # Helper to format grid config
            def _fmt(gc: dict) -> str:
                return (
                    f"Grid: {gc['x_cells']}×{gc['y_cells']}×{gc['z_cells']} cells | "
                    f"Resolution: {gc['x_resolution']:.0f}×{gc['y_resolution']:.0f}×"
                    f"{gc['z_resolution']:.0f}m | "
                    f"Reference: ({gc['reference_latitude']:.4f}°, "
                    f"{gc['reference_longitude']:.4f}°, "
                    f"{gc['reference_altitude']:.0f}m)"
                )

            # ---- No results loaded ----
            if not self._results_loaded:
                if has_g2:
                    text = f"Please run AUSTAL or load results.\n\n{_fmt(self._visualization_grid_config)}"
                else:
                    text = "Please run AUSTAL or load results."

                self.ui.visualisationStatusLabel.setText(text)
                self.ui.visualisationStatusLabel.setStyleSheet(STATUS_STYLE_WARNING)

            # ---- Results are available ----
            else:
                # Priority 1: G2 grid from Result Visualisation section
                if has_g2:
                    text = f"Using Grid from Result Visualisation Section\n{_fmt(self._visualization_grid_config)}"
                    bg_color = STATUS_STYLE_SUCCESS

                # Priority 2-4: AUSTAL ran - determine which grid was used
                elif self._austal_ran:
                    # Priority 2: AUSTAL ran from OpenALAQS generation (Option B)
                    if self._input_mode() == "alaqs" and self._austal_grid_config:
                        alaqs_file = self.ui.alaqs_output_file_path.filePath()
                        text = f"Using Grid from OpenALAQS file: {os.path.basename(alaqs_file)}\n{_fmt(self._austal_grid_config)}"
                        bg_color = STATUS_STYLE_SUCCESS

                    # Priority 3: AUSTAL ran from CSV generation (Option C)
                    elif self._input_mode() == "csv" and self._austal_grid_config:
                        text = f"Using Grid from CSV Generation\n{_fmt(self._austal_grid_config)}"
                        bg_color = STATUS_STYLE_SUCCESS

                    # Priority 4: AUSTAL ran from existing files (Option A) - default grid
                    elif self._input_mode() == "existing":
                        if self._austal_grid_config:
                            text = f"Using Default Grid\n{_fmt(self._austal_grid_config)}\n\nRecommendation: Load a Grid from Result Visualisation section for accurate visualisation."
                        else:
                            text = "Using Default Grid\n\nRecommendation: Load a Grid from Result Visualisation section for accurate visualisation."
                        bg_color = STATUS_STYLE_WARNING

                    else:
                        # Fallback
                        if self._austal_grid_config:
                            text = f"Using Default Grid\n{_fmt(self._austal_grid_config)}\n\nRecommendation: Load a Grid from Result Visualisation section."
                        else:
                            text = "Using Default Grid\n\nRecommendation: Load a Grid from Result Visualisation section."
                        bg_color = STATUS_STYLE_WARNING

                # Priority 5: Results loaded from directory (no AUSTAL run)
                else:
                    gc = self.get_current_grid_config()
                    if gc and any(gc.get(k, 0) > 0 for k in ["x_cells", "y_cells"]):
                        text = f"Using Default Grid\n{_fmt(gc)}\n\nRecommendation: Load a Grid from Result Visualisation section for accurate visualisation."
                    else:
                        text = "No Grid loaded. Please load a grid from Result Visualisation section for accurate visualisation."
                    bg_color = STATUS_STYLE_WARNING

                self.ui.visualisationStatusLabel.setText(text)
                self.ui.visualisationStatusLabel.setStyleSheet(bg_color)

            self.ui.visualisationStatusLabel.repaint()

        except Exception as e:
            logger.error(
                "Failed to update visualisation status label: %s", e, exc_info=True
            )
            self.ui.visualisationStatusLabel.setText(
                "Error updating visualization status"
            )
            self.ui.visualisationStatusLabel.repaint()

    def _update_grid_status_label(self) -> None:
        """Update the G1 grid status label (currentGridSummaryLabel).

        Colours:
        - Yellow:  No grid values set (all zero) or no file loaded.
        - Green:   Grid loaded from file and spinboxes still match.
        - Blue:    Grid was loaded from a file but spinbox values have been
                   modified → warn user to save / update the file.
        """
        x_cells = int(self.ui.xCellsSpinBox.value())
        y_cells = int(self.ui.yCellsSpinBox.value())
        z_cells = int(self.ui.zCellsSpinBox.value())
        x_res = float(self.ui.xResolutionSpinBox.value())
        y_res = float(self.ui.yResolutionSpinBox.value())
        z_res = float(self.ui.zResolutionSpinBox.value())
        ref_lat = float(self.ui.refLatSpinBox.value())
        ref_lon = float(self.ui.refLonSpinBox.value())
        ref_alt = float(self.ui.refAltSpinBox.value())

        # Update the in-memory grid configuration
        self._current_grid_config = {
            "x_cells": x_cells,
            "y_cells": y_cells,
            "z_cells": z_cells,
            "x_resolution": x_res,
            "y_resolution": y_res,
            "z_resolution": z_res,
            "reference_latitude": ref_lat,
            "reference_longitude": ref_lon,
            "reference_altitude": ref_alt,
        }

        params_text = (
            f"Grid: {x_cells}×{y_cells}×{z_cells} cells | "
            f"Res: {x_res:.0f}×{y_res:.0f}×{z_res:.0f}m | "
            f"Ref: ({ref_lat:.4f}°, {ref_lon:.4f}°, {ref_alt:.0f}m)"
        )

        if self._g1_original_grid_config is not None:
            # A file was loaded – check if spinboxes still match
            modified = any(
                self._current_grid_config[k] != self._g1_original_grid_config.get(k)
                for k in self._current_grid_config
            )
            if modified:
                # Blue – modified since load
                fname = (
                    os.path.basename(self._g1_loaded_file_path)
                    if self._g1_loaded_file_path
                    else "file"
                )
                status_text = (
                    f"Grid modified since loading from {fname}.\n"
                    f"{params_text}\n"
                    f"Save the grid or update the file to keep your changes."
                )
                style = STATUS_STYLE_INFO
            else:
                # Green – loaded and unmodified
                fname = (
                    os.path.basename(self._g1_loaded_file_path)
                    if self._g1_loaded_file_path
                    else ""
                )
                status_text = f"Grid loaded from {fname}\n{params_text}"
                style = STATUS_STYLE_SUCCESS
        else:
            # No file loaded – show default grid status (yellow)
            status_text = f"Default Grid Loaded\n{params_text}"
            style = STATUS_STYLE_WARNING

        self.ui.currentGridSummaryLabel.setText(status_text)
        self.ui.currentGridSummaryLabel.setStyleSheet(style)

    def get_current_grid_config(self) -> dict:
        """
        Get the current grid configuration from spinboxes.

        This includes any unsaved modifications and is used for calculations.
        Returns the configuration even if it hasn't been saved to a file.

        Returns:
            dict: Grid configuration with keys: x_cells, y_cells, z_cells, x_resolution,
                  y_resolution, z_resolution, reference_latitude, reference_longitude,
                  reference_altitude
        """
        if self._current_grid_config is None:
            # Initialize if not yet set
            self._update_grid_status_label()
        return self._current_grid_config

    def _on_grid_source_file_changed(self, grid_file: str) -> None:
        """Handle G1 (Grid Configuration from 'Generate AUSTAL Input Files from CSV') file selection.

        This is the gridSourceFilePath widget inside gridManagementGroupBox (CSV generation).
        It loads a grid file and populates the spinboxes + currentGridSummaryLabel.

        MUST NEVER touch _visualization_grid_config, _visualization_grid_file_path,
        visualisationStatusLabel, or _update_visualization_status_label().
        Those belong to G2 (alaqsGridGroupBox / alaqs_file_path in Result Visualisation).
        """
        logger.info("[G1] _on_grid_source_file_changed called with: %s", grid_file)

        if not grid_file or not os.path.isfile(grid_file):
            logger.info("[G1] File deselected or invalid")
            s = QgsSettings()
            s.setValue("OpenALAQS/last_grid_file_path", "")
            self._g1_original_grid_config = None
            self._g1_loaded_file_path = None
            self.ui.currentGridSummaryLabel.setText("No Grid selected")
            self.ui.currentGridSummaryLabel.setStyleSheet(STATUS_STYLE_WARNING)
            return

        # Store the selected grid file path for next session
        s = QgsSettings()
        s.setValue("OpenALAQS/last_grid_file_path", grid_file)

        try:
            grid_config = None

            # Try to parse as OA file (.alaqs)
            if grid_file.endswith(".alaqs"):
                try:
                    conn = sqlite3.connect(grid_file)
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT x_cells, y_cells, z_cells, "
                        "x_resolution, y_resolution, z_resolution, "
                        "reference_latitude, reference_longitude "
                        'FROM "grid_3d_definition"'
                    )
                    grid_row = cursor.fetchone()
                    cursor.execute('SELECT airport_elevation FROM "user_study_setup"')
                    alt_row = cursor.fetchone()
                    conn.close()

                    if grid_row is None:
                        raise ValueError("No grid_3d_definition found in database")

                    grid_config = {
                        "x_cells": int(grid_row["x_cells"]),
                        "y_cells": int(grid_row["y_cells"]),
                        "z_cells": int(grid_row["z_cells"]),
                        "x_resolution": float(grid_row["x_resolution"]),
                        "y_resolution": float(grid_row["y_resolution"]),
                        "z_resolution": float(grid_row["z_resolution"]),
                        "reference_latitude": float(grid_row["reference_latitude"]),
                        "reference_longitude": float(grid_row["reference_longitude"]),
                        "reference_altitude": (
                            float(alt_row["airport_elevation"]) if alt_row else 0.0
                        ),
                    }
                except Exception as e:
                    logger.warning(f"Could not extract grid from ALAQS file: {e}")
                    grid_config = None

            # Try to parse as CSV file
            elif grid_file.endswith(".csv"):
                try:
                    import csv

                    with open(grid_file, "r") as grid_fh:
                        reader = csv.DictReader(grid_fh)
                        for row in reader:
                            grid_config = {
                                "x_cells": int(row.get("x_cells", 50)),
                                "y_cells": int(row.get("y_cells", 50)),
                                "z_cells": int(row.get("z_cells", 1)),
                                "x_resolution": float(row.get("x_resolution", 100)),
                                "y_resolution": float(row.get("y_resolution", 100)),
                                "z_resolution": float(row.get("z_resolution", 50)),
                                "reference_latitude": float(
                                    row.get("reference_latitude", 0.0)
                                ),
                                "reference_longitude": float(
                                    row.get("reference_longitude", 0.0)
                                ),
                                "reference_altitude": float(
                                    row.get("reference_altitude", 0.0)
                                ),
                            }
                            break  # Use first row
                except Exception as e:
                    logger.warning(f"Could not extract grid from CSV file: {e}")
                    grid_config = None

            # If we successfully loaded grid config, populate the spin boxes
            if grid_config:

                # Snapshot the original loaded values for modification detection
                self._g1_original_grid_config = grid_config.copy()
                self._g1_loaded_file_path = grid_file
                # Populate spinboxes with loaded values
                self.ui.xCellsSpinBox.setValue(grid_config["x_cells"])
                self.ui.yCellsSpinBox.setValue(grid_config["y_cells"])
                self.ui.zCellsSpinBox.setValue(grid_config["z_cells"])
                self.ui.xResolutionSpinBox.setValue(grid_config["x_resolution"])
                self.ui.yResolutionSpinBox.setValue(grid_config["y_resolution"])
                self.ui.zResolutionSpinBox.setValue(grid_config["z_resolution"])
                self.ui.refLatSpinBox.setValue(grid_config["reference_latitude"])
                self.ui.refLonSpinBox.setValue(grid_config["reference_longitude"])
                self.ui.refAltSpinBox.setValue(grid_config["reference_altitude"])
                # valueChanged only fires when the value changes; call explicitly so
                # the status label always updates even when loaded values match defaults.
                self._update_grid_status_label()
            else:

                self.ui.currentGridSummaryLabel.setText(
                    f"Error: Could not parse {os.path.basename(grid_file)}"
                )
                self.ui.currentGridSummaryLabel.setStyleSheet(STATUS_STYLE_ERROR)

        except Exception as e:
            logger.error("Failed to load grid file: %s", e, exc_info=True)

    def _setup_external_csv_inputs(self, s: QgsSettings) -> None:
        """Setup the external CSV file input widgets and connections.

        The UI has two modes:
        - Use existing AUSTAL input files from a work directory
        - Generate input files from CSV (emissions + meteorology)
        """
        # Configure output directory widget for CSV generation
        self.ui.output_directory_path.setStorageMode(QgsFileWidget.GetDirectory)
        self.ui.output_directory_path.setDialogTitle(
            "Select Output Directory for Generated Files"
        )
        last_output_dir = s.value("OpenALAQS/last_csv_output_directory_path", "")
        self.ui.output_directory_path.setFilePath(last_output_dir)
        self.ui.output_directory_path.fileChanged.connect(
            self._on_output_directory_changed
        )

        # Configure emissions CSV file widget
        self.ui.emissions_csv_path.setFilter("CSV Files (*.csv)")
        self.ui.emissions_csv_path.setDialogTitle("Select Emissions CSV File")
        last_emissions_csv = s.value("OpenALAQS/last_emissions_csv_path", "")
        self.ui.emissions_csv_path.setFilePath(last_emissions_csv)
        self.ui.emissions_csv_path.fileChanged.connect(self._on_emissions_csv_changed)

        # Configure meteorology CSV file widget
        self.ui.meteo_csv_path.setFilter("CSV Files (*.csv)")
        self.ui.meteo_csv_path.setDialogTitle("Select Meteorology CSV File")
        last_meteo_csv = s.value("OpenALAQS/last_meteo_csv_path", "")
        self.ui.meteo_csv_path.setFilePath(last_meteo_csv)
        self.ui.meteo_csv_path.fileChanged.connect(self._on_meteo_csv_changed)

        # Configure ALAQS output file widget for direct ALAQS generation
        self.ui.alaqs_output_file_path.setFilter("OpenALAQS Files (*.alaqs)")
        self.ui.alaqs_output_file_path.setDialogTitle("Select OpenALAQS Output File")
        last_alaqs_output_file = s.value("OpenALAQS/last_alaqs_output_file_path", "")
        self.ui.alaqs_output_file_path.setFilePath(last_alaqs_output_file)
        self.ui.alaqs_output_file_path.fileChanged.connect(
            self._on_alaqs_output_file_changed
        )

        # Configure ALAQS output work directory widget
        self.ui.alaqs_output_work_dir_path.setStorageMode(QgsFileWidget.GetDirectory)
        self.ui.alaqs_output_work_dir_path.setDialogTitle(
            "Select Output Work Directory for Generated Files"
        )
        last_alaqs_output_dir = s.value(
            "OpenALAQS/last_alaqs_output_directory_path", ""
        )
        self.ui.alaqs_output_work_dir_path.setFilePath(last_alaqs_output_dir)
        self.ui.alaqs_output_work_dir_path.fileChanged.connect(
            self._on_alaqs_output_directory_changed
        )

        # Connect ALAQS pollutant checkboxes to validation
        self.ui.alaqs_pollutant_nox.stateChanged.connect(
            self._validate_alaqs_generation_files
        )
        self.ui.alaqs_pollutant_co.stateChanged.connect(
            self._validate_alaqs_generation_files
        )
        self.ui.alaqs_pollutant_hc.stateChanged.connect(
            self._validate_alaqs_generation_files
        )
        self.ui.alaqs_pollutant_pm10.stateChanged.connect(
            self._validate_alaqs_generation_files
        )
        self.ui.alaqs_pollutant_sox.stateChanged.connect(
            self._validate_alaqs_generation_files
        )
        self.ui.alaqs_pollutant_co2.stateChanged.connect(
            self._validate_alaqs_generation_files
        )

        # Connect CSV pollutant checkboxes to validation
        self.ui.pollutant_nox.stateChanged.connect(self._validate_external_csv_files)
        self.ui.pollutant_co.stateChanged.connect(self._validate_external_csv_files)
        self.ui.pollutant_hc.stateChanged.connect(self._validate_external_csv_files)
        self.ui.pollutant_pm10.stateChanged.connect(self._validate_external_csv_files)
        self.ui.pollutant_sox.stateChanged.connect(self._validate_external_csv_files)
        self.ui.pollutant_co2.stateChanged.connect(self._validate_external_csv_files)

        # Connect AUSTAL quality level, mixing height, and datetime controls to status update
        self.ui.alaqs_quality_level_spinbox.valueChanged.connect(
            self._validate_alaqs_generation_files
        )
        self.ui.alaqs_mixing_height_checkbox.stateChanged.connect(
            self._validate_alaqs_generation_files
        )
        self.ui.alaqs_start_dt_edit.dateTimeChanged.connect(
            self._validate_alaqs_generation_files
        )
        self.ui.alaqs_end_dt_edit.dateTimeChanged.connect(
            self._validate_alaqs_generation_files
        )
        self.ui.csv_quality_level_spinbox.valueChanged.connect(
            self._validate_external_csv_files
        )
        self.ui.csv_mixing_height_checkbox.stateChanged.connect(
            self._validate_external_csv_files
        )
        self.ui.csv_start_dt_edit.dateTimeChanged.connect(
            self._validate_external_csv_files
        )
        self.ui.csv_end_dt_edit.dateTimeChanged.connect(
            self._validate_external_csv_files
        )

        # Connect radio buttons to toggle input modes
        self.ui.useExistingFilesRadio.toggled.connect(self._on_input_mode_changed)
        self.ui.generateFromAlaqsRadio.toggled.connect(self._on_input_mode_changed)
        self.ui.generateFromCsvRadio.toggled.connect(self._on_input_mode_changed)

        # Connect generate button
        self.ui.generateFromCsvBtn.clicked.connect(self._generate_austal_input_files)

        # Initial state
        self._on_input_mode_changed()

    def _get_austal_config_from_ui(self, mode: str = "alaqs") -> dict:
        """Get AUSTAL configuration from UI controls.

        Args:
            mode: "alaqs" or "csv" to determine which UI controls to read

        Returns:
            dict: AUSTAL dispersion module configuration
        """
        if mode == "alaqs":
            quality_level = int(self.ui.alaqs_quality_level_spinbox.value())
            mixing_height = self.ui.alaqs_mixing_height_checkbox.isChecked()
            notaluft = self.ui.alaqs_notaluft_checkbox.isChecked()
            try:
                pm10_fine_fraction = float(
                    self.ui.alaqs_pm10_fine_fraction_spinbox.value()
                )
            except Exception:
                pm10_fine_fraction = 0.9
        else:  # csv mode
            quality_level = int(self.ui.csv_quality_level_spinbox.value())
            mixing_height = self.ui.csv_mixing_height_checkbox.isChecked()
            notaluft = self.ui.csv_notaluft_checkbox.isChecked()
            # CSV path doesn't have a PM10 split control yet; use default.
            pm10_fine_fraction = 0.9

        # Build os= options string. NOTALUFT switches AUSTAL from
        # TA Luft mode (annual mean post-process only) to per-hour
        # series output. The latter is required for the result viewer
        # to produce hourly / 8-hour / daily means.
        if notaluft:
            options_string = "NOSTANDARD;NOTALUFT;Kmax=1"
        else:
            options_string = "NOSTANDARD;SCINOTAT;Kmax=1"

        return {
            "is_enabled": True,
            "quality_level": quality_level,
            "options_string": options_string,
            "roughness_length_m": 0.2,
            "displacement_height_m": 1.2,
            "anemometer_height_m": 11.2,
            "mixing_height_enabled": mixing_height,
            "pm10_fine_fraction": pm10_fine_fraction,
        }

    def _read_receptor_csv(self, csv_path):
        """Read a receptor CSV into a GeoDataFrame.

        Returns None on any failure (caller decides fallback). Required
        columns: longitude, latitude (case-insensitive, lon/lat aliases
        accepted). Optional: height (default 1.5m), EPSG (default 4326),
        id (label only).
        """
        try:
            import geopandas as gpd
            import pandas as pd
        except Exception as e:
            logger.warning(
                "Receptor CSV read skipped (geopandas/pandas import failed): %s",
                e,
            )
            return None
        if not csv_path or not os.path.isfile(csv_path):
            return None
        try:
            df = pd.read_csv(csv_path)
            df.columns = [c.strip().lower() for c in df.columns]
            if "longitude" not in df.columns and "lon" in df.columns:
                df = df.rename(columns={"lon": "longitude"})
            if "latitude" not in df.columns and "lat" in df.columns:
                df = df.rename(columns={"lat": "latitude"})
            if "longitude" not in df.columns or "latitude" not in df.columns:
                raise ValueError(
                    "Receptor CSV must contain 'longitude' and 'latitude' "
                    "columns (case-insensitive). Got: %s" % list(df.columns)
                )
            if "height" not in df.columns:
                df["height"] = 1.5
            if "epsg" in df.columns and "EPSG" not in df.columns:
                df = df.rename(columns={"epsg": "EPSG"})
            if "EPSG" not in df.columns:
                df["EPSG"] = 4326
            logger.info(
                "Loaded %d receptor point(s) from CSV: %s",
                len(df),
                csv_path,
            )
            return gpd.GeoDataFrame(df)
        except Exception as e:
            logger.warning("Failed to load receptor CSV '%s': %s", csv_path, e)
            return None

    def _read_receptors_from_alaqs_db(self, alaqs_file):
        """Read shapes_receptor_points table into a GeoDataFrame.

        Returns None if the file isn't a readable SQLite DB or has no
        rows. Filters to instudy != 'N' (Y, blank, NULL all kept).
        """
        try:
            import geopandas as gpd
            import pandas as pd
        except Exception as e:
            logger.warning(
                "Receptor DB read skipped (geopandas/pandas import failed): %s",
                e,
            )
            return None
        if not alaqs_file or not os.path.isfile(alaqs_file):
            return None
        try:
            conn = sqlite3.connect(alaqs_file)
            cur = conn.cursor()
            cur.execute(
                "SELECT oid, source_id, xcoord, ycoord, height, instudy, "
                "AsText(geometry) FROM shapes_receptor_points"
            )
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            logger.warning(
                "Could not read shapes_receptor_points from '%s': %s",
                alaqs_file,
                e,
            )
            return None
        if not rows:
            return None
        accepted = []
        for oid, source_id, xc, yc, h, instudy, _wkt in rows:
            if instudy and str(instudy).strip().upper() == "N":
                continue
            accepted.append(
                {
                    "id": source_id or ("R%d" % oid),
                    "longitude": float(xc) if xc is not None else None,
                    "latitude": float(yc) if yc is not None else None,
                    "height": float(h) if h is not None else 1.5,
                    "EPSG": 3857,
                }
            )
        if not accepted:
            return None
        df = pd.DataFrame(accepted).dropna(subset=["longitude", "latitude"])
        if df.empty:
            return None
        logger.info(
            "Loaded %d receptor point(s) from %s (shapes_receptor_points).",
            len(df),
            alaqs_file,
        )
        return gpd.GeoDataFrame(df)

    def _empty_receptors_gdf(self):
        """Return an empty GeoDataFrame matching the receptor schema."""
        try:
            import geopandas as gpd
        except Exception:
            return None
        return gpd.GeoDataFrame()

    def _load_receptors(self, mode, alaqs_file=None):
        """Mode-aware receptor loader.

        mode='alaqs': read alaqs_receptors_csv_path → fall back to
            shapes_receptor_points in alaqs_file → empty.
        mode='csv': read csv_receptors_csv_path only (no .alaqs fallback,
            since CSV mode has no .alaqs file) → empty.
        mode='existing' or unknown: empty (no generation happening).

        Returns a GeoDataFrame (possibly empty). Empty means AUSTAL will
        run without xp/yp lines and TalMon will not write -tmpa.dmna,
        so the receptor-based result buttons will stay disabled.
        """
        if mode == "alaqs":
            csv_path = ""
            try:
                csv_path = self.ui.alaqs_receptors_csv_path.filePath().strip()
            except Exception:
                pass
            gdf = self._read_receptor_csv(csv_path)
            if gdf is not None and not gdf.empty:
                return gdf
            gdf = self._read_receptors_from_alaqs_db(alaqs_file)
            if gdf is not None and not gdf.empty:
                return gdf
            logger.info(
                "No receptor points (alaqs mode: CSV empty and .alaqs db "
                "has none). AUSTAL will run without xp/yp lines; "
                "Compliance Report and Plot Time Series will be disabled."
            )
            return self._empty_receptors_gdf()

        if mode == "csv":
            csv_path = ""
            try:
                csv_path = self.ui.csv_receptors_csv_path.filePath().strip()
            except Exception:
                pass
            gdf = self._read_receptor_csv(csv_path)
            if gdf is not None and not gdf.empty:
                return gdf
            logger.info(
                "No receptor points (CSV mode: receptor CSV empty or not "
                "provided). AUSTAL will run without xp/yp lines; "
                "Compliance Report and Plot Time Series will be disabled."
            )
            return self._empty_receptors_gdf()

        # 'existing' or unknown
        return self._empty_receptors_gdf()

    def _load_receptors_for_alaqs_path(self, alaqs_file):
        """Backward-compatible wrapper around _load_receptors('alaqs').

        Kept for any external callers that may still reach this name;
        new code should call _load_receptors(mode, alaqs_file) directly.
        """
        return self._load_receptors("alaqs", alaqs_file)

    def _generate_austal_input_files(self):
        """Generate AUSTAL input files from CSV files or OpenALAQS output file.

        This method:
        1. Determines which generation path to use (CSV or ALAQS)
        2. Creates a subdirectory "AUSTAL" in the output directory
        3. For ALAQS mode: processes the OpenALAQS file for selected pollutants
        4. For CSV mode: CSV generation with selected pollutants
        5. Marks files as generated and stores the work directory
        6. Enables the Run AUSTAL button
        """
        use_alaqs = self._input_mode() == "alaqs"
        use_csv = self._input_mode() == "csv"

        # Determine the base output directory
        if use_alaqs:
            base_dir = self.ui.alaqs_output_work_dir_path.filePath()
            selected_pollutants = self._get_selected_alaqs_pollutants()
        elif use_csv:
            base_dir = self.ui.output_directory_path.filePath()
            selected_pollutants = self._get_selected_pollutants()
        else:
            return

        # Create AUSTAL_inputs subdirectory path
        austal_inputs_dir = os.path.join(base_dir, "AUSTAL")

        # Check if directory exists and is not empty
        if os.path.exists(austal_inputs_dir) and os.path.isdir(austal_inputs_dir):

            # Check if directory has any files
            dir_contents = os.listdir(austal_inputs_dir)
            if dir_contents:  # Directory is not empty

                # Show warning dialog
                reply = QtWidgets.QMessageBox.warning(
                    self,
                    "Directory Not Empty",
                    "All existing files in this directory will be overwritten.\n\n"
                    "Do you want to continue?",
                    QtWidgets.QMessageBox.StandardButton.Yes
                    | QtWidgets.QMessageBox.StandardButton.No,
                    QtWidgets.QMessageBox.StandardButton.No,  # Default to No for safety
                )

                if reply == QtWidgets.QMessageBox.StandardButton.No:
                    # User chose not to overwrite and shows the messsage to select a different directory
                    if use_alaqs:
                        self.ui.alaqsGenerationStatusLabel.setText(
                            "Generation cancelled. Please select a different output directory."
                        )
                        self.ui.alaqsGenerationStatusLabel.setStyleSheet(
                            STATUS_STYLE_WARNING
                        )
                    else:
                        self.ui.external_files_feedback.setText(
                            "Generation cancelled. Please select a different output directory."
                        )
                        self.ui.external_files_feedback.setStyleSheet(
                            STATUS_STYLE_WARNING
                        )
                    return

                # User chose Yes then proceed with the overwritting
                logger.info(f"User confirmed overwriting files in: {austal_inputs_dir}")

                shutil.rmtree(austal_inputs_dir)

        # Create the AUSTAL inputs directory (always needed, whether it existed or not)
        try:
            os.makedirs(austal_inputs_dir, exist_ok=True)
        except Exception as e:
            error_msg = f"Failed to create AUSTAL inputs directory: {e}"
            if use_alaqs:
                self.ui.alaqsGenerationStatusLabel.setText(error_msg)
                self.ui.alaqsGenerationStatusLabel.setStyleSheet(STATUS_STYLE_ERROR)
            else:
                self.ui.external_files_feedback.setText(error_msg)
                self.ui.external_files_feedback.setStyleSheet(STATUS_STYLE_ERROR)
            return

        # Read selected time period from UI
        def _qdatetime_to_py(qdt: QtCore.QDateTime) -> datetime:
            d, t = qdt.date(), qdt.time()
            return datetime(
                d.year(), d.month(), d.day(), t.hour(), t.minute(), t.second()
            )

        if use_alaqs:
            sel_start = _qdatetime_to_py(self.ui.alaqs_start_dt_edit.dateTime())
            sel_end = _qdatetime_to_py(self.ui.alaqs_end_dt_edit.dateTime())
        else:
            sel_start = _qdatetime_to_py(self.ui.csv_start_dt_edit.dateTime())
            sel_end = _qdatetime_to_py(self.ui.csv_end_dt_edit.dateTime())

        # Validate selected time period against available data
        def _set_status_error(msg: str) -> None:
            if use_alaqs:
                self.ui.alaqsGenerationStatusLabel.setText(msg)
                self.ui.alaqsGenerationStatusLabel.setStyleSheet(STATUS_STYLE_ERROR)
            else:
                self.ui.external_files_feedback.setText(msg)
                self.ui.external_files_feedback.setStyleSheet(STATUS_STYLE_ERROR)

        try:
            if use_alaqs:
                available = get_inventory_timestamps(
                    self.ui.alaqs_output_file_path.filePath()
                )
            else:
                available = []
                emissions_csv_path = self.ui.emissions_csv_path.filePath()
                with open(emissions_csv_path, "r") as _f:
                    _reader = csv.DictReader(_f)
                    for _row in _reader:
                        for _col in (
                            "DateTime(YYYY-mm-dd hh:mm:ss)",
                            "DateTime",
                            "datetime",
                            "date_time",
                        ):
                            if _col in _row:
                                try:
                                    available.append(
                                        datetime.strptime(
                                            _row[_col], "%Y-%m-%d %H:%M:%S"
                                        )
                                    )
                                except ValueError:
                                    pass
                                break
                available.sort()

            if len(available) >= 2:
                avail_start, avail_end = available[0], available[-1]
                if (
                    sel_start < avail_start
                    or sel_end > avail_end
                    or sel_start >= sel_end
                ):
                    fmt = "%d-%m-%Y %H:%M"
                    _set_status_error(
                        f"AUSTAL input files could not be created: the selected time period "
                        f"({sel_start.strftime(fmt)} – {sel_end.strftime(fmt)}) is not available in the data. "
                        f"Available range: {avail_start.strftime(fmt)} – {avail_end.strftime(fmt)}."
                    )
                    return
        except Exception as _e:
            logger.warning(f"Could not validate time period: {_e}")

        try:
            if use_alaqs:
                # Generate from OpenALAQS output file for selected pollutants
                alaqs_file = self.ui.alaqs_output_file_path.filePath()
                self._generate_from_alaqs_file(
                    alaqs_file,
                    austal_inputs_dir,
                    selected_pollutants,
                    sel_start,
                    sel_end,
                )
            elif use_csv:
                # Generate from CSV files for selected pollutants
                emissions_csv = self.ui.emissions_csv_path.filePath()
                meteo_csv = self.ui.meteo_csv_path.filePath()
                grid_config = self.get_current_grid_config()

                logger.info(
                    f"Generating AUSTAL input files from CSV for pollutants: {', '.join(selected_pollutants)}"
                )
                logger.info(
                    f"Time period: {sel_start.strftime('%d-%m-%Y %H:%M')} – {sel_end.strftime('%d-%m-%Y %H:%M')}"
                )
                logger.info(f"Grid config: {grid_config}")

                austal_cfg = self._get_austal_config_from_ui(mode="csv")
                receptors_gdf = self._load_receptors("csv")
                generate_austal_from_csv(
                    emissions_csv_path=emissions_csv,
                    meteo_csv_path=meteo_csv,
                    grid_config=grid_config,
                    austal_config=austal_cfg,
                    output_dir=austal_inputs_dir,
                    selected_pollutants=selected_pollutants,
                    start_dt=sel_start,
                    end_dt=sel_end,
                    receptors=receptors_gdf,
                )
        except Exception as e:
            error_msg = f"Error generating AUSTAL input files: {e}"
            if use_alaqs:
                self.ui.alaqsGenerationStatusLabel.setText(error_msg)
                self.ui.alaqsGenerationStatusLabel.setStyleSheet(STATUS_STYLE_ERROR)
            else:
                self.ui.external_files_feedback.setText(error_msg)
                self.ui.external_files_feedback.setStyleSheet(STATUS_STYLE_ERROR)
            logger.error(error_msg, exc_info=True)
            return

        # Mark files as generated and store directory
        self._austal_input_files_generated = True
        self._generated_austal_work_dir = austal_inputs_dir

        # Enable Run AUSTAL button after successful generation
        self.ui.RunA2K.setEnabled(True)

        # Update status
        status_msg = (
            f"AUSTAL input files generated successfully. Path: {austal_inputs_dir}"
        )
        if use_alaqs:
            self.ui.alaqsGenerationStatusLabel.setText(status_msg)
            self.ui.alaqsGenerationStatusLabel.setStyleSheet(STATUS_STYLE_SUCCESS)
        else:
            self.ui.external_files_feedback.setText(status_msg)
            self.ui.external_files_feedback.setStyleSheet(STATUS_STYLE_SUCCESS)

    def _generate_from_alaqs_file(
        self,
        alaqs_file: str,
        output_dir: str,
        selected_pollutants: list,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
    ) -> None:
        """Generate AUSTAL input files from an OpenALAQS output file.

        Uses EmissionCalculation directly with source modules and the AUSTAL
        dispersion module to generate input files (austal.txt, series.dmna,
        grid .dmna files) for each selected pollutant.

        The *_out.alaqs file contains all necessary input data (movements,
        geometries, meteorology, profiles) but not pre-calculated emissions,
        so source modules must still run to calculate them. The AUSTAL
        dispersion module is attached to distribute emissions onto the grid.

        Args:
            alaqs_file: Path to the OpenALAQS output file (*_out.alaqs)
            output_dir: Output directory where AUSTAL input files will be written
            selected_pollutants: List of selected pollutants to generate files for
            start_dt: Start of the time period to generate files for (inclusive).
                      Defaults to the first timestamp in the file.
            end_dt: End of the time period to generate files for (inclusive).
                    Defaults to the last timestamp in the file.
        """
        logger.info(f"Generating AUSTAL input files from {alaqs_file}")
        logger.info(f"Selected pollutants: {', '.join(selected_pollutants)}")
        logger.info(f"Output directory: {output_dir}")

        # Get quality level and mixing height settings for status message
        quality_level = int(self.ui.alaqs_quality_level_spinbox.value())
        mixing_height_enabled = self.ui.alaqs_mixing_height_checkbox.isChecked()
        mixing_height_status = "enabled" if mixing_height_enabled else "disabled"
        logger.info(
            f"AUSTAL parameters - Quality level: {quality_level}, Mixing height: {mixing_height_status}"
        )

        # Get time series from the ALAQS output file
        timestamps = get_inventory_timestamps(alaqs_file)
        if len(timestamps) < 2:
            raise ValueError(
                "OpenALAQS file does not contain enough time steps (need at least 2)"
            )

        # Use caller-supplied range or fall back to the full range from the file
        if start_dt is None:
            start_dt = timestamps[0]
        if end_dt is None:
            end_dt = timestamps[-1]
        time_interval = timestamps[1] - timestamps[0]

        logger.info(
            f"Time period: {start_dt.strftime('%d-%m-%Y %H:%M')} – {end_dt.strftime('%d-%m-%Y %H:%M')} (interval: {time_interval})"
        )

        # Read grid configuration from the ALAQS file
        conn = sqlite3.connect(alaqs_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT x_cells, y_cells, z_cells, x_resolution, y_resolution, "
            "z_resolution, reference_latitude, reference_longitude "
            'FROM "grid_3d_definition" LIMIT 1'
        )
        grid_row = cursor.fetchone()
        conn.close()

        if grid_row is None:
            raise ValueError("No grid_3d_definition found in OpenALAQS file")

        grid_config: GridConfig = {
            "x_cells": int(grid_row["x_cells"]),
            "y_cells": int(grid_row["y_cells"]),
            "z_cells": int(grid_row["z_cells"]),
            "x_resolution": float(grid_row["x_resolution"]),
            "y_resolution": float(grid_row["y_resolution"]),
            "z_resolution": float(grid_row["z_resolution"]),
            "reference_latitude": float(grid_row["reference_latitude"]),
            "reference_longitude": float(grid_row["reference_longitude"]),
            "reference_altitude": 0.0,
        }

        logger.info(f"Grid configuration: {grid_config}")

        # Initialize EmissionCalculation directly (bypasses EmissionCalculatorService)
        emission_calc = EmissionCalculation(
            db_path=alaqs_file,
            grid_config=grid_config,
            start_dt=start_dt,
            end_dt=end_dt,
            time_interval=time_interval,
        )

        # Add all source modules (movements, area sources, parking, etc.)
        source_module_names = SourceModuleRegistry().get_module_names()
        for module_name in source_module_names:
            emission_calc.add_source_module(
                module_name,
                {
                    "method": "bymode",
                    "should_apply_nox_corrections": False,
                    "source_dynamics": "none",
                    "reference_altitude": grid_config.get("reference_altitude", 0.0),
                    "show_progress": False,
                    "receptors": None,
                },
            )
            logger.info(f"Added source module: {module_name}")

        # Add AUSTAL dispersion module for the selected pollutants
        austal_config = self._get_austal_config_from_ui()
        receptors_gdf = self._load_receptors("alaqs", alaqs_file)
        austal_config.update(
            {
                "output_path": output_dir,
                "pollutant": None,  # Will be set per pollutant below
                "pollutants_list": selected_pollutants,
                "title": "OpenALAQS AUSTAL generation",
                "grid": emission_calc.get3DGrid(),
                "receptors": receptors_gdf,
            }
        )

        emission_calc.add_dispersion_modules(["AUSTAL"], austal_config)
        logger.info(
            f"Added AUSTAL dispersion module with config: Quality level={austal_config['quality_level']}, Mixing height enabled={austal_config['mixing_height_enabled']}"
        )
        logger.debug(f"Full AUSTAL config: {austal_config}")

        # Run the calculation: source modules calculate emissions,
        # AUSTAL dispersion module writes input files
        logger.info("Running emission calculation with AUSTAL dispersion...")
        emission_calc.run(
            source_names=["all"],
            vertical_limit_m=914.4,
            show_progress=True,
        )
        emission_calc.sortEmissionsByTime()

        logger.info(
            f"AUSTAL input files generated for pollutants: {', '.join(selected_pollutants)}"
        )

    def _input_mode(self) -> str:
        """Return current input strategy: 'existing', 'alaqs', or 'csv'."""
        if self.ui.useExistingFilesRadio.isChecked():
            return "existing"
        if self.ui.generateFromAlaqsRadio.isChecked():
            return "alaqs"
        if self.ui.generateFromCsvRadio.isChecked():
            return "csv"
        return "existing"

    def _on_input_mode_changed(self, *_args) -> None:
        """Handle switching between input strategies.

        Called both on radio toggle and directly during init. Manages
        frame visibility, the generate button, generation flag reset,
        and Run AUSTAL button state for the active mode.
        """
        mode = self._input_mode()
        use_existing = mode == "existing"
        use_alaqs = mode == "alaqs"
        use_csv = mode == "csv"

        # Show/hide and enable/disable the frames based on selection
        self.ui.existingFilesFrame.setVisible(use_existing)
        self.ui.existingFilesFrame.setEnabled(use_existing)
        self.ui.generateFromAlaqsFrame.setVisible(use_alaqs)
        self.ui.generateFromAlaqsFrame.setEnabled(use_alaqs)
        self.ui.generateFromCsvFrame.setVisible(use_csv)
        self.ui.generateFromCsvFrame.setEnabled(use_csv)

        # Show/hide the generate button - only visible when generating
        # from OpenALAQS output or CSV
        self.ui.generateFromCsvBtn.setVisible(use_alaqs or use_csv)

        # Reset generation state when mode changes - need to regenerate files
        self._austal_input_files_generated = False
        self._generated_austal_work_dir = None

        # Validate and update feedback based on selected mode
        if use_existing:
            self.ui.RunA2K.setEnabled(
                bool(
                    self.ui.work_directory_path.filePath()
                    and os.path.isdir(self.ui.work_directory_path.filePath())
                )
            )
        elif use_alaqs:
            self._validate_alaqs_generation_files()
        elif use_csv:
            self._validate_external_csv_files()
        else:
            self.ui.RunA2K.setEnabled(False)

    def _on_alaqs_output_file_changed(self, path: str) -> None:
        """Handle OpenALAQS output file selection."""
        if os.path.isfile(path):
            s = QgsSettings()
            s.setValue("OpenALAQS/last_alaqs_output_file_path", path)
            try:
                timestamps = get_inventory_timestamps(path)
                if len(timestamps) >= 2:
                    dt_min = QtCore.QDateTime(
                        timestamps[0].year,
                        timestamps[0].month,
                        timestamps[0].day,
                        timestamps[0].hour,
                        timestamps[0].minute,
                        timestamps[0].second,
                    )
                    dt_max = QtCore.QDateTime(
                        timestamps[-1].year,
                        timestamps[-1].month,
                        timestamps[-1].day,
                        timestamps[-1].hour,
                        timestamps[-1].minute,
                        timestamps[-1].second,
                    )
                    self.ui.alaqs_start_dt_edit.setMinimumDateTime(dt_min)
                    self.ui.alaqs_start_dt_edit.setMaximumDateTime(dt_max)
                    self.ui.alaqs_start_dt_edit.setDateTime(dt_min)
                    self.ui.alaqs_end_dt_edit.setMinimumDateTime(dt_min)
                    self.ui.alaqs_end_dt_edit.setMaximumDateTime(dt_max)
                    self.ui.alaqs_end_dt_edit.setDateTime(dt_max)
            except Exception as e:
                logger.warning(f"Could not read timestamps from OpenALAQS file: {e}")
        self._validate_alaqs_generation_files()

    def _on_alaqs_output_directory_changed(self, dirname: str) -> None:
        """Handle OpenALAQS output directory selection."""
        if os.path.isdir(dirname):
            s = QgsSettings()
            s.setValue("OpenALAQS/last_alaqs_output_directory_path", dirname)
        self._validate_alaqs_generation_files()

    def _validate_alaqs_generation_files(self) -> None:
        """Validate the selected OpenALAQS output file and working directory."""
        # Only this validator owns the RunA2K state when the OpenALAQS
        # generation radio is active. If the user is in "Use Existing"
        # or "Generate from CSV" mode, leave RunA2K alone — that mode's
        # own handler is the source of truth.
        owns_run_button = self._input_mode() == "alaqs"

        alaqs_file = self.ui.alaqs_output_file_path.filePath()
        output_dir = self.ui.alaqs_output_work_dir_path.filePath()
        pollutants = self._get_selected_alaqs_pollutants()

        # Collect missing items
        missing = []
        if not alaqs_file or not os.path.isfile(alaqs_file):
            missing.append("OpenALAQS Emission Inventory (*_out.alaqs)")
        if not output_dir or not os.path.isdir(output_dir):
            missing.append("output directory")
        if not pollutants:
            missing.append("at least one pollutant")

        # Check if ALAQS file has grid_3d_definition if provided
        has_valid_grid = False
        if alaqs_file and os.path.isfile(alaqs_file):
            grid_def = get_grid_3d_definition(alaqs_file)
            has_valid_grid = grid_def is not None

        if missing:
            self.ui.alaqsGenerationStatusLabel.setText(f"Missing {', '.join(missing)}")
            self.ui.alaqsGenerationStatusLabel.setStyleSheet(STATUS_STYLE_WARNING)
            self.ui.generateFromCsvBtn.setEnabled(False)
            # Keep Run AUSTAL enabled if files have already been generated (user may have deselected pollutant by mistake)
            if owns_run_button and not self._austal_input_files_generated:
                self.ui.RunA2K.setEnabled(False)
            return

        if alaqs_file and os.path.isfile(alaqs_file) and not has_valid_grid:
            self.ui.alaqsGenerationStatusLabel.setText(
                "Selected OpenALAQS output file (emission inventory *_out.alaqs) is not valid"
            )
            self.ui.alaqsGenerationStatusLabel.setStyleSheet(STATUS_STYLE_ERROR)
            self.ui.generateFromCsvBtn.setEnabled(False)
            # Keep Run AUSTAL enabled if files have already been generated
            if owns_run_button and not self._austal_input_files_generated:
                self.ui.RunA2K.setEnabled(False)
            return

        # All inputs valid - enable generate button, but Run AUSTAL only after generation succeeds
        selected_list = ", ".join(pollutants)
        quality_level = int(self.ui.alaqs_quality_level_spinbox.value())
        mixing_height_enabled = self.ui.alaqs_mixing_height_checkbox.isChecked()
        mixing_height_status = "enabled" if mixing_height_enabled else "disabled"
        _fmt = "dd-MM-yyyy HH:mm"
        start_str = self.ui.alaqs_start_dt_edit.dateTime().toString(_fmt)
        end_str = self.ui.alaqs_end_dt_edit.dateTime().toString(_fmt)
        status_text = (
            f"Ready to generate AUSTAL input files. "
            f"Pollutants: {selected_list} | "
            f"Period: {start_str} – {end_str} | "
            f"Quality level: {quality_level}, Mixing height: {mixing_height_status}"
        )
        self.ui.alaqsGenerationStatusLabel.setText(status_text)
        self.ui.alaqsGenerationStatusLabel.setStyleSheet(STATUS_STYLE_SUCCESS)
        self.ui.generateFromCsvBtn.setEnabled(True)
        # Only enable Run AUSTAL if files have been generated
        if owns_run_button:
            self.ui.RunA2K.setEnabled(self._austal_input_files_generated)

    def _on_output_directory_changed(self, dirname: str) -> None:
        """Handle output directory selection for CSV generation."""
        if os.path.isdir(dirname):
            s = QgsSettings()
            s.setValue("OpenALAQS/last_csv_output_directory_path", dirname)
        self._validate_external_csv_files()

    def _on_emissions_csv_changed(self, path: str) -> None:
        """Handle emissions CSV file selection."""
        if os.path.isfile(path):
            s = QgsSettings()
            s.setValue("OpenALAQS/last_emissions_csv_path", path)
            self._update_csv_datetime_range()
        self._validate_external_csv_files()

    def _update_csv_datetime_range(self) -> None:
        """Parse the emissions CSV to set min/max limits on the CSV datetime pickers."""
        emissions_path = self.ui.emissions_csv_path.filePath()
        if not emissions_path or not os.path.isfile(emissions_path):
            return
        try:
            timestamps = []
            with open(emissions_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    raw = (row.get("timestamp") or "").strip()
                    if raw:
                        try:
                            timestamps.append(datetime.fromisoformat(raw))
                        except ValueError:
                            pass
            if len(timestamps) >= 2:
                timestamps.sort()
                dt_min = QtCore.QDateTime(
                    timestamps[0].year,
                    timestamps[0].month,
                    timestamps[0].day,
                    timestamps[0].hour,
                    timestamps[0].minute,
                    timestamps[0].second,
                )
                dt_max = QtCore.QDateTime(
                    timestamps[-1].year,
                    timestamps[-1].month,
                    timestamps[-1].day,
                    timestamps[-1].hour,
                    timestamps[-1].minute,
                    timestamps[-1].second,
                )
                self.ui.csv_start_dt_edit.setMinimumDateTime(dt_min)
                self.ui.csv_start_dt_edit.setMaximumDateTime(dt_max)
                self.ui.csv_start_dt_edit.setDateTime(dt_min)
                self.ui.csv_end_dt_edit.setMinimumDateTime(dt_min)
                self.ui.csv_end_dt_edit.setMaximumDateTime(dt_max)
                self.ui.csv_end_dt_edit.setDateTime(dt_max)
        except Exception as e:
            logger.warning(f"Could not read timestamps from emissions CSV: {e}")

    def _on_meteo_csv_changed(self, path: str) -> None:
        """Handle meteorology CSV file selection."""
        if os.path.isfile(path):
            s = QgsSettings()
            s.setValue("OpenALAQS/last_meteo_csv_path", path)
        self._validate_external_csv_files()

    def _validate_external_csv_files(self) -> None:
        """Validate the selected external CSV files, output directory, and grid configuration."""
        # Only this validator owns RunA2K when the CSV generation radio
        # is active. Otherwise leave the button alone.
        owns_run_button = self._input_mode() == "csv"

        output_dir = self.ui.output_directory_path.filePath()
        emissions_path = self.ui.emissions_csv_path.filePath()
        meteo_path = self.ui.meteo_csv_path.filePath()
        selected_pollutants = self._get_selected_pollutants()
        grid_config = self.get_current_grid_config()

        # Collect missing items
        missing = []
        if not output_dir or not os.path.isdir(output_dir):
            missing.append("output directory")
        if not emissions_path or not os.path.isfile(emissions_path):
            missing.append("emissions CSV")
        if not meteo_path or not os.path.isfile(meteo_path):
            missing.append("meteo CSV")
        if not selected_pollutants:
            missing.append("at least one pollutant")
        if not grid_config:
            missing.append(
                "grid configuration (load or define in Grid Management section)"
            )

        if missing:
            self.ui.external_files_feedback.setText(f"Missing {', '.join(missing)}")
            self.ui.external_files_feedback.setStyleSheet(STATUS_STYLE_WARNING)
            self.ui.generateFromCsvBtn.setEnabled(False)
            # Keep Run AUSTAL enabled if files have already been generated (user may have deselected pollutant by mistake)
            if owns_run_button and not self._austal_input_files_generated:
                self.ui.RunA2K.setEnabled(False)
            return

        # All inputs valid - enable generate button, but Run AUSTAL only after generation succeeds
        selected_list = ", ".join(selected_pollutants)
        quality_level = int(self.ui.csv_quality_level_spinbox.value())
        mixing_height_enabled = self.ui.csv_mixing_height_checkbox.isChecked()
        mixing_height_status = "enabled" if mixing_height_enabled else "disabled"
        _fmt = "dd-MM-yyyy HH:mm"
        start_str = self.ui.csv_start_dt_edit.dateTime().toString(_fmt)
        end_str = self.ui.csv_end_dt_edit.dateTime().toString(_fmt)
        self.ui.external_files_feedback.setText(
            f"Ready to generate AUSTAL input files. "
            f"Pollutants: {selected_list} | "
            f"Period: {start_str} – {end_str} | "
            f"Quality level: {quality_level}, Mixing height: {mixing_height_status}"
        )
        self.ui.external_files_feedback.setStyleSheet(STATUS_STYLE_SUCCESS)
        self.ui.generateFromCsvBtn.setEnabled(True)
        # Only enable Run AUSTAL if files have been generated
        if owns_run_button:
            self.ui.RunA2K.setEnabled(self._austal_input_files_generated)

    # Display the text when the user presses the AUSTAL HELP buttton
    def show_austal_help(self):
        """
        Display AUSTAL setup instructions in a dialog
        """
        help_text = """
        <b>AUSTAL Setup Instructions</b><br><br>

        <b>Download AUSTAL:</b><br>
        Visit: <a href="https://www.umweltbundesamt.de/en/topics/air/air-quality-control-in-europe/download">
        AUSTAL Download Page</a><br><br>

        <b>Available Versions:</b><br>
        • Windows: AUSTAL_3.3.0.zip<br>
        • Linux: AUSTAL_3.3.0.zip<br><br>

        <b>Installation Steps:</b><br>
        1. Download the AUSTAL base package for your OS<br>
        2. Extract the package to your desired location<br>
        3. Replace austal.settings with the one provided here: <a href="https://github.com/eurocontrol-asu/open_alaqs/tree/main/documents/AUSTAL/austal.settings"> austal.settings </a> <br>
        4. Ensure the AUSTAL executable is in your system PATH<br>
        5. Select the austal.exe (or austal) file above<br><br>

        <b>Configuration Files:</b><br>
        • <a href="https://github.com/eurocontrol-asu/open_alaqs/tree/main/documents/AUSTAL/austal.settings">
        austal.settings</a> - Main AUSTAL configuration file<br>
        • AST_en and DIA_en - English language files (included in AUSTAL distribution)<br><br>

        <b>For More Information:</b><br>
        See <a href="https://github.com/eurocontrol-asu/open_alaqs/tree/main/documents/AUSTAL//AUSTAL.md">
        AUSTAL.md</a> in the OpenALAQS documentation folder.
        """

        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setWindowTitle("AUSTAL Setup Help")
        msg_box.setText(help_text)
        msg_box.setTextFormat(QtCore.Qt.TextFormat.RichText)
        msg_box.setIcon(QtWidgets.QMessageBox.Icon.Information)
        msg_box.exec()

    def _get_austal_work_directory(self) -> str:
        """Get the work directory for AUSTAL based on selected input mode.

        For generation modes (CSV/ALAQS), returns the directory where input files
        were generated. For existing files mode, returns the selected directory.
        """
        # If files have been generated, use the generated directory
        if self._austal_input_files_generated and self._generated_austal_work_dir:
            return self._generated_austal_work_dir

        # Otherwise, determine based on selected mode
        if self._input_mode() == "alaqs":
            # Use the output directory from OpenALAQS generation
            return str(self.ui.alaqs_output_work_dir_path.filePath())
        elif self._input_mode() == "csv":
            # Use the output directory from CSV generation
            return str(self.ui.output_directory_path.filePath())
        else:
            # Use the existing files work directory
            return str(self.ui.work_directory_path.filePath())

    def _get_selected_pollutants(self) -> list:
        """Get list of selected pollutants for CSV generation mode."""
        pollutants = []
        if self.ui.pollutant_nox.isChecked():
            pollutants.append("NOx")
        if self.ui.pollutant_co.isChecked():
            pollutants.append("CO")
        if self.ui.pollutant_hc.isChecked():
            pollutants.append("HC")
        if self.ui.pollutant_pm10.isChecked():
            pollutants.append("PM10")
        if self.ui.pollutant_sox.isChecked():
            pollutants.append("SOx")
        if self.ui.pollutant_co2.isChecked():
            pollutants.append("CO2")
        return pollutants

    def _get_selected_alaqs_pollutants(self) -> list:
        """Get list of selected pollutants for OpenALAQS generation mode."""
        pollutants = []
        if self.ui.alaqs_pollutant_nox.isChecked():
            pollutants.append("NOx")
        if self.ui.alaqs_pollutant_co.isChecked():
            pollutants.append("CO")
        if self.ui.alaqs_pollutant_hc.isChecked():
            pollutants.append("HC")
        if self.ui.alaqs_pollutant_pm10.isChecked():
            pollutants.append("PM10")
        if self.ui.alaqs_pollutant_sox.isChecked():
            pollutants.append("SOx")
        if self.ui.alaqs_pollutant_co2.isChecked():
            pollutants.append("CO2")
        return pollutants

    def _validate_austal_inputs(self) -> tuple[bool, str]:
        """Validate all required inputs for AUSTAL based on selected input mode.

        Returns:
            tuple: (is_valid, error_message)
        """
        # Check executable is selected
        if not self.ui.a2k_executable_path.filePath() or not os.path.isfile(
            self.ui.a2k_executable_path.filePath()
        ):
            return False, "Please select a valid AUSTAL executable file (Section 1)"

        # Check mode-specific requirements
        if self._input_mode() == "existing":
            work_dir = self.ui.work_directory_path.filePath()
            if not work_dir or not os.path.isdir(work_dir):
                return (
                    False,
                    "Please select a valid work directory with AUSTAL input files",
                )

        elif self._input_mode() == "alaqs":
            alaqs_file = self.ui.alaqs_output_file_path.filePath()
            output_dir = self.ui.alaqs_output_work_dir_path.filePath()
            pollutants = self._get_selected_alaqs_pollutants()

            if not alaqs_file or not os.path.isfile(alaqs_file):
                return False, "Please select a valid OpenALAQS output file"
            if not output_dir or not os.path.isdir(output_dir):
                return False, "Please select a valid output work directory"
            if not pollutants:
                return False, "Please select at least one pollutant"

            # Check for grid_3d_definition
            if not has_grid_3d_definition(alaqs_file):
                return (
                    False,
                    "Selected OpenALAQS file does not have a valid grid_3d_definition",
                )

        elif self._input_mode() == "csv":
            output_dir = self.ui.output_directory_path.filePath()
            emissions_csv = self.ui.emissions_csv_path.filePath()
            meteo_csv = self.ui.meteo_csv_path.filePath()
            pollutants = self._get_selected_pollutants()

            if not output_dir or not os.path.isdir(output_dir):
                return False, "Please select a valid output directory"
            if not emissions_csv or not os.path.isfile(emissions_csv):
                return False, "Please select a valid emissions CSV file"
            if not meteo_csv or not os.path.isfile(meteo_csv):
                return False, "Please select a valid meteorology CSV file"
            if not pollutants:
                return False, "Please select at least one pollutant"

        return True, ""

    @catch_errors
    def run_austal(self, *args, **kwargs):
        import subprocess as _sp
        from subprocess import Popen

        try:
            # Validate all inputs before running
            is_valid, error_message = self._validate_austal_inputs()
            if not is_valid:
                self.ui.executionStatusLabel.setText(
                    f"Status: Validation Failed: {error_message}"
                )
                self.ui.executionStatusLabel.setStyleSheet(STATUS_STYLE_WARNING)
                QtWidgets.QMessageBox.warning(
                    self,
                    "Input Validation Failed",
                    f"Unable to run AUSTAL:\n\n{error_message}",
                )
                return

            # Update status to running
            self.ui.executionStatusLabel.setText("Status: Running AUSTAL...")
            self.ui.executionStatusLabel.setStyleSheet(STATUS_STYLE_INFO)
            QtWidgets.QApplication.processEvents()  # Update UI immediately

            austal_ = str(self.ui.a2k_executable_path.filePath())
            logger.info("AUSTAL directory:%s" % austal_)
            work_dir = self._get_austal_work_directory()
            logger.info("AUSTAL input files directory:%s" % work_dir)

            if not work_dir or not os.path.isdir(work_dir):
                self.ui.executionStatusLabel.setText(
                    "Status: Error - Invalid input directory"
                )
                self.ui.executionStatusLabel.setStyleSheet(STATUS_STYLE_ERROR)
                QtWidgets.QMessageBox.warning(
                    self,
                    "Warning",
                    "Please select a valid directory containing AUSTAL input files.",
                )
                return

            if self.ui.erase_log.isChecked():
                opt_ = "D"
                logger.info(
                    "Running AUSTAL with -D option. Log file will be re-written"
                    " at the start of the calculation."
                )
                cmd = [austal_, "-%s" % (opt_), work_dir]
            else:
                cmd = [austal_, work_dir]

            # Don't redirect stdout/stderr. On Windows the OS allocates a
            # console window for AUSTAL automatically; with redirection the
            # window stays blank for the entire (potentially hour-long) run.
            # Letting output flow through gives the user live progress.
            # CREATE_NEW_CONSOLE forces a fresh console even when QGIS was
            # itself launched from one (otherwise AUSTAL's output would
            # interleave with QGIS console output).
            creationflags = 0
            if hasattr(_sp, "CREATE_NEW_CONSOLE"):
                creationflags = _sp.CREATE_NEW_CONSOLE

            p = Popen(cmd, creationflags=creationflags)
            p.wait()

            if p.returncode != 0:
                # Output was written to AUSTAL's own console; pull error
                # detail from austal.log in the work dir if it exists.
                err_msg = f"AUSTAL exited with code {p.returncode}."
                log_path = os.path.join(work_dir, "austal.log")
                if os.path.isfile(log_path):
                    try:
                        with open(
                            log_path, "r", encoding="utf-8", errors="replace"
                        ) as fh:
                            tail = fh.readlines()[-40:]
                        err_msg += "\n\nLast 40 lines of austal.log:\n" + (
                            "".join(tail)
                        )
                    except OSError as exc_:
                        err_msg += f"\n(Could not read austal.log: {exc_})"
                else:
                    err_msg += "\nSee the AUSTAL console window for details."
                raise Austal2000RunError(err_msg)

            # Update status to completed
            self.ui.executionStatusLabel.setText("Status: Completed successfully")
            self.ui.executionStatusLabel.setStyleSheet(STATUS_STYLE_SUCCESS)

            # Mark results as loaded and update visualisation status with grid details
            self._results_loaded = True
            self._austal_ran = True

            # Snapshot grid based on which input mode was used
            if self._input_mode() == "alaqs":
                # Option B: Use grid from the ALAQS file
                alaqs_file = self.ui.alaqs_output_file_path.filePath()
                try:
                    conn = sqlite3.connect(alaqs_file)
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT x_cells, y_cells, z_cells, x_resolution, y_resolution, "
                        "z_resolution, reference_latitude, reference_longitude "
                        'FROM "grid_3d_definition" LIMIT 1'
                    )
                    grid_row = cursor.fetchone()
                    cursor.execute('SELECT airport_elevation FROM "user_study_setup"')
                    alt_row = cursor.fetchone()
                    conn.close()

                    if grid_row:
                        self._austal_grid_config = {
                            "x_cells": int(grid_row["x_cells"]),
                            "y_cells": int(grid_row["y_cells"]),
                            "z_cells": int(grid_row["z_cells"]),
                            "x_resolution": float(grid_row["x_resolution"]),
                            "y_resolution": float(grid_row["y_resolution"]),
                            "z_resolution": float(grid_row["z_resolution"]),
                            "reference_latitude": float(grid_row["reference_latitude"]),
                            "reference_longitude": float(
                                grid_row["reference_longitude"]
                            ),
                            "reference_altitude": (
                                float(alt_row["airport_elevation"]) if alt_row else 0.0
                            ),
                        }
                except Exception as e:
                    logger.warning(f"Could not load grid from ALAQS file: {e}")
                    self._austal_grid_config = (
                        self.get_current_grid_config().copy()
                        if self.get_current_grid_config()
                        else None
                    )
            elif self._input_mode() == "csv":
                # Option C: Use G1 grid from spinboxes
                self._austal_grid_config = (
                    self.get_current_grid_config().copy()
                    if self.get_current_grid_config()
                    else None
                )
            else:
                # Option A: Use default/existing grid
                self._austal_grid_config = (
                    self.get_current_grid_config().copy()
                    if self.get_current_grid_config()
                    else None
                )

            self._update_visualization_status_label()

            # Update result buttons - AUSTAL has run, so buttons should be enabled
            self._update_result_buttons_state()

            # Auto-detect and update pollutant/averaging options from work directory outputs
            try:
                self._detect_and_update_pollutants_and_averaging(work_dir)
            except Exception as _e:
                logger.warning("Auto-detection after AUSTAL run failed: %s", _e)

            QtWidgets.QMessageBox.information(
                self, "Success", "Dispersion simulation completed successfully"
            )
            logger.info("Dispersion simulation completed successfully")
        except Exception as exception:
            # Update status to error
            self.ui.executionStatusLabel.setText("Status: Failed")
            self.ui.executionStatusLabel.setStyleSheet(STATUS_STYLE_ERROR)
            QtWidgets.QMessageBox.critical(
                self, "Error", "AUSTAL execution failed! See the log for details."
            )

            if isinstance(exception, Austal2000RunError):
                logger.error(
                    f"AUSTAL execution failed with the following output:\n{exception}"
                )
            else:
                logger.error(
                    f"AUSTAL execution failed with the following error: {exception}",
                    exc_info=exception,
                )

    def _detect_and_update_pollutants_and_averaging(self, results_dir: str) -> None:
        """Scan a directory for AUSTAL .dmna files and update pollutant/averaging comboboxes.

        This helper is also called after running AUSTAL so the UI reflects newly
        produced output files even when the user hasn't selected a separate
        results directory.
        """
        try:
            if not results_dir or not os.path.isdir(results_dir):
                return

            dmna_files = [
                f for f in os.listdir(results_dir) if f.lower().endswith(".dmna")
            ]

            # Scan filenames for known pollutant tokens; skip 'series.dmna' and similar generic files
            # TODO: ALso map p1 and p2
            known_tokens = ["nox", "co", "hc", "pm", "sox", "co2"]
            found_codes = set()
            for fn in dmna_files:
                base = fn.lower()
                # Exclude generic series files.
                if base.startswith("series") or base == "series.dmna":
                    continue
                # Match token as whole word to avoid false positives (e.g. 'coX' vs 'co').
                for token in known_tokens:
                    token_re = token.replace(".", r"\\.")
                    if re.search(r"(^|[^a-z0-9])" + token_re + r"([^a-z0-9]|$)", base):
                        found_codes.add(token)
                        break

            # Map internal codes to UI display labels.
            code_to_display = {
                "nox": "NOx",
                "co": "CO",
                "hc": "HC",
                "pm": "PM10",
                "sox": "SOx",
                "co2": "CO2",
            }

            # Populate pollutant combo; preserve previous selection if available.
            available_display = [
                code_to_display.get(c, c.upper()) for c in sorted(found_codes)
            ]

            if hasattr(self.ui, "resultPollutantCombo"):
                prev = self.ui.resultPollutantCombo.currentText()
                self.ui.resultPollutantCombo.clear()
                for disp in available_display:
                    self.ui.resultPollutantCombo.addItem(disp)
                # Restore previous selection or default to first option.
                if prev and self.ui.resultPollutantCombo.findText(prev) >= 0:
                    self.ui.resultPollutantCombo.setCurrentText(prev)
                elif available_display:
                    self.ui.resultPollutantCombo.setCurrentIndex(0)

            # TODO: Detect averaging periods from filename patterns and add the option to generate the files on an hourly basis
            # averaging_options = ['hourly', '8-hours mean', 'daily mean', 'annual mean']
            self._setup_averaging_options()
        except Exception as _e:
            logger.warning(
                "Could not auto-detect pollutants/averaging from directory: %s", _e
            )

    def save_grid_as_csv(self) -> None:
        """
        Save the current grid configuration to a CSV file.

        The CSV will contain columns for:
        - x_cells, y_cells, z_cells (grid dimensions)
        - x_resolution, y_resolution, z_resolution (cell sizes)
        - reference_latitude, reference_longitude, reference_altitude (reference point)
        """
        try:
            # Open file save dialog
            file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Save Grid Configuration as CSV",
                "",
                "CSV Files (*.csv);;All Files (*)",
            )

            if not file_path:
                # User cancelled the dialog
                return

            # Ensure .csv extension
            if not file_path.endswith(".csv"):
                file_path += ".csv"

            # Get grid values from UI spinboxes
            grid_config = {
                "x_cells": int(self.ui.xCellsSpinBox.value()),
                "y_cells": int(self.ui.yCellsSpinBox.value()),
                "z_cells": int(self.ui.zCellsSpinBox.value()),
                "x_resolution": float(self.ui.xResolutionSpinBox.value()),
                "y_resolution": float(self.ui.yResolutionSpinBox.value()),
                "z_resolution": float(self.ui.zResolutionSpinBox.value()),
                "reference_latitude": float(self.ui.refLatSpinBox.value()),
                "reference_longitude": float(self.ui.refLonSpinBox.value()),
                "reference_altitude": float(self.ui.refAltSpinBox.value()),
            }

            # Write to CSV file
            with open(file_path, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=grid_config.keys())
                writer.writeheader()
                writer.writerow(grid_config)

            # Update tracking so the status label turns green
            self._g1_original_grid_config = grid_config.copy()
            self._g1_loaded_file_path = file_path

            # Show success message
            QtWidgets.QMessageBox.information(
                self,
                "Success",
                f"Grid configuration saved successfully to:\n{file_path}",
            )

            # Update status label to reflect saved state
            self._update_grid_status_label()

        except Exception as e:
            logger.error(f"Failed to save grid configuration: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(
                self, "Error", f"Failed to save grid configuration:\n{str(e)}"
            )

    def update_file(self, file_path: str = None) -> None:
        """
        Update the grid file with the current grid configuration.

        If no file_path is provided, tries to get it from the gridSourceFilePath widget.
        If that's also empty, opens a file dialog for the user to select a file.

        Supports:
        - CSV files: Updates the grid configuration values
        - OpenALAQS files: Updates grid parameters in study_setup and grid_3d_definition tables

        Args:
            file_path (str, optional): Path to the grid file to update. If None, uses gridSourceFilePath widget.
        """
        try:
            # If no file_path provided, try to get it from the widget
            if not file_path:
                file_path = self.ui.gridSourceFilePath.filePath()

            # If still no file, open a dialog for the user to select one
            if not file_path:
                file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                    self,
                    "Select Grid File to Update (CSV or OpenALAQS)",
                    "",
                    "Grid Files (*.csv *.alaqs);;CSV Files (*.csv);;OpenALAQS Files (*.alaqs);;All Files (*)",
                )

                if not file_path:
                    # User cancelled the dialog
                    return

                # Update the gridSourceFilePath widget with the selected file
                self.ui.gridSourceFilePath.setFilePath(file_path)

            # Verify file exists
            if not os.path.isfile(file_path):
                QtWidgets.QMessageBox.warning(
                    self,
                    "File Not Found",
                    f"The selected file does not exist:\n{file_path}",
                )
                return

            # Get grid values from UI spinboxes
            grid_config = {
                "x_cells": int(self.ui.xCellsSpinBox.value()),
                "y_cells": int(self.ui.yCellsSpinBox.value()),
                "z_cells": int(self.ui.zCellsSpinBox.value()),
                "x_resolution": float(self.ui.xResolutionSpinBox.value()),
                "y_resolution": float(self.ui.yResolutionSpinBox.value()),
                "z_resolution": float(self.ui.zResolutionSpinBox.value()),
                "reference_latitude": float(self.ui.refLatSpinBox.value()),
                "reference_longitude": float(self.ui.refLonSpinBox.value()),
                "reference_altitude": float(self.ui.refAltSpinBox.value()),
            }

            # Determine file type and update accordingly
            if file_path.endswith(".csv"):
                # Update CSV file
                with open(file_path, "w", newline="") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=grid_config.keys())
                    writer.writeheader()
                    writer.writerow(grid_config)

                # Update tracking so the status label turns green
                self._g1_original_grid_config = grid_config.copy()
                self._g1_loaded_file_path = file_path
                self._update_grid_status_label()

                QtWidgets.QMessageBox.information(
                    self,
                    "Success",
                    f"Grid configuration updated successfully in:\n{file_path}",
                )

            elif file_path.endswith(".alaqs"):
                # Update grid parameters directly in the OpenALAQS database
                try:
                    conn = sqlite3.connect(file_path)
                    cursor = conn.cursor()

                    cursor.execute(
                        "UPDATE user_study_setup SET airport_elevation = ?",
                        (grid_config["reference_altitude"],),
                    )

                    cursor.execute(
                        """UPDATE grid_3d_definition
                           SET x_cells = ?,
                               y_cells = ?,
                               z_cells = ?,
                               x_resolution = ?,
                               y_resolution = ?,
                               z_resolution = ?,
                               reference_latitude = ?,
                               reference_longitude = ?""",
                        (
                            grid_config["x_cells"],
                            grid_config["y_cells"],
                            grid_config["z_cells"],
                            grid_config["x_resolution"],
                            grid_config["y_resolution"],
                            grid_config["z_resolution"],
                            grid_config["reference_latitude"],
                            grid_config["reference_longitude"],
                        ),
                    )

                    conn.commit()
                    conn.close()

                    # Update tracking so the status label turns green
                    self._g1_original_grid_config = grid_config.copy()
                    self._g1_loaded_file_path = file_path
                    self._update_grid_status_label()

                    QtWidgets.QMessageBox.information(
                        self,
                        "Success",
                        f"Grid parameters updated successfully in:\n{file_path}",
                    )

                except sqlite3.Error as db_err:
                    QtWidgets.QMessageBox.critical(
                        self,
                        "Database Error",
                        f"Failed to update OpenALAQS database file:\n{str(db_err)}",
                    )
                    return

            else:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Invalid File Type",
                    f"File must be either .csv or .alaqs format.\n"
                    f"Selected file: {os.path.basename(file_path)}",
                )
                return

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Error", f"Failed to update grid configuration file:\n{str(e)}"
            )

    def resetConcentrationCalculationConfiguration(self, config=None):
        if config is None:
            config = {}

        # Note: Configuration stack widget not available in new simplified UI
        # The old stacked widget architecture has been replaced with direct controls
        # This method is kept for compatibility but doesn't do anything

    def getOutputModulesConfiguration(self):
        # Note: Output modules tab widget not available in new simplified UI
        return {}

    def ShowNotice(self):
        QtWidgets.QMessageBox.information(self, "Notice", "Feature not ready")

    def runOutputModule(self, name):

        try:
            # select output file to load - use the same path as AUSTAL uses
            concentration_path = str(self._get_austal_work_directory())
            if os.path.exists(concentration_path):

                if self._conc_calculation_ is None:
                    raise Exception(
                        "No emission calculation loaded. Please load an OpenALAQS file first."
                    )

                if self._conc_calculation_.get3DGrid() is None:
                    raise Exception("No 3DGrid found.")

                OutputModule = OutputDispersionModuleRegistry().get_module(name)
                if OutputModule is None:
                    logger.error("Did not find module '%s'" % (name))
                    return

                gui_modules_config_ = self.getOutputModulesConfiguration()

                # Read UI values (ensure QDateTime transforms to python datetime)
                if hasattr(self.ui, "startDtEdit"):
                    qdt = self.ui.startDtEdit.dateTime()
                    start_dt = datetime(
                        qdt.date().year(),
                        qdt.date().month(),
                        qdt.date().day(),
                        qdt.time().hour(),
                        qdt.time().minute(),
                        qdt.time().second(),
                    )
                else:
                    start_dt = datetime(2023, 3, 1, 0, 0)

                if hasattr(self.ui, "endDtEdit"):
                    qdt = self.ui.endDtEdit.dateTime()
                    end_dt = datetime(
                        qdt.date().year(),
                        qdt.date().month(),
                        qdt.date().day(),
                        qdt.time().hour(),
                        qdt.time().minute(),
                        qdt.time().second(),
                    )
                else:
                    end_dt = datetime(2023, 3, 1, 23, 0)

                # Extract pollutant from UI and normalize to internal code.
                # Display label -> internal code (e.g. 'PM2.5' -> 'p2').
                pollutant_text = (
                    self.ui.resultPollutantCombo.currentText()
                    if hasattr(self.ui, "resultPollutantCombo")
                    else None
                )
                # UI display string to internal pollutant code mapping.
                pollutant_map = {
                    "NOx": "nox",
                    "CO": "co",
                    "HC": "hc",
                    "PM10": "pm10",
                    "SOx": "sox",
                    "CO2": "co2",
                }
                pollutant = None
                if pollutant_text:
                    pollutant = pollutant_map.get(
                        pollutant_text, pollutant_text.lower()
                    )
                is_uncertainty = (
                    self.ui.uncertaintyCheckBox.isChecked()
                    if hasattr(self.ui, "uncertaintyCheckBox")
                    else False
                )
                averaging = (
                    self.ui.averagingCombo.currentText()
                    if hasattr(self.ui, "averagingCombo")
                    else None
                )

                # Initialize widget with UI values for consistent config parsing.
                self._concentration_visualization_widget.init_values(
                    {
                        "start_dt_inclusive": start_dt,
                        "end_dt_inclusive": end_dt,
                        "averaging": averaging,
                        "pollutant": pollutant,
                        "is_uncertainty_enabled": is_uncertainty,
                    }
                )

                # Read final configuration from widget after initialization.
                conc_configuration = (
                    self._concentration_visualization_widget.get_values()
                )
                pollutant_ = conc_configuration.get("pollutant", pollutant)
                averaging_period_ = conc_configuration.get("averaging", averaging)
                check_std = conc_configuration.get(
                    "is_uncertainty_enabled", is_uncertainty
                )

                # Use the visualization grid from Grid Management if one has
                # been loaded; otherwise fall back to the default grid stored
                # in the concentration calculation object.
                if self._visualization_grid_config:
                    active_grid = Grid3D(
                        db_path=self._conc_calculation_.getDatabasePath(),
                        grid_config=self._visualization_grid_config,
                        deserialize=False,
                    )
                else:
                    active_grid = self._conc_calculation_.get3DGrid()

                # Build output module config from UI values and widget configuration.
                config = {
                    "parent": self,
                    "pollutant": pollutant_,
                    "title": "Mean concentration of '%s'" % pollutant_,
                    "ytitle": "%s" % pollutant_,
                    "grid": active_grid,
                    "database_path": self._conc_calculation_.getDatabasePath(),
                    "concentration_path": concentration_path,
                    "averaging_period": averaging_period_,
                    "timeseries": self.getTimeSeries(
                        self._conc_calculation_.getDatabasePath()
                    ),
                    # Disable optional module features by default.
                    "is_plotting_daily_max_enabled": False,
                    "is_csv_output_enabled": False,
                    "is_daily_maximum_enabled": False,
                    "use_centroid_symbol": False,
                    "should_add_labels": False,
                    "should_add_title": False,
                    "3DVisualization": False,
                    "name_suffix": "",
                    "threshold": 0.0001,
                    "check_uncertainty": check_std,
                }

                config.update(conc_configuration)

                # Force Python datetime objects into config
                # ModuleConfigurationWidget returns QDateTime as ISO strings and override to prevent type mismatch in module comparisons
                try:
                    config["start_dt_inclusive"] = start_dt
                    config["end_dt_inclusive"] = end_dt
                except Exception:
                    # fallback: leave whatever was provided
                    pass

                if OutputModule.getModuleDisplayName() in gui_modules_config_:
                    config.update(
                        gui_modules_config_[OutputModule.getModuleDisplayName()]
                    )

                output_module = OutputModule(values_dict=config)

                # Execute the output module
                output_module.beginJob()
                output_module.process()
                res = output_module.endJob()

                if isinstance(res, QtWidgets.QDialog):
                    res.show()
                elif isinstance(res, QgsMapLayer):
                    # Replace existing layers with same name...
                    for layer in self._iface.mapCanvas().layers():
                        if layer.name() == res.name():
                            QgsProject.instance().removeMapLayers([layer.id()])
                    # and add the vector layer to the existing QGIS layers
                    QgsProject.instance().addMapLayers([res])
                    # automatically zoom to new layer
                    self._iface.mapCanvas().setExtent(res.extent())

                    # add coordinate-references system
                    if res.crs() is not None:
                        self._iface.mapCanvas().mapSettings().setDestinationCrs(
                            res.crs()
                        )

                    if name == "ConcentrationsQGISVectorLayerOutputModule":
                        # add text to graphics renderer
                        addTitleToLayer = gui_modules_config_.get("Add title", False)

                        if addTitleToLayer:
                            textItem = QgsTextAnnotation(self._iface.mapCanvas())
                            textItem.setHasFixedMapPosition(False)

                            concentration = output_module.getTotalConcentration()

                            text = QtGui.QTextDocument(
                                "%s Concentration (%.1f kg)\n%s - %s"
                                % (
                                    str(output_module.getPollutant()),
                                    round(concentration, 1),
                                    str(output_module.getTimeStart()),
                                    str(output_module.getTimeEnd()),
                                )
                            )

                            text.setDefaultFont(QtGui.QFont("Arial", 12))
                            textItem.setDocument(text)
                            textItem.setFrameSize(QtCore.QSizeF(500, 48))
                            textItem.setFrameOffsetFromReferencePoint(
                                QtCore.QPointF(20, 75)
                            )
                            # textItem.setFrameBorderWidth(0.0)
                            # textItem.setFrameColor(QColor("white"))

                            self._iface.mapCanvas().scene().addItem(textItem)

            else:
                logger.error("Path not found <%s>" % (concentration_path))

        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Error",
                "Could not execute runOutputModule: %s (error: %s)" % (name, e),
            )
            # Don't re-raise: that triggers QGIS's own Python traceback
            # popup, giving the user two error windows for the same
            # condition. The single dialog above is enough; the full
            # traceback is written to the QGIS message log (View > Panels
            # > Log Messages > "open_alaqs") for developer debugging.
            logger.error(
                "runOutputModule(%s) failed: %s",
                name,
                e,
                exc_info=True,
            )

    def _setup_averaging_options(self):
        """Configure the averaging combo box.

        All four options (annual / daily / hourly / 8-hours) are
        selectable. The reading path (`getA2KData` in
        ConcentrationsQGISVectorLayerOutputModule and
        TableViewDispersionOutputModule) handles each by reading the
        appropriate AUSTAL output file:
            - annual mean → <pol>-y00a.dmna
            - daily / hourly / 8-hours → consecutive <pol>-NNNa.dmna
              files, aggregated client-side over the selected period.

        For non-annual options to actually have files to read, AUSTAL
        must have been run with the NOTALUFT option (Section 2 →
        "Output Mode: Per-hour series" checkbox). Without NOTALUFT,
        only the annual mean file exists; selecting another averaging
        will hit "File X doesn't exist" warnings.
        """
        try:
            averaging_combo = (
                self.ui.averagingCombo if hasattr(self.ui, "averagingCombo") else None
            )

            if averaging_combo and isinstance(averaging_combo, QtWidgets.QComboBox):
                model = averaging_combo.model()
                # Re-enable every item (clear any prior disable from older builds)
                for i in range(averaging_combo.count()):
                    item = model.item(i)
                    if item:
                        item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsEnabled)
                        item.setForeground(QtGui.QColor(0, 0, 0))
                        item.setToolTip("")

                # Default to annual mean as the initial pick (still the
                # most reliable option until os=Hourly/Daily are wired
                # into the AUSTAL run-time config).
                annual_mean_index = averaging_combo.findText("annual mean")
                if annual_mean_index >= 0 and averaging_combo.currentIndex() < 0:
                    averaging_combo.setCurrentIndex(annual_mean_index)

                logger.debug("Averaging options enabled (all four selectable).")
            else:
                logger.warning("Could not find averagingCombo in UI")

        except Exception as e:
            logger.warning(f"Could not setup averaging options: {e}", exc_info=True)
