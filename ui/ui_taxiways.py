from PyQt5 import QtWidgets

form = None
name_field = None
time_field = None
speed_field = None
instudy = None


def form_open(my_dialog, layer_id, feature_id):
    global form
    global name_field
    global time_field
    global speed_field
    global instudy

    form = my_dialog
    name_field = form.findChild(QtWidgets.QLineEdit, "taxiway_id")
    time_field = form.findChild(QtWidgets.QLineEdit, "time")
    speed_field = form.findChild(QtWidgets.QLineEdit, "speed")
    button_box = form.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
    instudy = form.findChild(QtWidgets.QCheckBox, "instudy")

    button_box.button(button_box.Ok).blockSignals(True)

    # #disconnect old-style signals, which are created e.g. by QGIS from the ui file
    # try:
    #     QObject.disconnect(button_box, SIGNAL("accepted()"), form.accept)
    # except Exception as e:
    #     pass
    #disconnect new-style signals
    # try:
    #     #button_box.blockSignals(True)
    #     button_box.accepted.disconnect(form.accept)
    # except Exception as e:
    #     pass
    # button_box.accepted.connect(validate)
    #button_box.rejected.connect(form.resetValues)

    time_field.setText("Calculated")
    time_field.setEnabled(False)

    name_field.textChanged.connect(lambda: validate(button_box))
    speed_field.textChanged.connect(lambda: validate(button_box))


def validate(button_box):
    """
    This function validates that all of the required fields have been completed
    correctly. If they have, the attributes are committed to the feature. 
    Otherwise an error message is displayed and the incorrect field is 
    highlighted in red.
    """
    results = list()
    results.append(validate_field(name_field, "str"))
    results.append(validate_field(speed_field, "float"))
    # if False in results:
    #     QtWidgets.QMessageBox.warning(None, "Validation error", "Please fill in all the required fields")
    #     return False
    # # for value in results:
    # #     if value is False:
    # #         QtWidgets.QMessageBox.warning(None, "Validation error", "Please fill in all the required fields")
    # #         return False

    # form.save()

    if not ('False' in str(results)):
        button_box.button(button_box.Ok).blockSignals(False)
        button_box.accepted.connect(form.save)
    else:
        button_box.button(button_box.Ok).blockSignals(True)

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
    elif color is "green":
        ui_element.setStyleSheet("background-color: rgba(0,255,0,0.3);")
    else:
        pass