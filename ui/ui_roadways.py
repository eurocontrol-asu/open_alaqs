from PyQt5 import QtCore, QtWidgets
from qgis.core import *
from qgis.gui import *

from open_alaqs.alaqs_core import alaqs, alaqslogging, alaqsutils
from open_alaqs.alaqs_core.tools.lib_alaqs_method import \
    roadway_emission_factors_alaqs_method

logger = alaqslogging.logging.getLogger(__name__)
logger.setLevel('DEBUG')
file_handler = alaqslogging.logging.FileHandler(alaqslogging.LOG_FILE_PATH)
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
formatter = alaqslogging.logging.Formatter(log_format)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

form = None
name_field = None
vehicle_year_field = None
speed_field = None
height_field = None
vehicle_light_field = None
vehicle_medium_field = None
vehicle_heavy_field = None
hour_profile_field = None
daily_profile_field = None
month_profile_field = None
co_gm_km_field = None
hc_gm_km_field = None
nox_gm_km_field = None
sox_gm_km_field = None
pm10_gm_km_field = None
p1_gm_km_field = None
p2_gm_km_field = None
method_field = None
scenario_field = None
instudy = None


def form_open(my_dialog, layer_id, feature_id):
    global form
    global name_field
    global vehicle_year_field
    global speed_field
    global height_field
    global vehicle_light_field
    global vehicle_medium_field
    global vehicle_heavy_field
    global hour_profile_field
    global daily_profile_field
    global month_profile_field
    global co_gm_km_field
    global hc_gm_km_field
    global nox_gm_km_field
    global sox_gm_km_field
    global pm10_gm_km_field
    global p1_gm_km_field
    global p2_gm_km_field
    global method_field
    global scenario_field
    global instudy

    form = my_dialog
    name_field = form.findChild(QtWidgets.QLineEdit, "roadway_id")
    vehicle_year_field = form.findChild(QtWidgets.QLineEdit, "vehicle_year")
    height_field = form.findChild(QtWidgets.QLineEdit, "height")
    speed_field = form.findChild(QtWidgets.QLineEdit, "speed")
    vehicle_light_field = form.findChild(QtWidgets.QLineEdit, "vehicle_light")
    vehicle_medium_field = form.findChild(QtWidgets.QLineEdit, "vehicle_medium")
    vehicle_heavy_field = form.findChild(QtWidgets.QLineEdit, "vehicle_heavy")
    hour_profile_field = form.findChild(QtWidgets.QComboBox, "hour_profile")
    daily_profile_field = form.findChild(QtWidgets.QComboBox, "daily_profile")
    month_profile_field = form.findChild(QtWidgets.QComboBox, "month_profile")
    co_gm_km_field = form.findChild(QtWidgets.QLineEdit, "co_gm_km")
    hc_gm_km_field = form.findChild(QtWidgets.QLineEdit, "hc_gm_km")
    nox_gm_km_field = form.findChild(QtWidgets.QLineEdit, "nox_gm_km")
    sox_gm_km_field = form.findChild(QtWidgets.QLineEdit, "sox_gm_km")
    pm10_gm_km_field = form.findChild(QtWidgets.QLineEdit, "pm10_gm_km")
    p1_gm_km_field = form.findChild(QtWidgets.QLineEdit, "p1_gm_km")
    p2_gm_km_field = form.findChild(QtWidgets.QLineEdit, "p2_gm_km")
    scenario_field = form.findChild(QtWidgets.QComboBox, "scenario")
    method_field = form.findChild(QtWidgets.QLineEdit, "method")
    # ToDo:
    # method_field = form.findChild(QtWidgets.QComboBox, "method")

    recalculate = form.findChild(QtWidgets.QPushButton, "button_recalculate")
    button_box = form.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
    instudy = form.findChild(QtWidgets.QCheckBox, "instudy")

    # populate_combo_boxes()
    populate_hourly_profiles()
    populate_daily_profiles()
    populate_monthly_profiles()

    recalculate.clicked.connect(recalculate_emissions)
    # #disconnect old-style signals, which are created e.g. by QGIS from the ui file
    # try:
    #     QObject.disconnect(button_box, SIGNAL("accepted()"), form.accept)
    # except Exception as e:
    #     pass
    #disconnect new-style signals
    try:
        button_box.accepted.disconnect(form.accept)
    except Exception as e:
        pass

    button_box.accepted.connect(validate)
    # button_box.rejected.connect(form.reject)

    # Disable the travel distance field - this can come directly from the geometry
    # QgsEditorWidgetWrapper.fromWidget( instudy ).setValue(1)
    # QgsEditorWidgetWrapper.fromWidget( method_field ).setValue("ALAQS")
    # QgsEditorWidgetWrapper.fromWidget( height_field ).setValue(0)

    method_field.setText("Open-ALAQS")
    method_field.setEnabled(False)
    scenario_field.addItem('Not Applicable')
    scenario_field.setEnabled(False)
    height_field.setText("0")
    height_field.setEnabled(False)

