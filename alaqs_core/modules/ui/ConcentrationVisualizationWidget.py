from __future__ import absolute_import
__author__ = 'ENVISA'

from . import __init__

import sys
import logging
logger = logging.getLogger("alaqs.%s" % (__name__))

# from qgis.PyQt import QtGui, QtWidgets
# from qgis.PyQt import QtCore
from PyQt5 import QtCore, QtGui, QtWidgets
from collections import OrderedDict
from tools import Conversions

from .ModuleConfigurationWidget import ModuleConfigurationWidget

#Configuration (widget) of emissions calculation
class ConcentrationVisualizationWidget(ModuleConfigurationWidget):
    def __init__(self, parent=None, config={}):

        ModuleConfigurationWidget.__init__(self, config_dict = OrderedDict([
                ("uncertainty" , QtWidgets.QCheckBox),
                ("Start (incl.)" , QtWidgets.QDateTimeEdit),
                ("End (incl.)" , QtWidgets.QDateTimeEdit),
                ("Averaging" , QtWidgets.QComboBox),
                ("Pollutant" , QtWidgets.QComboBox)

            ]), parent=parent)

        self.initValues({
            "uncertainty": False,
            "Start (incl.)" : "2000-01-01 00:00:00" if not "Start (incl.)" in config else config["Start (incl.)"],
            "End (incl.)" : "2000-01-02 00:00:00" if not "End (incl.)" in config else config["End (incl.)"],
            "Averaging": {"available": ["hourly", "8-hours mean", "daily mean", "annual mean"], "selected": "annual mean"},
            "Pollutant": {"available": ["CO2", "CO", "HC", "NOx", "SOx", "PM10"], "selected": None}
        })
            # "Apply NOx corrections": False,
            # "Vertical limit [m]": 305

if __name__ == "__main__":
    import alaqslogging

    from qgis.PyQt import QtGui, QtWidgets
    app = QtGui.QApplication(sys.argv)
    configuration_widget = ConcentrationVisualizationWidget()

    import datetime
    cfg = {
        'Start (incl.)': datetime.datetime(2011, 1, 2, 0, 0),
        'End (incl.)': datetime.datetime(2012, 1, 2, 0, 0),
        # "Method" : {"available": ["BFFM2","bymode","matching","linear"], "selected": None}
        # "Vertical limit [m]":304.8
    }

    configuration_widget.initValues(cfg)
    configuration_widget.show()

    sys.exit(app.exec_())


