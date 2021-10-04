from PyQt5 import QtWidgets

from open_alaqs.alaqs_core import alaqs
from open_alaqs.alaqs_core import alaqsutils

# from qgis.utils import *

form = None
name_field = None
height_field = None
category_field = None
type_field = None
substance_field = None
temperature_field = None
diameter_field = None
velocity_field = None
ops_year_field = None
hour_profile_field = None
daily_profile_field = None
month_profile_field = None
co_kg_k_field = None
hc_kg_k_field = None
nox_kg_k_field = None
sox_kg_k_field = None
pm10_kg_k_field = None
p1_kg_k_field = None
p2_kg_k_field = None
instudy = None


def form_open(my_dialog, layer_id, feature_id):


    global form
    global name_field
    global height_field
    global category_field
    global type_field
    global substance_field
    global temperature_field
    global diameter_field
    global velocity_field
    global ops_year_field
    global hour_profile_field
    global daily_profile_field
    global month_profile_field
    global co_kg_k_field
    global hc_kg_k_field
    global nox_kg_k_field
    global sox_kg_k_field
    global pm10_kg_k_field
    global p1_kg_k_field
    global p2_kg_k_field
    global instudy

    form = my_dialog

    name_field = form.findChild(QtWidgets.QLineEdit, "source_id")
    height_field = form.findChild(QtWidgets.QLineEdit, "height")
    co_kg_k_field = form.findChild(QtWidgets.QLineEdit, "co_kg_k")
    hc_kg_k_field = form.findChild(QtWidgets.QLineEdit, "hc_kg_k")
    nox_kg_k_field = form.findChild(QtWidgets.QLineEdit, "nox_kg_k")
    sox_kg_k_field = form.findChild(QtWidgets.QLineEdit, "sox_kg_k")
    pm10_kg_k_field = form.findChild(QtWidgets.QLineEdit, "pm10_kg_k")
    p1_kg_k_field = form.findChild(QtWidgets.QLineEdit, "p1_kg_k")
    p2_kg_k_field = form.findChild(QtWidgets.QLineEdit, "p2_kg_k")
    substance_field = form.findChild(QtWidgets.QLineEdit, "substance")
    temperature_field = form.findChild(QtWidgets.QLineEdit, "temperature")
    diameter_field = form.findChild(QtWidgets.QLineEdit, "diameter")
    velocity_field = form.findChild(QtWidgets.QLineEdit, "velocity")
    ops_year_field = form.findChild(QtWidgets.QLineEdit, "ops_year")

    category_field = form.findChild(QtWidgets.QComboBox, "category")
    type_field = form.findChild(QtWidgets.QComboBox, "type")
    hour_profile_field = form.findChild(QtWidgets.QComboBox, "hour_profile")
    daily_profile_field = form.findChild(QtWidgets.QComboBox, "daily_profile")
    month_profile_field = form.findChild(QtWidgets.QComboBox, "month_profile")

    instudy = form.findChild(QtWidgets.QCheckBox, "instudy")
    button_box = form.findChild(QtWidgets.QDialogButtonBox, "buttonBox")

    group_change = True

    if category_field is not None:
        button_box.button(button_box.Ok).blockSignals(True)
        group_change = False

    #self.action.triggered.connect(self.run)

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

    # QgsEditorWidgetWrapper.fromWidget(instudy).setValue('T')
    if not group_change:
        category_field.addItem("")
        category_field.setCurrentIndex(0)
        type_field.addItem("")

        populate_categories()
        populate_hourly_profiles()
        populate_daily_profiles()
        populate_monthly_profiles()

        category_field.currentIndexChanged["QString"].connect(change_point_category)
        type_field.currentIndexChanged["QString"].connect(change_category_type)

        name_field.textChanged.connect(lambda: validate(button_box))
        height_field.textChanged.connect(lambda: validate(button_box))
        co_kg_k_field.textChanged.connect(lambda: validate(button_box)) 
        hc_kg_k_field.textChanged.connect(lambda: validate(button_box))
        nox_kg_k_field.textChanged.connect(lambda: validate(button_box))
        sox_kg_k_field.textChanged.connect(lambda: validate(button_box))
        pm10_kg_k_field.textChanged.connect(lambda: validate(button_box)) 
        p1_kg_k_field.textChanged.connect(lambda: validate(button_box))
        p2_kg_k_field.textChanged.connect(lambda: validate(button_box))
        substance_field.textChanged.connect(lambda: validate(button_box))
        temperature_field.textChanged.connect(lambda: validate(button_box))
        diameter_field.textChanged.connect(lambda: validate(button_box))
        velocity_field.textChanged.connect(lambda: validate(button_box))
        ops_year_field.textChanged.connect(lambda: validate(button_box))

    # button_box.accepted.connect(validate)
    #button_box.rejected.connect(form.resetValues)

    #type_field.clear()
    #type_attribute = {description : description}
    #QgsEditorWidgetWrapper.fromWidget(type_field).setValue(type_attribute)

    # layer = iface.activeLayer()
    # layer.startEditing()
    # idx = layer.fieldNameIndex("type")
    # layer.setFieldEditable(idx, True)
    # type_attribute = str(type_field.currentText()).strip()
    # # for feat in layer.getFeatures():
    # for feat in layer.selectedFeatures():
    #     fid = feat.id()
    #     layer.changeAttributeValue(fid, idx, type_attribute)
    # # layer.changeAttributeValue(-1, idx, type_attribute)
    # layer.commitChanges()

    # return form(my_dialog, layer_id, feature_id)
    return form


