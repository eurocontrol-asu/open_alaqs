from collections import OrderedDict

from PyQt5 import QtWidgets

from open_alaqs.alaqs_core.modules.ModuleConfigurationWidget import (
    ModuleConfigurationWidget,
)


# Configuration (widget) of emissions calculation
class ConcentrationVisualizationWidget(ModuleConfigurationWidget):
    def __init__(self, parent=None, config=None):
        if config is None:
            config = {}
        ModuleConfigurationWidget.__init__(
            self,
            config_dict=OrderedDict(
                [
                    ("Start (incl.)", QtWidgets.QDateTimeEdit),
                    ("End (incl.)", QtWidgets.QDateTimeEdit),
                    ("Averaging", QtWidgets.QComboBox),
                    ("Pollutant", QtWidgets.QComboBox),
                    ("Enable Uncertainty", QtWidgets.QCheckBox),
                ]
            ),
            parent=parent,
        )

        self.initValues(
            {
                "Enable Uncertainty": False,
                "Start (incl.)": config.get("Start (incl.)", "2000-01-01 00:00:00"),
                "End (incl.)": config.get("End (incl.)", "2000-01-02 00:00:00"),
                "Averaging": {
                    "available": [
                        "hourly",
                        "8-hours mean",
                        "daily mean",
                        "annual mean",
                    ],
                    "selected": "annual mean",
                },
                "Pollutant": {
                    "available": ["CO2", "CO", "HC", "NOx", "SOx", "PM10"],
                    "selected": None,
                },
            }
        )
