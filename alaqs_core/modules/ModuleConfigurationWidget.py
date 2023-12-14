from collections import OrderedDict
from datetime import datetime

from PyQt5 import QtCore, QtWidgets
from qgis.gui import QgsDoubleSpinBox, QgsSpinBox

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.tools import conversion

logger = get_logger(__name__)


class ModuleConfigurationWidget(QtWidgets.QWidget):
    """
    This class provides a widget for module configuration
    """

    def __init__(self, config_dict=None, parent=None):
        if config_dict is None:
            config_dict = {}
        super(QtWidgets.QWidget, self).__init__(parent)

        if parent is not None:
            self.setParent(parent)

        # Layout
        self.setLayout(QtWidgets.QFormLayout())

        # Settings
        self._settings = OrderedDict()
        for key, widget_type in config_dict.items():
            self.addSetting(key, widget_type)
        self._qtdateformat = "yyyy-MM-dd HH:mm:ss"
        self._pydateformat = "%Y-%m-%d %H:%M:%S"

    def addSetting(self, name, widget_type):
        self._settings[name] = widget_type()
        label = QtWidgets.QLabel("%s: " % name)

        if isinstance(self._settings[name], QtWidgets.QDateTimeEdit):
            self._settings[name].setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        elif isinstance(self._settings[name], QtWidgets.QAbstractButton):
            self._settings[name].setText(name)
            label = None

        if label:
            self.layout().insertRow(-1, label,
                                    self._settings[name])
        else:
            self.layout().insertRow(-1, self._settings[name])

    def getSettings(self):
        return self._settings

    def getValues(self):
        values_ = {}
        for name, widget in self._settings.items():
            val_ = None
            if isinstance(widget, QtWidgets.QLabel):
                val_ = widget.text()
            elif isinstance(widget, QtWidgets.QLineEdit):
                val_ = widget.text()
            elif isinstance(widget, QtWidgets.QAbstractButton):
                val_ = widget.isChecked()
            elif isinstance(widget, QtWidgets.QDateTimeEdit):
                val_ = conversion.convertSecondsToTimeString(
                    conversion.convertTimeToSeconds(
                        widget.dateTime().toPyDateTime(),
                        self._pydateformat
                    ), self._pydateformat)
            elif isinstance(widget, QtWidgets.QComboBox):
                val_ = {
                    "available": [widget.itemText(i_) for i_ in
                                  range(widget.count())],
                    "selected": widget.currentText()
                }
            elif isinstance(widget, QtWidgets.QTableWidget):
                val_ = {}
                for col in range(widget.columnCount()):
                    for row in range(widget.rowCount()):
                        val_[row, col] = widget.item(row, col).text() if (
                                widget.item(row, col) is not None) else None
            elif isinstance(widget, QgsDoubleSpinBox) or \
                     isinstance(widget, QgsSpinBox):
                val = widget.value()

            elif isinstance(widget, QtWidgets.QHBoxLayout) or \
                    isinstance(widget, QtWidgets.QVBoxLayout):
                continue

            else:
                logger.error("Did not find method to read values from widget of"
                             " type '%s'!" % (type(widget)))

            values_[name] = val_
        return values_

    def initValues(self, default):
        for name, value in default.items():
            if name in self._settings:
                widget = self._settings[name]
                if isinstance(widget, QtWidgets.QLabel):
                    widget.setText(str(value))
                elif isinstance(widget, QtWidgets.QLineEdit):
                    widget.setText(str(value))
                elif isinstance(widget, QtWidgets.QAbstractButton):
                    widget.setChecked(value)
                elif isinstance(widget, QtWidgets.QComboBox):
                    widget.clear()
                    if "available" in value:
                        for v_ in value["available"]:
                            widget.addItem(v_)
                    if "selected" in value:
                        j_ = -1
                        if not value["selected"] is None:
                            j_ = widget.findText(value["selected"])
                        else:
                            if widget.count():
                                j_ = 0
                        widget.setCurrentIndex(j_)
                elif isinstance(widget, QtWidgets.QTableWidget):
                    if "rows" in value and isinstance(value["rows"], int):
                        widget.setRowCount(value["rows"])
                    if "columns" in value and isinstance(value["columns"], int):
                        widget.setColumnCount(value["columns"])
                    if "header" in value and isinstance(value["header"], tuple):
                        widget.setHorizontalHeaderLabels(value["header"])
                        if 'epsg' in value["header"]:
                            widget.setItem(0, value["header"].index('epsg'),
                                           QtWidgets.QTableWidgetItem('4326'))

                    widget.setFixedHeight(55)
                    widget.resizeColumnsToContents()

                elif isinstance(widget, QtWidgets.QHBoxLayout) or \
                        isinstance(widget, QtWidgets.QVBoxLayout):
                    continue

                elif isinstance(widget, QtWidgets.QDateTimeEdit):
                    if isinstance(value, (datetime, QtCore.QDateTime)):
                        widget.setDateTime(value)
                    elif isinstance(value, str):
                        widget.setDateTime(
                            QtCore.QDateTime.fromString(value,
                                                        self._qtdateformat))
                    else:
                        widget.setDateTime(
                            QtCore.QDateTime.fromString(
                                conversion.convertSecondsToTimeString(
                                    conversion.convertTimeToSeconds(value)
                                ), self._qtdateformat))
                elif isinstance(widget, QgsDoubleSpinBox):
                    val = widget.setValue(float(value))
                elif isinstance(widget, QgsSpinBox):
                    val = widget.setValue(int(value))
                else:
                    logger.error("Did not find method to set values to widget "
                                 "of type '%s'.!" % (type(widget)))
            else:
                logger.error("Did not find setting '%s' in internal "
                             "store" % name)
        self.update()
