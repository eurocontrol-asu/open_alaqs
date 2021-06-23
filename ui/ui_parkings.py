from PyQt5 import QtCore, QtWidgets

from open_alaqs.alaqs_core import alaqs
from open_alaqs.alaqs_core import alaqsutils
from open_alaqs.alaqs_core.tools.lib_alaqs_method import \
    roadway_emission_factors_alaqs_method

form = None
name_field = None
height_field = None
distance_field = None
idle_time_field = None
park_time_field = None
vehicle_light_field = None
vehicle_medium_field = None
vehicle_heavy_field = None
vehicle_year_field = None
speed_field = None
hour_profile_field = None
daily_profile_field = None
month_profile_field = None
co_gm_vh_field = None
hc_gm_vh_field = None
nox_gm_vh_field = None
sox_gm_vh_field = None
pm10_gm_vh_field = None
p1_gm_vh_field = None
p2_gm_vh_field = None
method_field = None
instudy = None


def form_open(my_dialog, layer_id, feature_id):
    global form
    global name_field
    global height_field
    global distance_field
    global idle_time_field
    global park_time_field
    global vehicle_light_field
    global vehicle_medium_field
    global vehicle_heavy_field
    global vehicle_year_field
    global speed_field
    global hour_profile_field
    global daily_profile_field
    global month_profile_field
    global co_gm_vh_field 
    global hc_gm_vh_field 
    global nox_gm_vh_field
    global sox_gm_vh_field
    global pm10_gm_vh_field
    global p1_gm_vh_field 
    global p2_gm_vh_field
    global method_field
    global instudy

    form = my_dialog
    name_field = form.findChild(QtWidgets.QLineEdit, "parking_id")
    height_field = form.findChild(QtWidgets.QLineEdit, "height")
    distance_field = form.findChild(QtWidgets.QLineEdit, "distance")
    idle_time_field = form.findChild(QtWidgets.QLineEdit, "idle_time")
    park_time_field = form.findChild(QtWidgets.QLineEdit, "park_time")
    vehicle_light_field = form.findChild(QtWidgets.QLineEdit, "vehicle_light")
    vehicle_medium_field = form.findChild(QtWidgets.QLineEdit, "vehicle_medium")
    vehicle_heavy_field = form.findChild(QtWidgets.QLineEdit, "vehicle_heavy")
    vehicle_year_field = form.findChild(QtWidgets.QLineEdit, "vehicle_year")
    speed_field = form.findChild(QtWidgets.QLineEdit, "speed")
    hour_profile_field = form.findChild(QtWidgets.QComboBox, "hour_profile")
    daily_profile_field = form.findChild(QtWidgets.QComboBox, "daily_profile")
    month_profile_field = form.findChild(QtWidgets.QComboBox, "month_profile")
    co_gm_vh_field = form.findChild(QtWidgets.QLineEdit, "co_gm_vh")
    hc_gm_vh_field = form.findChild(QtWidgets.QLineEdit, "hc_gm_vh")
    nox_gm_vh_field = form.findChild(QtWidgets.QLineEdit, "nox_gm_vh")
    sox_gm_vh_field = form.findChild(QtWidgets.QLineEdit, "sox_gm_vh")
    pm10_gm_vh_field = form.findChild(QtWidgets.QLineEdit, "pm10_gm_vh")
    p1_gm_vh_field = form.findChild(QtWidgets.QLineEdit, "p1_gm_vh")
    p2_gm_vh_field = form.findChild(QtWidgets.QLineEdit, "p2_gm_vh")
    method_field = form.findChild(QtWidgets.QLineEdit, "method")
    recalculate = form.findChild(QtWidgets.QPushButton, "button_recalculate")
    button_box = form.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
    instudy = form.findChild(QtWidgets.QCheckBox, "instudy")

    recalculate.clicked.connect(recalculate_emissions)

    #disconnect old-style signals, which are created e.g. by QGIS from the ui file
    # try:
    #     QObject.disconnect(button_box, SIGNAL("accepted()"), form.accept)
    # except Exception, e:
    #     pass
    #disconnect new-style signals
    try:
        button_box.accepted.disconnect(form.accept)
    except Exception as e:
        pass

    button_box.accepted.connect(validate)
    # button_box.rejected.connect(form.reject)

    populate_hourly_profiles()
    populate_daily_profiles()
    populate_monthly_profiles()

    method_field.setText("Open-ALAQS")
    method_field.setEnabled(False)
    height_field.setText("0")
    height_field.setEnabled(False)
    park_time_field.setText("0")
    park_time_field.setEnabled(False)


def populate_hourly_profiles():
    try:
        hourly_profiles = alaqs.get_hourly_profiles()
        if (hourly_profiles is None) or (hourly_profiles == []):
            hour_profile_field.addItem("default")
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