def populate_categories():
    """
    Description
    """
    try:
        #category_field.clear()
        categories = alaqs.get_point_categories()
        if (categories is None) or (categories == []):
            return None
        else:
            for category in categories:
                category_field.addItem(category[2])
            category_field.setCurrentIndex(0)
            category_field.setEditable(False)

    except Exception as e:
        error = alaqsutils.print_error(populate_categories.__name__, Exception, e)
        return error


def change_point_category():
    """
    Description
    """
    try:
        category_name = str(category_field.currentText()).strip()
        if category_name == "Other":
            type_field.clear()
            type_field.addItem("NA")
            height_field.setEnabled(True)
            substance_field.setEnabled(True)
            temperature_field.setEnabled(True)
            diameter_field.setEnabled(True)
            velocity_field.setEnabled(True)
            return
        if category_name == "":
            type_field.clear()
            height_field.setText("")
            temperature_field.setText("")
            diameter_field.setText("")
            velocity_field.setText("")
            substance_field.setText("")
            return

        category_data = alaqs.get_point_category(category_name)
        # QgsMapLayerRegistry.instance().addMapLayers([layer])
        if isinstance(category_data, str):
            raise Exception("No data was found for the supplied category: %s" % category_data)
        elif (category_data is None) or (category_data == []):
            raise Exception("The selected category returned no data: %s" % category_data)
        else:
            category_num = category_data[0][1]
            category_types = alaqs.get_point_types(category_num)
            if isinstance(category_types, str):
                raise Exception("Category types could not be returned: %s" % category_types)
            elif (category_types == []) or (category_types is None):
                raise Exception("No category types were returned.")
            else:
                type_field.clear()
                for category_type in category_types:
                    type_field.addItem(category_type[7])
            return None
    except Exception as e:
        #QtWidgets.QMessageBox.information(None, "Error", e)
        error = alaqsutils.print_error(change_point_category.__name__, Exception, e)
        return error


def change_category_type(type_name):
    """
    Description
    """
    try:
        if type_name != "":
            type_data = alaqs.get_point_type(type_name)
            if isinstance(type_data,str):
                raise Exception("Could not return category type data: %s" % type_data)
            elif (type_data is None) or (type_data == []):
                raise Exception("No data could be found for this category.")
            else:

                data = type_data[0]
                temperature = data[3]
                diameter = data[4]
                velocity = data[5]
                height = data[6]
                description = data[7]
                co_kg_k = data[8]
                hc_kg_k = data[9]
                nox_kg_k = data[10]
                sox_kg_k = data[11]
                pm10_kg_k = data[12]
                p1_kg_k = data[13]
                p2_kg_k = data[14]
                substance = data[15]

                height_field.setText(str(height))
                temperature_field.setText(str(temperature))
                diameter_field.setText(str(diameter))
                velocity_field.setText(str(velocity))
                if substance == 1:
                    substance_field.setText("Solid")
                elif substance == 2:
                    substance_field.setText("Liquid")
                elif substance == 3:
                    substance_field.setText("Gas")
                else:
                    raise Exception("Substance could not be identified for this point type.")
                co_kg_k_field.setText(str(co_kg_k))
                hc_kg_k_field.setText(str(hc_kg_k))
                nox_kg_k_field.setText(str(nox_kg_k))
                sox_kg_k_field.setText(str(sox_kg_k))
                pm10_kg_k_field.setText(str(pm10_kg_k))
                p1_kg_k_field.setText(str(p1_kg_k))
                p2_kg_k_field.setText(str(p2_kg_k))

        else:
            height_field.setText("")
            temperature_field.setText("")
            diameter_field.setText("")
            velocity_field.setText("")
            substance_field.setText("")
            co_kg_k_field.setText("")
            hc_kg_k_field.setText("")
            nox_kg_k_field.setText("")
            sox_kg_k_field.setText("")
            pm10_kg_k_field.setText("")
            p1_kg_k_field.setText("")
            p2_kg_k_field.setText("")
            return None
    except Exception as e:
        error = alaqsutils.print_error(change_category_type.__name__, Exception, e)
        return error


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
    results.append(validate_field(height_field, "float"))
    results.append(validate_field(ops_year_field, "float"))
    results.append(validate_field(temperature_field, "float"))
    results.append(validate_field(diameter_field, "float"))
    results.append(validate_field(velocity_field, "float"))
    results.append(validate_field(co_kg_k_field, "float"))
    results.append(validate_field(hc_kg_k_field, "float"))
    results.append(validate_field(nox_kg_k_field, "float"))
    results.append(validate_field(sox_kg_k_field, "float"))
    results.append(validate_field(pm10_kg_k_field, "float"))
    results.append(validate_field(p1_kg_k_field, "float"))
    results.append(validate_field(p2_kg_k_field, "float"))

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
    elif color is "green":
        ui_element.setStyleSheet("background-color: rgba(0,255,0,0.3);")
    else:
        #ui_element.setStyleSheet("background-color: rgba(192,192,192,0.3);")
        pass

# if __name__ == "__main__":
#     import sys
#     from PyQt5 import QtCore, QtGui, QtWidgets
#     from PyQt5.QtCore import Qt
#
#     app = QtWidgets.QApplication(sys.argv)
#     QtWidgets.QApplication.setQuitOnLastWindowClosed(False)
#     Dialog = QtWidgets.QDialog()
#     ui = Ui_Dialog()
#     ui.setupUi(Dialog)
#     Dialog.show()
#     sys.exit(app.exec_())