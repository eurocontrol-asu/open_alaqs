from PyQt5 import QtWidgets

from open_alaqs.alaqs_core import alaqs, alaqsutils

form = None
name_field = None
unit_field = None
height_field = None
heat_flux_field = None
hour_profile_field = None
daily_profile_field = None
month_profile_field = None
co_kg_unit_field = None
hc_kg_unit_field = None
nox_kg_unit_field = None
sox_kg_unit_field = None
pm10_kg_unit_field = None
p1_kg_unit_field = None
p2_kg_unit_field = None
instudy = None


def form_open(my_dialog, layer_id, feature_id):
    global form
    global name_field
    global unit_field
    global height_field
    global heat_flux_field
    global hour_profile_field
    global daily_profile_field
    global month_profile_field
    global co_kg_unit_field
    global hc_kg_unit_field
    global nox_kg_unit_field
    global sox_kg_unit_field
    global pm10_kg_unit_field
    global p1_kg_unit_field
    global p2_kg_unit_field
    global instudy


    form = my_dialog
    name_field = form.findChild(QtWidgets.QLineEdit, "source_id")
    unit_field = form.findChild(QtWidgets.QLineEdit, "unit_year")
    height_field = form.findChild(QtWidgets.QLineEdit, "height")
    heat_flux_field = form.findChild(QtWidgets.QLineEdit, "heat_flux")
    hour_profile_field = form.findChild(QtWidgets.QComboBox, "hourly_profile")
    daily_profile_field = form.findChild(QtWidgets.QComboBox, "daily_profile")
    month_profile_field = form.findChild(QtWidgets.QComboBox, "monthly_profile")
    co_kg_unit_field = form.findChild(QtWidgets.QLineEdit, "co_kg_unit")
    hc_kg_unit_field = form.findChild(QtWidgets.QLineEdit, "hc_kg_unit")
    nox_kg_unit_field = form.findChild(QtWidgets.QLineEdit, "nox_kg_unit")
    sox_kg_unit_field = form.findChild(QtWidgets.QLineEdit, "sox_kg_unit")
    pm10_kg_unit_field = form.findChild(QtWidgets.QLineEdit, "pm10_kg_unit")
    p1_kg_unit_field = form.findChild(QtWidgets.QLineEdit, "p1_kg_unit")
    p2_kg_unit_field = form.findChild(QtWidgets.QLineEdit, "p2_kg_unit")
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
    #     button_box.accepted.disconnect(form.accept)
    # except Exception as e:
    #     pass

    # By default the source is accounted for in the study - Set to 0 to ignore
    # instudy.setChecked(True)
    # QgsEditorWidgetWrapper.fromWidget( instudy ).setValue(1)
    # QgsEditorWidgetWrapper.fromWidget( height_field ).setValue(0)
    # QgsEditorWidgetWrapper.fromWidget( heat_flux_field ).setValue(0)

    height_field.setText('0')
    height_field.setEnabled(False)
    heat_flux_field.setText('0')
    heat_flux_field.setEnabled(False)

    populate_hourly_profiles()
    populate_daily_profiles()
    populate_monthly_profiles()

    name_field.textChanged.connect(lambda: validate(button_box))
    unit_field.textChanged.connect(lambda: validate(button_box))
    height_field.textChanged.connect(lambda: validate(button_box)) 
    co_kg_unit_field.textChanged.connect(lambda: validate(button_box))
    hc_kg_unit_field.textChanged.connect(lambda: validate(button_box))
    nox_kg_unit_field.textChanged.connect(lambda: validate(button_box))
    sox_kg_unit_field.textChanged.connect(lambda: validate(button_box))
    pm10_kg_unit_field.textChanged.connect(lambda: validate(button_box))
    p1_kg_unit_field.textChanged.connect(lambda: validate(button_box))
    p2_kg_unit_field.textChanged.connect(lambda: validate(button_box))
    heat_flux_field.textChanged.connect(lambda: validate(button_box))
    #button_box.accepted.connect(validate)
    # button_box.rejected.connect(form.reject)

def populate_hourly_profiles():
    try:
        hour_profile_field.addItem("default")
        hourly_profiles = alaqs.get_hourly_profiles()
        if (hourly_profiles is None) or (hourly_profiles == []):
            return None
        else:
            for profile in hourly_profiles:
                if profile[1] != "default":
                    hour_profile_field.addItem(profile[1])
            hour_profile_field.setCurrentIndex(0)
            hour_profile_field.setEditable(False)
    except Exception as e:
        error = alaqsutils.print_error(populate_hourly_profiles.__name__, Exception, e)
        return error


def populate_daily_profiles():
    try:
        daily_profile_field.addItem("default")
        daily_profiles = alaqs.get_daily_profiles()
        if (daily_profiles is None) or (daily_profiles == []):
            return None
        else:
            for profile in daily_profiles:
                if profile[1] != "default":
                    daily_profile_field.addItem(profile[1])
            daily_profile_field.setCurrentIndex(0)
            daily_profile_field.setEditable(False)
    except Exception as e:
        error = alaqsutils.print_error(populate_daily_profiles.__name__, Exception, e)
        return error


def populate_monthly_profiles():
    try:
        month_profile_field.addItem("default")
        monthly_profiles = alaqs.get_monthly_profiles()
        if (monthly_profiles is None) or (monthly_profiles == []):
            return None
        else:
            for profile in monthly_profiles:
                if profile[1] != "default":
                    month_profile_field.addItem(profile[1])
            month_profile_field.setCurrentIndex(0)
            month_profile_field.setEditable(False)
    except Exception as e:
        error = alaqsutils.print_error(populate_monthly_profiles.__name__, Exception, e)
        return error


def validate(button_box):
    """
    This function validates that all of the required fields have been completed
    correctly. If they have, the attributes are committed to the feature.
    Otherwise an error message is displayed and the incorrect field is
    highlighted in red.
    """
    results = list()
    results.append(validate_field(name_field, "str"))
    results.append(validate_field(unit_field, "float"))
    results.append(validate_field(height_field, "float"))
    results.append(validate_field(heat_flux_field, "float"))
    results.append(validate_field(co_kg_unit_field, "float"))
    results.append(validate_field(hc_kg_unit_field, "float"))
    results.append(validate_field(nox_kg_unit_field, "float"))
    results.append(validate_field(sox_kg_unit_field, "float"))
    results.append(validate_field(pm10_kg_unit_field, "float"))
    results.append(validate_field(p1_kg_unit_field, "float"))
    results.append(validate_field(p2_kg_unit_field, "float"))

    # if False in results:
    #     msg = QtWidgets.QMessageBox()
    #     msg.setIcon(QtWidgets.QMessageBox.Critical)
    #     msg.setWindowTitle('Validation error')
    #     msg.setText("Please complete all fields.")
    #     # msg.setInformativeText(
    #     #     "It seems that some fields are empty. You need to provide values for all fields in red.")
    #     msg.exec_()
    #     return

    # form.save()

    if not ('False' in str(results)):
        button_box.button(button_box.Ok).blockSignals(False)
        button_box.accepted.connect(form.save)


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