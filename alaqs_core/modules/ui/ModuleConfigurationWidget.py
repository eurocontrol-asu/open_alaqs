from __future__ import absolute_import
from builtins import str
from builtins import range
__author__ = 'ENVISA'

try:
    from . import __init__
except:
    import __init__
import sys
import logging
logger = logging.getLogger("alaqs.%s" % (__name__))

# from qgis.PyQt import QtGui, QtCore, QtWidgets
from PyQt5 import QtCore, QtGui, QtWidgets

from collections import OrderedDict
from tools import Conversions

class ModuleConfigurationWidget(QtWidgets.QWidget):
    """
    This class provides a widget for module configuration
    """

    def __init__(self, config_dict={}, parent=None):
        super(QtWidgets.QWidget, self).__init__(parent)

        if not parent is None:
            self.setParent(parent)

        #Layout
        self.setLayout(QtWidgets.QFormLayout())

        #Settings
        self._settings = OrderedDict()
        for key, widget_type in config_dict.items():
            self.addSetting(key, widget_type)
        self._qtdateformat = "yyyy-MM-dd HH:mm:ss"
        self._pydateformat = "%Y-%m-%d %H:%M:%S"

    def addSetting(self, name, widget_type):
        self._settings[name] = widget_type()
        if isinstance(self._settings[name], QtWidgets.QDateTimeEdit):
            self._settings[name].setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        #insert new row at the end of the QFormLayout
        self.layout().insertRow(-1, QtWidgets.QLabel("%s: " % (name)), self._settings[name])

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
                val_ = Conversions.convertSecondsToTimeString(Conversions.convertTimeToSeconds(widget.dateTime().toPyDateTime(), self._pydateformat), self._pydateformat)
            elif isinstance(widget, QtWidgets.QComboBox):
                val_ = {
                    "available":[widget.itemText(i_) for i_ in range(0, widget.count())],
                    "selected":widget.currentText()
                }
            elif isinstance(widget, QtWidgets.QTableWidget):
                val_ = {}
                for col in range(widget.columnCount()):
                    for row in range(widget.rowCount()):
                        val_[row, col] = widget.item(row, col).text() if not widget.item(row, col) is None else None

            elif isinstance(widget, QtWidgets.QHBoxLayout) or isinstance(widget, QtWidgets.QVBoxLayout):
                continue

            else:
                logger.error("Did not find method to read values from widget of type '%s'!" % (type(widget)))

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
                            widget.setItem(0, value["header"].index('epsg'), QtWidgets.QTableWidgetItem('4326'))

                    widget.setFixedHeight(55)
                    widget.resizeColumnsToContents()

                elif isinstance(widget, QtWidgets.QHBoxLayout) or isinstance(widget, QtWidgets.QVBoxLayout):
                    continue

                elif isinstance(widget, QtWidgets.QDateTimeEdit):
                    if isinstance(value, QtCore.QDateTime):
                        widget.setDateTime(value)
                    elif isinstance(value, str):
                        widget.setDateTime(QtCore.QDateTime.fromString(value, self._qtdateformat))
                    else:
                        widget.setDateTime(QtCore.QDateTime.fromString(Conversions.convertSecondsToTimeString(Conversions.convertTimeToSeconds(value)), self._qtdateformat))
                else:
                    logger.error("Did not find method to set values to widget of type '%s'.!" % (type(widget)))
            else:
                logger.error("Did not find setting '%s' in internal store" % (name))
        self.update()





