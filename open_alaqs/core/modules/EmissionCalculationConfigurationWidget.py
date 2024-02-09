import os
from collections import OrderedDict

import geopandas as gpd
from qgis.gui import QgsDoubleSpinBox, QgsFileWidget
from qgis.PyQt import Qt, QtWidgets
from qgis.utils import OverrideCursor

from open_alaqs.core.modules.ModuleConfigurationWidget import ModuleConfigurationWidget
from open_alaqs.core.tools.csv_interface import read_csv_to_geodataframe


# Configuration (widget) of emissions calculation
class EmissionCalculationConfigurationWidget(ModuleConfigurationWidget):
    def __init__(self, parent=None, config=None):
        if config is None:
            config = {}

        ModuleConfigurationWidget.__init__(
            self,
            config_dict=OrderedDict(
                [
                    ("Start (incl.)", QtWidgets.QDateTimeEdit),
                    ("End (incl.)", QtWidgets.QDateTimeEdit),
                    ("Method", QtWidgets.QComboBox),
                    ("Apply NOx Corrections", QtWidgets.QCheckBox),
                    ("Source Dynamics", QtWidgets.QComboBox),
                    ("Vertical Limit", QgsDoubleSpinBox),
                    ("Receptor Points", QtWidgets.QHBoxLayout),
                ]
            ),
            parent=parent,
        )

        widget = self.getSettings()["Vertical Limit"]
        widget.setSuffix(" m")
        widget.setMinimum(0.0)
        widget.setMaximum(999999.9)

        self.getSettings()["Apply NOx Corrections"].setToolTip(
            "Only available when the method is set to 'bymode'."
        )

        self._receptor_points = gpd.GeoDataFrame()

        self._receptors_filename_field = QgsFileWidget()
        self._receptors_filename_field.setFilter("CSV (*.csv)")
        self._receptors_filename_field.setDialogTitle(
            "Select CSV File with Receptor Points"
        )
        self._receptors_filename_field.fileChanged.connect(self.load_receptors_csv)

        self.getSettings()["Receptor Points"].addWidget(self._receptors_filename_field)

        self.initValues(
            {
                "Start (incl.)": config.get("Start (incl.)", "2000-01-01 00:00:00"),
                "End (incl.)": config.get("End (incl.)", "2000-01-02 00:00:00"),
                "Method": {"available": [], "selected": None},
                "Source Dynamics": {
                    "available": ["none", "default", "smooth & shift"],
                    "selected": None,
                },
                "Apply NOx Corrections": False,
                "Vertical Limit": 914.4,
            }
        )

    def load_receptors_csv(self, path):
        try:
            if os.path.exists(path):
                with OverrideCursor(Qt.WaitCursor):
                    self.get_receptors_from_csv(path)
                # if isinstance(result, str):
                #     raise Exception()
            else:
                raise Exception("File does not exists.")
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "Error", "Could not open receptors file:  %s." % e
            )
            return e

    def get_receptors_from_csv(self, filename_):
        csv_gdf = read_csv_to_geodataframe(filename_)
        self._receptor_points = csv_gdf
