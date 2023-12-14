import os
from collections import OrderedDict

import geopandas as gpd

from PyQt5 import QtCore, QtWidgets
from qgis.gui import QgsFileWidget, QgsDoubleSpinBox

from open_alaqs.alaqs_core.modules.ModuleConfigurationWidget import ModuleConfigurationWidget
from open_alaqs.alaqs_core.tools.csv_interface import read_csv_to_geodataframe


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
            ("Vertical limit", QgsDoubleSpinBox),
            ("Receptor Points (*.csv)", QtWidgets.QHBoxLayout),
        ]), parent=parent)

        self.getSettings()["Vertical limit"].setSuffix(' m')

        self._receptor_points = gpd.GeoDataFrame()

        self._receptors_filename_field = QgsFileWidget()
        self._receptors_filename_field.setFilter('CSV (*.csv)')
        self._receptors_filename_field.setDialogTitle('Select CSV File with Receptor Points')
        self._receptors_filename_field.fileChanged.connect(self.load_receptors_csv)

        self.getSettings()["Receptor Points (*.csv)"].addWidget(self._receptors_filename_field)

        self.initValues({
            "Start (incl.)": config.get("Start (incl.)", "2000-01-01 00:00:00"),
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

    def load_receptors_csv(self, path):
        try:
            if os.path.exists(path):
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
                self.get_receptors_from_csv(path)
                QtWidgets.QApplication.restoreOverrideCursor()
                # if isinstance(result, str):
                #     raise Exception()
            else:
                raise Exception("File does not exists.")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", "Could not open receptors file:  %s." % e)
            return e

    def get_receptors_from_csv(self, filename_):
        csv_gdf = read_csv_to_geodataframe(filename_)
        self._receptor_points = csv_gdf
