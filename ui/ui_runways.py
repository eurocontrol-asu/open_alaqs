from PyQt5 import QtWidgets

form = None
first_runway_number = None
first_runway_letter = None
second_runway_number = None
second_runway_number = None
number_field = None
suffix_field = None
capacity_field = None
name_field = None
offset_field = None
time_field = None
speed_field = None
instudy = None


def form_open(my_dialog, layer_id, feature_id):
    global form
    global first_runway_letter
    global first_runway_number
    global second_runway_letter
    global second_runway_number
    global number_field
    global suffix_field
    global name_field
    global capacity_field
    global offset_field
    global time_field
    global speed_field
    global instudy

    form = my_dialog
    first_runway_number = form.findChild(QtWidgets.QComboBox, "first_runway_number")
    first_runway_letter = form.findChild(QtWidgets.QComboBox, "first_runway_letter")
    second_runway_number = form.findChild(QtWidgets.QComboBox, "second_runway_number")
    second_runway_letter = form.findChild(QtWidgets.QComboBox, "second_runway_letter")

    number_field = form.findChild(QtWidgets.QComboBox, "number")
    suffix_field = form.findChild(QtWidgets.QComboBox, "suffix")
    name_field = form.findChild(QtWidgets.QLineEdit, "runway_id")
    capacity_field = form.findChild(QtWidgets.QLineEdit, "capacity")
    offset_field = form.findChild(QtWidgets.QLineEdit, "touchdown")
    speed_field = form.findChild(QtWidgets.QLineEdit, "max_queue_speed")
    time_field = form.findChild(QtWidgets.QLineEdit, "peak_queue_time")
    button_box = form.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
    instudy = form.findChild(QtWidgets.QCheckBox, "instudy")

    button_box.button(button_box.Ok).blockSignals(True)

    first_runway_number.currentIndexChanged['QString'].connect(first_runway_number_changed)
    first_runway_letter.currentIndexChanged['QString'].connect(first_runway_letter_changed)
    name_field.setReadOnly(True)
    second_runway_number.setEnabled(False)
    second_runway_letter.setEnabled(False)

    populate_runway_numbers(second_runway_number)
    populate_runway_numbers(first_runway_number)
    populate_runway_letters(second_runway_letter)
    populate_runway_letters(first_runway_letter)

    first_runway_number_changed()
    first_runway_letter_changed()
    create_runway_id()

    # #disconnect old-style signals, which are created e.g. by QGIS from the ui file
    # try:
    #     QObject.disconnect(button_box, SIGNAL("accepted()"), form.accept)
    # except Exception, e:
    #     pass
    # #disconnect new-style signals
    # try:
    #     button_box.accepted.disconnect(form.accept)
    # except Exception as e:
    #     pass

    # button_box.accepted.connect(validate)
    #button_box.rejected.connect(form.reject)

    #QgsEditorWidgetWrapper.fromWidget( instudy ).setValue(1)

    name_field.textChanged.connect(lambda: validate(button_box))
    capacity_field.textChanged.connect(lambda: validate(button_box))
    offset_field.textChanged.connect(lambda: validate(button_box))
    speed_field.textChanged.connect(lambda: validate(button_box))
    time_field.textChanged.connect(lambda: validate(button_box))


def populate_runway_numbers(combobox_object):
    for i in range(1, 37):
        combobox_object.addItem("%02d" % i)


def populate_runway_letters(combobox_object):
    combobox_object.addItem("")
    combobox_object.addItem("L")
    combobox_object.addItem("R")
    combobox_object.addItem("C")

def first_runway_number_changed():
    # Get the current number
    first_runway_number_value = int(first_runway_number.currentText())
    # Calculate the opposite
    if first_runway_number_value <= 18:
        second_runway_number_value = first_runway_number_value + 18
    else:
        second_runway_number_value = first_runway_number_value - 18
    # Update the second number
    index = second_runway_number.findText("%02d" % second_runway_number_value)
    second_runway_number.setCurrentIndex(index)
    create_runway_id()


def first_runway_letter_changed():
    # Get the current letter
    first_runway_letter_value = str(first_runway_letter.currentText())
    # Calculate the opposite
    second_runway_letter_value = ""

    if first_runway_letter_value == "L":
        second_runway_letter_value = "R"
    elif first_runway_letter_value == "R":
        second_runway_letter_value = "L"
    elif first_runway_letter_value == "":
        second_runway_letter_value = ""
    elif first_runway_letter_value == "C":
        second_runway_letter_value = "C"

    # Update the second letter
    index = second_runway_letter.findText(second_runway_letter_value)
    second_runway_letter.setCurrentIndex(index)
    create_runway_id()


def create_runway_id():
    runway_string = "%s%s/%s%s" % (first_runway_number.currentText(), first_runway_letter.currentText(),
                                   second_runway_number.currentText(), second_runway_letter.currentText())
    name_field.setText(runway_string)


def validate(button_box):
    """
    This function validates that all of the required fields have been completed
    correctly. If they have, the attributes are committed to the feature. 
    Otherwise an error message is displayed and the incorrect field is 
    highlighted in red.
    """
    results = list()
    results.append(validate_field(name_field, "str"))
    results.append(validate_field(capacity_field, "float"))
    results.append(validate_field(offset_field, "float"))
    results.append(validate_field(speed_field, "float"))
    results.append(validate_field(time_field, "float"))

    # for value in results:
    #     if value is False:
    #         msg = QtWidgets.QMessageBox()
    #         msg.setIcon(QtWidgets.QMessageBox.Critical)
    #         msg.setWindowTitle('Validation error')
    #         msg.setText("Please complete all fields.")
    #         # msg.setInformativeText(
    #         #     "It seems that some fields are empty. You need to provide values for all fields in red.")
    #         msg.exec_()
    #         # QtWidgets.QMessageBox().warning(form, "Error", "Please complete all fields", QtWidgets.QMessageBox.Cancel)
    #         return

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
    else:
        pass