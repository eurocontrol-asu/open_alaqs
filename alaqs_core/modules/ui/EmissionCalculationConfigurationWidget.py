import os
from collections import OrderedDict

import geopandas as gpd
from PyQt5 import QtCore, QtWidgets

from open_alaqs.alaqs_core.modules.ui.ModuleConfigurationWidget import \
    ModuleConfigurationWidget
from open_alaqs.alaqs_core.tools import CSVInterface


# Configuration (widget) of emissions calculation
class EmissionCalculationConfigurationWidget(ModuleConfigurationWidget):
    def __init__(self, parent=None, config=None):
        if config is None:
            config = {}

        ModuleConfigurationWidget.__init__(self, config_dict=OrderedDict([
            ("Start (incl.)", QtWidgets.QDateTimeEdit),
            ("End (incl.)", QtWidgets.QDateTimeEdit),
            ("Method", QtWidgets.QComboBox),
            ("Source Dynamics", QtWidgets.QComboBox),
            ("Apply NOx corrections", QtWidgets.QCheckBox),
            ("Vertical limit [m]", QtWidgets.QLineEdit),
            ("Receptor Points (*.csv)", QtWidgets.QHBoxLayout),
        ]), parent=parent)

        self.getSettings()["Vertical limit [m]"].setFixedWidth(60)

        self._receptor_points = gpd.GeoDataFrame()

        self._receptors_filename_field = QtWidgets.QLineEdit()
        self._receptors_filename_field.setFixedWidth(150)
        self._receptors_filename_field.setToolTip("Select CSV file with "
                                                  "receptor points")

        self._receptors_filename_browse = QtWidgets.QPushButton("Load File")
        self._receptors_filename_browse.clicked.connect(self.load_receptors_csv)

        self.getSettings()["Receptor Points (*.csv)"].addWidget(
            self._receptors_filename_field)
        self.getSettings()["Receptor Points (*.csv)"].addWidget(
            self._receptors_filename_browse)
        self.getSettings()["Receptor Points (*.csv)"].addStretch()

        self.initValues({
            "Start (incl.)": config.get("Start (incl.)",
                                        "2000-01-01 00:00:00"),
            "End (incl.)": config.get("End (incl.)", "2000-01-02 00:00:00"),
            "Method": {
                "available": [],
                "selected": None},
            "Source Dynamics": {
                "available": ["none", "default", "smooth & shift"],
                "selected": None},
            "Apply NOx corrections": False,
            "Vertical limit [m]": 914.4,
        })

    def load_receptors_csv(self):
        filename, _filter = \
            QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Select file with receptor points",
                "",
                'CSV (*.csv)')
        try:
            if os.path.exists(filename):
                self._receptors_filename_field.setText(filename)
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
                self.get_receptors_from_csv(filename)
                QtWidgets.QApplication.restoreOverrideCursor()
                # if isinstance(result, str):
                #     raise Exception()
            else:
                raise Exception("File does not exists.")
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "Error", "Could not open receptors file:  %s." % e)
            return e

    def get_receptors_from_csv(self, filename_):
        csv_gdf = CSVInterface.readCSVtoGeoDataFrame(filename_)
        self._receptor_points = csv_gdf
