from PyQt5 import QtCore, QtGui, QtWidgets
from qgis.gui import QgsEditorWidgetWrapper

import alaqs

form = None
name_field = None
runway_field = None
arrdep_field = None
instudy = None

def form_open(my_dialog, layer_id, feature_id):
    global form
    global name_field
    global runway_field
    global arrdep_field
    global instudy

    form = my_dialog
    name_field = form.findChild(QtWidgets.QLineEdit, "track_id")
    runway_field = form.findChild(QtWidgets.QComboBox, "runway")
    arrdep_field = form.findChild(QtWidgets.QComboBox, "departure_arrival")
    button_box = form.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
    instudy = form.findChild(QtWidgets.QCheckBox, "instudy")

    populate_combo_boxes()
    
    # #disconnect old-style signals, which are created e.g. by QGIS from the ui file
    # try:
    #     QObject.disconnect(button_box, SIGNAL("accepted()"), form.accept)
    # except Exception, e:
    #     pass
    #disconnect new-style signals
    try:
        button_box.accepted.disconnect(form.accept)
    except Exception, e:
        pass

    button_box.accepted.connect(validate)
    # button_box.rejected.connect(form.reject)
    # QgsEditorWidgetWrapper.fromWidget( instudy ).setValue(1)

    # arrdep_field.addItem("Arrival")
    # arrdep_field.addItem("Departure")

def populate_combo_boxes():
    arrdep_field.addItem("Arrival")
    arrdep_field.addItem("Departure")

    runways = alaqs.get_runways()
    if runways is None or runways == []:
        msg_box = QtWidgets.QMessageBox()
        msg.setIcon(QtWidgets.QMessageBox.Critical)
        msg.setWindowTitle('Critical error')
        msg_box.setText("Please define your runways before creating tracks.")
        msg_box.exec_()
    else:
        for runway in runways:
            directions = runway[0].split("-")
            for direction in directions:
                runway_field.addItem(direction.strip())
    runway_field.setEditable(False)


def validate():
    """
    This function validates that all of the required fields have been completed
    correctly. If they have, the attributes are committed to the feature. 
    Otherwise an error message is displayed and the incorrect field is 
    highlighted in red.
    """
    results = list()
    results.append(validate_field(name_field, "str"))
    results.append(validate_field(runway_field, "str"))
    results.append(validate_field(arrdep_field, "str"))

    if False in results:
        msg = QtWidgets.QMessageBox()
        msg.setIcon(QtWidgets.QMessageBox.Critical)
        msg.setWindowTitle('Validation error')
        msg.setText("Please complete all fields.")
        # msg.setInformativeText(
        #     "It seems that some fields are empty. You need to provide values for all fields in red.")
        msg.exec_()
        return

    form.save()


def validate_field(ui_element, var_type):
    try:
        if var_type is "str":
            try:
                value = str(ui_element.currentText()).strip()
            except:
                value = str(ui_element.text()).strip()
            if value is "":
                color_ui_background(ui_element, "red")
                ui_element.setToolTip("This value should be a string")
                return False
            else:
                color_ui_background(ui_element, "white")
                return value

        elif var_type is "int":
            try:
                value = str(ui_element.currentText()).strip()
            except:
                value = str(ui_element.text()).strip()
            try:
                if value == "" or value is None:
                    raise Exception()
                value = int(value)
                color_ui_background(ui_element, "white")
                return value
            except:
                color_ui_background(ui_element, "red")
                ui_element.setToolTip("This value should be an integer")
                return False

        elif var_type is "float":
            try:
                value = str(ui_element.currentText()).strip()
            except:
                value = str(ui_element.text()).strip()
            try:
                if value == "" or value is None:
                    raise Exception()
                value = float(value)
                color_ui_background(ui_element, "white")
                return value
            except:
                color_ui_background(ui_element, "red")
                ui_element.setToolTip("This value should be a float")
                return False
    except:
        return False


def color_ui_background(ui_element, color):
    if color is "red":
        ui_element.setStyleSheet("background-color: rgba(255, 107, 107, 150);")
    elif color is "white":
        ui_element.setStyleSheet("background-color: rgba(255, 255, 255, 255);")
    else:
        pass