def recalculate_emissions():
    try:
        # Do some validation first
        name = validate_field(name_field, "str")
        vehicle_year = validate_field(vehicle_year_field, "int")
        height = validate_field(height_field, "float")
        speed = validate_field(speed_field, "float")
        travel_distance = validate_field(distance_field, "float")
        idle_time = validate_field(idle_time_field, "float")
        park_time = validate_field(park_time_field, "float")
        vehicle_light = validate_field(vehicle_light_field, "float")
        vehicle_medium = validate_field(vehicle_medium_field, "float")
        vehicle_heavy = validate_field(vehicle_heavy_field, "float")
        method = str(method_field.text())

        if name is False or vehicle_year is False or height is False or speed is False or vehicle_light is False or \
                        vehicle_medium is False or vehicle_heavy is False or method is False or \
                        travel_distance is False or idle_time is False or park_time is False:
            msg_box = QtWidgets.QMessageBox()
            msg_box.setText("Please complete all fields first")
            msg_box.exec_()
            return False

        form_data_dict = dict()
        form_data_dict['name'] = name
        form_data_dict['vehicle_year'] = vehicle_year
        form_data_dict['height'] = height
        form_data_dict['speed'] = speed
        form_data_dict['vehicle_light'] = float(vehicle_light)
        form_data_dict['vehicle_medium'] = float(vehicle_medium)
        form_data_dict['vehicle_heavy'] = float(vehicle_heavy)
        form_data_dict['idle_time'] = float(idle_time)
        form_data_dict['park_time'] = float(park_time)
        form_data_dict['travel_distance'] = float(travel_distance)
        form_data_dict['parking'] = True

        vl = float(vehicle_light_field.text())
        vm = float(vehicle_medium_field.text())
        vh = float(vehicle_heavy_field.text())
        if (vl + vm + vh) != 100:
            QtWidgets.QMessageBox().warning(form, "Error", "Fleet mix must be decimal values that total 100%",
                                            QtWidgets.QMessageBox.Cancel)
            return error

        emission_profile = None
        if method == "Open-ALAQS":
            # Calculate emissions according to the ALAQS method
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            emission_profile = roadway_emission_factors_alaqs_method(form_data_dict)
            QtWidgets.QApplication.restoreOverrideCursor()

        co_gm_vh_field.setText(str(emission_profile['co_ef']))
        hc_gm_vh_field.setText(str(emission_profile['hc_ef']))
        nox_gm_vh_field.setText(str(emission_profile['nox_ef']))
        sox_gm_vh_field.setText(str(emission_profile['sox_ef']))
        pm10_gm_vh_field.setText(str(emission_profile['pm10_ef']))
        p1_gm_vh_field.setText(str(emission_profile['p1_ef']))
        p2_gm_vh_field.setText(str(emission_profile['p2_ef']))

    except Exception as e:
        msg_box = QtWidgets.QMessageBox()
        msg_box.setText("Emissions could not be calculated: %s" % e)
        msg_box.exec_()
        error = alaqsutils.print_error(populate_hourly_profiles.__name__, Exception, e)
        return error


def validate():
    """
    This function validates that all of the required fields have been completed
    correctly. If they have, the attributes are committed to the feature. 
    Otherwise an error message is displayed and the incorrect field is 
    highlighted in red.
    """
    results = list()
    results.append(validate_field(name_field, "str"))
    results.append(validate_field(vehicle_year_field, "int"))
    results.append(validate_field(height_field, "float"))
    results.append(validate_field(speed_field, "float"))
    results.append(validate_field(distance_field, "float"))
    results.append(validate_field(idle_time_field, "float"))
    results.append(validate_field(park_time_field, "float"))
    results.append(validate_field(vehicle_light_field, "float"))
    results.append(validate_field(vehicle_medium_field, "float"))
    results.append(validate_field(vehicle_heavy_field, "float"))
    results.append(validate_field(co_gm_vh_field, "float"))
    results.append(validate_field(hc_gm_vh_field, "float"))
    results.append(validate_field(nox_gm_vh_field, "float"))
    results.append(validate_field(sox_gm_vh_field, "float"))
    results.append(validate_field(pm10_gm_vh_field, "float"))
    results.append(validate_field(p1_gm_vh_field, "float"))
    results.append(validate_field(p2_gm_vh_field, "float"))

    for value in results:
        if value is False:
            msg = QtWidgets.QMessageBox()
            msg.setIcon(QtWidgets.QMessageBox.Critical)
            msg.setWindowTitle('Validation error')
            msg.setText("Please complete all fields.")
            # msg.setInformativeText(
            #     "It seems that some fields are empty. You need to provide values for all fields in red.")
            msg.exec_()
            # QtWidgets.QMessageBox().warning(form, "Error", "Please complete all fields", QtWidgets.QMessageBox.Cancel)
            return

    # vl = float(vehicle_light_field.text())
    # vm = float(vehicle_medium_field.text())
    # vh = float(vehicle_heavy_field.text())
    # if (vl + vm + vh) != 100:
    #     # msg_box = QtWidgets.QMessageBox()
    #     # msg_box.setText("Fleet mix must be decimal values that total 100%")
    #     # msg_box.exec_()
    #     QtWidgets.QMessageBox().warning(self, "Error", "Fleet mix must be decimal values that total 100%", QtWidgets.QMessageBox.Ok)
    #     return

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