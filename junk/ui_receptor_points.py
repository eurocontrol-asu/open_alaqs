from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

import os, sys
from qgis.gui import QgsEditorWidgetWrapper
#from qgis.utils import *

import alaqs
import alaqsutils

form = None
name_field = None
height_field = None
x_field = None
y_field = None
instudy = None

def form_open(my_dialog, layer_id, feature_id):

    global form
    global name_field
    global height_field
    global x_field
    global y_field
    global instudy

    form = my_dialog

    name_field = form.findChild(QtWidgets.QLineEdit, "source_id")
    height_field = form.findChild(QtWidgets.QLineEdit, "height")
    x_field = form.findChild(QtWidgets.QComboBox, "xcoord")
    y_field = form.findChild(QtWidgets.QComboBox, "ycoord")
    instudy = form.findChild(QtWidgets.QCheckBox, "instudy")

    button_box = form.findChild(QtWidgets.QDialogButtonBox, "buttonBox")

    #self.action.triggered.connect(self.run)

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

    # x_field.currentIndexChanged["QString"].connect(change_xcoord)
    # y_field.currentIndexChanged["QString"].connect(change_xcoord)
    # type_field.currentIndexChanged["QString"].connect(change_category_type)

    button_box.accepted.connect(validate)
    #button_box.rejected.connect(form.resetValues)

    return form





# def change_point_category():
#     """
#     Description
#     """
#     try:
#         category_name = str(category_field.currentText()).strip()
#         if category_name == "Other":
#             type_field.clear()
#             type_field.addItem("NA")
#             height_field.setEnabled(True)
#             substance_field.setEnabled(True)
#             temperature_field.setEnabled(True)
#             diameter_field.setEnabled(True)
#             velocity_field.setEnabled(True)
#             return
#         if category_name == "":
#             type_field.clear()
#             height_field.setText("")
#             temperature_field.setText("")
#             diameter_field.setText("")
#             velocity_field.setText("")
#             substance_field.setText("")
#             return
#
#         category_data = alaqs.get_point_category(category_name)
#         # QgsMapLayerRegistry.instance().addMapLayers([layer])
#         if isinstance(category_data, str):
#             raise Exception("No data was found for the supplied category: %s" % category_data)
#         elif (category_data is None) or (category_data == []):
#             raise Exception("The selected category returned no data: %s" % category_data)
#         else:
#             category_num = category_data[0][1]
#             category_types = alaqs.get_point_types(category_num)
#             if isinstance(category_types, str):
#                 raise Exception("Category types could not be returned: %s" % category_types)
#             elif (category_types == []) or (category_types is None):
#                 raise Exception("No category types were returned.")
#             else:
#                 type_field.clear()
#                 for category_type in category_types:
#                     type_field.addItem(category_type[7])
#             return None
#     except Exception as e:
#         #QtWidgets.QMessageBox.information(None, "Error", e)
#         error = alaqsutils.print_error(change_point_category.__name__, Exception, e)
#         return error


# def change_category_type(type_name):
#     """
#     Description
#     """
#     try:
#         if type_name != "":
#             type_data = alaqs.get_point_type(type_name)
#             if isinstance(type_data,str):
#                 raise Exception("Could not return category type data: %s" % type_data)
#             elif (type_data is None) or (type_data == []):
#                 raise Exception("No data could be found for this category.")
#             else:
#
#                 data = type_data[0]
#                 temperature = data[3]
#                 diameter = data[4]
#                 velocity = data[5]
#                 height = data[6]
#                 description = data[7]
#                 co_kg_k = data[8]
#                 hc_kg_k = data[9]
#                 nox_kg_k = data[10]
#                 sox_kg_k = data[11]
#                 pm10_kg_k = data[12]
#                 p1_kg_k = data[13]
#                 p2_kg_k = data[14]
#                 substance = data[15]
#
#                 height_field.setText(str(height))
#                 temperature_field.setText(str(temperature))
#                 diameter_field.setText(str(diameter))
#                 velocity_field.setText(str(velocity))
#                 if substance == 1:
#                     substance_field.setText("Solid")
#                 elif substance == 2:
#                     substance_field.setText("Liquid")
#                 elif substance == 3:
#                     substance_field.setText("Gas")
#                 else:
#                     raise Exception("Substance could not be identified for this point type.")
#                 co_kg_k_field.setText(str(co_kg_k))
#                 hc_kg_k_field.setText(str(hc_kg_k))
#                 nox_kg_k_field.setText(str(nox_kg_k))
#                 sox_kg_k_field.setText(str(sox_kg_k))
#                 pm10_kg_k_field.setText(str(pm10_kg_k))
#                 p1_kg_k_field.setText(str(p1_kg_k))
#                 p2_kg_k_field.setText(str(p2_kg_k))
#
#         else:
#             height_field.setText("")
#             temperature_field.setText("")
#             diameter_field.setText("")
#             velocity_field.setText("")
#             substance_field.setText("")
#             co_kg_k_field.setText("")
#             hc_kg_k_field.setText("")
#             nox_kg_k_field.setText("")
#             sox_kg_k_field.setText("")
#             pm10_kg_k_field.setText("")
#             p1_kg_k_field.setText("")
#             p2_kg_k_field.setText("")
#             return None
#     except Exception as e:
#         error = alaqsutils.print_error(change_category_type.__name__, Exception, e)
#         return error


def validate():
    """
    This function validates that all of the required fields have been completed
    correctly. If they have, the attributes are committed to the feature. 
    Otherwise an error message is displayed and the incorrect field is 
    highlighted in red.
    """
    results = list()
    results.append(validate_field(name_field, "str"))
    results.append(validate_field(height_field, "float"))

    if False in results:
        QtWidgets.QMessageBox.warning(None, "Validation error", "Please fill in all the required fields")
        return False

    else:
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
    elif color is "green":
        ui_element.setStyleSheet("background-color: rgba(0,255,0,0.3);")
    else:
        #ui_element.setStyleSheet("background-color: rgba(192,192,192,0.3);")
        pass

if __name__ == "__main__":
    # import sys, os
    from PyQt5 import QtCore, QtGui, QtWidgets
    from PyQt5.QtCore import Qt

    app = QtWidgets.QApplication(sys.argv)
    QtWidgets.QApplication.setQuitOnLastWindowClosed(False)
    Dialog = QtWidgets.QDialog()
    ui = Ui_Dialog()
    ui.setupUi(Dialog)
    Dialog.show()
    # sys.exit(app.exec_())
    app.exec_()