# if __name__ == "__main__":
#     import alaqslogging
#     import sys
#     from qgis.PyQt.QtWidgets import QApplication, QCompleter, QLineEdit
#
#     def get_data(model):
#         model.setStringList(["completion", "data", "goes", "here"])
#
#     def validate():
#         """
#         This function validates that all of the required fields have been completed correctly. If they have, the attributes
#         are committed to the feature. Otherwise an error message is displayed and the incorrect field is highlighted in red.
#         """
#         results = list()
#
#         results.append(validate_field(name_field, "str"))
#         # results.append(validate_field(type_field, "str"))
#         # results.append(validate_field(height_field, "float"))
#         if False in results:
#             QtWidgets.QMessageBox.warning(configuration_widget, "Error", "Please complete all fields")
#             # configuration_widget.ignore()
#             # msg_box = QtGui.QMessageBox()
#             # msg_box.setIcon(QtGui.QMessageBox.Information)
#             # msg_box.setWindowTitle("Foo")
#             # msg_box.setText("Please complete all values")
#             # msg_box.setStandardButtons(QMessageBox.Ok)
#             # msg_box.exec_()
#             return
#         else:
#             # return
#             configuration_widget.close()
#
#     def validate_field(ui_element, var_type):
#         try:
#             if var_type is "str":
#                 try:
#                     value = str(ui_element.currentText()).strip()
#                 except:
#                     value = str(ui_element.text()).strip()
#                 if value is "":
#                     color_ui_background(ui_element, "red")
#                     ui_element.setToolTip("This value should be a string")
#                     return False
#                 else:
#                     color_ui_background(ui_element, "white")
#                     return value
#
#             elif var_type is "int":
#                 try:
#                     value = str(ui_element.currentText()).strip()
#                 except:
#                     value = str(ui_element.text()).strip()
#                 try:
#                     if value == "" or value is None:
#                         raise Exception()
#                     value = int(value)
#                     color_ui_background(ui_element, "white")
#                     return value
#                 except:
#                     color_ui_background(ui_element, "red")
#                     ui_element.setToolTip("This value should be an integer")
#                     return False
#
#             elif var_type is "float":
#                 try:
#                     value = str(ui_element.currentText()).strip()
#                 except:
#                     value = str(ui_element.text()).strip()
#                 try:
#                     if value == "" or value is None:
#                         raise Exception()
#                     value = float(value)
#                     color_ui_background(ui_element, "white")
#                     return value
#                 except:
#                     color_ui_background(ui_element, "red")
#                     ui_element.setToolTip("This value should be a float")
#                     return False
#         except:
#             return False
#
#
#     def color_ui_background(ui_element, color):
#         if color is "red":
#             ui_element.setStyleSheet("background-color: rgba(255, 107, 107, 150);")
#         elif color is "white":
#             ui_element.setStyleSheet("background-color: rgba(255, 255, 255, 255);")
#         else:
#             pass
#
#     completer = QCompleter()
#
#     app = QApplication(sys.argv)
#     configuration_widget = ModuleConfigurationWidget()
#     configuration_widget.show()
#
#     configuration_widget.setWindowTitle("configuration_widget example")
#
#     configuration_widget.addSetting("A bunch of foo Settings", QtWidgets.QLabel)
#     configuration_widget.addSetting("foo", QtWidgets.QLineEdit)
#     # configuration_widget.addSetting("bar", QtGui.QCheckBox)
#     # configuration_widget.addSetting("foobar", QtGui.QComboBox)
#     # btn = QtGui.QPushButton('Button')
#     # configuration_widget.addSetting("button", QtGui.QPushButton)
#
#     # configuration_widget.adjustSize()
#     name_field = configuration_widget.getSettings()['foo']
#     # name_field.setValidator(QtGui.QIntValidator()) # now edit will only accept integers
#     # connect edit to label
#     # update label each time the text has been edited
#     # foo.textEdited.connect(foo.setText)
#
#     # foo.setCompleter(completer)
#     # model = QStringListModel()
#     # completer.setModel(model)
#     # get_data(model)
#
#     button_box = configuration_widget.getSettings()['button']
#     # button_box.setStyleSheet("background-color: rgba(255, 107, 107, 150);")
#     button_box.clicked.connect(validate)
#     # button_box.rejected.connect(form.reject)
#
#     # validator = QtGui.QDoubleValidator()
#     # foo.setValidator(validator)
#     # foo.textChanged.connect(self.check_state)
#     # foo.textChanged.emit(foo.text())
#
#
#
#     configuration_widget.show()
#     # ---- end of widget test code -----
#     sys.exit(app.exec_())
#
#
#     # app = QApplication(sys.argv)
#     # edit = QLineEdit()
#     # completer = QCompleter()
#     # edit.setCompleter(completer)
#     #
#     # model = QStringListModel()
#     # completer.setModel(model)
#     # get_data(model)
#     #
#     # edit.show()
#     # sys.exit(app.exec_())
#
#
#         # def check_state(self, *args, **kwargs):
#         #     sender = self.sender()
#         #     validator = sender.validator()
#         #     state = validator.validate(sender.text(), 0)[0]
#         #     if state == QtGui.QValidator.Acceptable:
#         #         color = '#c4df9b' # green
#         #     elif state == QtGui.QValidator.Intermediate:
#         #         color = '#fff79a' # yellow
#         #     else:
#         #         color = '#f6989d' # red
#         #     sender.setStyleSheet('QLineEdit { background-color: %s }' % color)