def recalculate_emissions():
    try:
        # Do some validation first
        name = validate_field(name_field, "str")
        vehicle_year = validate_field(vehicle_year_field, "int")
        height = validate_field(height_field, "float")
        speed = validate_field(speed_field, "float")
        vehicle_light = validate_field(vehicle_light_field, "float")
        vehicle_medium = validate_field(vehicle_medium_field, "float")
        vehicle_heavy = validate_field(vehicle_heavy_field, "float")
        method = str(method_field.text())

        if name is False or vehicle_year is False or height is False or speed is False or vehicle_light is False or \
                        vehicle_medium is False or vehicle_heavy is False or method is False:
            msg_box = QtWidgets.QMessageBox()
            msg_box.setText("Please complete all fields first")
            msg_box.exec_()
            return False
        
        vl = float(vehicle_light_field.text())
        vm = float(vehicle_medium_field.text())
        vh = float(vehicle_heavy_field.text())
        if (vl + vm + vh) != 100:
            msg_box = QtWidgets.QMessageBox()
            msg_box.setText("Fleet mix must be decimal values that total 100%")
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
        form_data_dict['parking'] = False
        
        emission_profile = None
        if method == "Open-ALAQS":
            # Calculate emissions according to the ALAQS method
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            emission_profile = roadway_emission_factors_alaqs_method(form_data_dict)
            QtWidgets.QApplication.restoreOverrideCursor()

        co_gm_km_field.setText(str(emission_profile['co_ef']))
        hc_gm_km_field.setText(str(emission_profile['hc_ef']))
        nox_gm_km_field.setText(str(emission_profile['nox_ef']))
        sox_gm_km_field.setText(str(emission_profile['sox_ef']))
        pm10_gm_km_field.setText(str(emission_profile['pm10_ef']))
        p1_gm_km_field.setText(str(emission_profile['p1_ef']))
        p2_gm_km_field.setText(str(emission_profile['p2_ef']))

    except Exception as e:
        msg_box = QtWidgets.QMessageBox()
        msg_box.setText("Emissions could not be calculated: %s" % e)
        msg_box.exec_()
        error = alaqsutils.print_error(populate_hourly_profiles.__name__, Exception, e)
        return error

def populate_hourly_profiles():
    try:
        AllItems = [hour_profile_field.itemText(i) for i in range(hour_profile_field.count())]
        if not "default" in AllItems:
            hour_profile_field.addItem("default")
        hourly_profiles = alaqs.get_hourly_profiles()

        if (hourly_profiles is None) or (hourly_profiles == []):
            hour_profile_field.addItem("default")
            # hour_profile_field.setCurrentIndex(0)
            return None
        else:
            for profile in hourly_profiles:
                if profile[1] != "default":
                    hour_profile_field.addItem(profile[1])
            hour_profile_field.setCurrentIndex(0)
            hour_profile_field.setEditable(False)

    except Exception as e:
        logger.debug(e)
        error = alaqsutils.print_error(populate_hourly_profiles.__name__, Exception, e)
        return error


def populate_daily_profiles():
    try:
        AllItems = [daily_profile_field.itemText(i) for i in range(daily_profile_field.count())]
        if not "default" in AllItems:
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
        AllItems = [month_profile_field.itemText(i) for i in range(month_profile_field.count())]
        if not "default" in AllItems:
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

# def populate_combo_boxes():
#     """
#     fills in the various comboboxes that are needed for the UI to be operational
#     """
#     hourly_profiles = alaqs.get_hourly_profiles()
#     if (hourly_profiles is None) or (hourly_profiles == []):
#         pass
#     else:
#         for profile in hourly_profiles:
#             if profile[1] != "default":
#                 hour_profile_field.addItem(profile[1])
#         hour_profile_field.setEditable(False)
#
#     daily_profiles = alaqs.get_daily_profiles()
#     if (daily_profiles is None) or (daily_profiles == []):
#         pass
#     else:
#         for profile in daily_profiles:
#             if profile[1] != "default":
#                 daily_profile_field.addItem(profile[1])
#         daily_profile_field.setEditable(False)
#
#     monthly_profiles = alaqs.get_daily_profiles()
#     if (monthly_profiles is None) or (monthly_profiles == []):
#         pass
#     else:
#         for profile in monthly_profiles:
#             if profile[1] != "default":
#                 month_profile_field.addItem(profile[1])
#         month_profile_field.setEditable(False)
#
#     # lasport_scenarios = alaqs.get_lasport_scenarios()
#     # if (lasport_scenarios is None) or (lasport_scenarios == []):
#     #    pass
#     # else:
#     #    for scenario in lasport_scenarios:
#     #        scenario = str(scenario[0]).replace("'", "")
#     #        scenario_field.addItem(scenario)
#     #    scenario_field.setEditable(False)
#     # scenario_field.addItem("Not Applicable")

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
    #results.append(validate_field(distance_field, "float"))
    results.append(validate_field(speed_field, "float"))
    results.append(validate_field(vehicle_light_field, "float"))
    results.append(validate_field(vehicle_medium_field, "float"))
    results.append(validate_field(vehicle_heavy_field, "float"))
    results.append(validate_field(hour_profile_field, "str"))
    results.append(validate_field(daily_profile_field, "str"))
    results.append(validate_field(month_profile_field, "str"))
    results.append(validate_field(co_gm_km_field, "float"))
    results.append(validate_field(hc_gm_km_field, "float"))
    results.append(validate_field(nox_gm_km_field, "float"))
    results.append(validate_field(sox_gm_km_field, "float"))
    results.append(validate_field(pm10_gm_km_field, "float"))
    results.append(validate_field(p1_gm_km_field, "float"))
    results.append(validate_field(p2_gm_km_field, "float"))

    # for value in results:
    #     if value is False:
    #         QtWidgets.QMessageBox.information(form, "Validation error", "Please fill in all the required fields")
    #         return False
    #
    # form.accept()
    if False in results:
        QtWidgets.QMessageBox.warning(None, "Validation error", "Please fill in all the required fields")
        return False

    else:
        form.save()

def validate_field(ui_element, var_type):
    try:
        value = str(ui_element.currentText()).strip()
    except:
        value = str(ui_element.text()).strip()
    try:
        if var_type is "str":
            # try:
            #     value = str(ui_element.currentText()).strip()
            # except:
            #     value = str(ui_element.text()).strip()
            if value == "" or value == NULL or value == None:
                color_ui_background(ui_element, "red")
                ui_element.setToolTip("This value should be a string")
                return False
            else:
                color_ui_background(ui_element, "white")
                return value

        elif var_type is "int":
            # try:
            #     value = str(ui_element.currentText()).strip()
            # except:
            #     value = str(ui_element.text()).strip()
            try:
                if value == "" or value == NULL or value == None:
                    color_ui_background(ui_element, "red")
                    #raise Exception()
                value = int(value)
                color_ui_background(ui_element, "white")
                return value
            except:
                color_ui_background(ui_element, "red")
                ui_element.setToolTip("This value should be an integer")
                return False

        elif var_type is "float":
            # try:
            #     value = str(ui_element.currentText()).strip()
            # except:
            #     value = str(ui_element.text()).strip()
            try:
                if value == "" or value == NULL or value == None:
                    color_ui_background(ui_element, "red")
                    # raise Exception()
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
        color_style = "QWidget { background-color: rgba(255, 107, 107, 150); }"
        ui_element.setStyleSheet(color_style)
    elif color is "white":
        color_style = "QWidget { background-color: rgba(255, 255, 255, 255); }"
        ui_element.setStyleSheet(color_style)
    else:
        color_style = "QWidget { background-color: rgba(0,255,0,0.3); }"
        ui_element.setStyleSheet(color_style)
        pass