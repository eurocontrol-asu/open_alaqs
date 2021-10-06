from PyQt5 import QtWidgets

form = None
name_field = None
type_field = None
height_field = None
instudy = None

def form_open(my_dialog, layer_id, feature_id):
    global form
    global name_field
    global type_field
    global height_field
    global instudy
    global layer
    layer = layer_id

    # QgsAttributeForm contains QgsFeature with attributes gate_id, gate_type etc ..
    form = my_dialog
    name_field = form.findChild(QtWidgets.QLineEdit, "gate_id")
    name_field.setToolTip('Gate ID')

    type_field = form.findChild(QtWidgets.QComboBox, "gate_type")
    type_field.setToolTip('Gate type')

    height_field = form.findChild(QtWidgets.QLineEdit, "gate_height")
    height_field.setToolTip('Not implemented')

    button_box = form.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
    instudy = form.findChild(QtWidgets.QCheckBox, "instudy")
    instudy.setToolTip('Enable to include source in the study')

    button_box.button(button_box.Ok).blockSignals(True)

    populate_combo_boxes()

    # # disconnect old-style signals, which are created e.g. by QGIS from the ui file
    # try:
    #     QObject.disconnect(button_box, SIGNAL("accepted()"), form.accept)
    # except Exception, e:
    #     pass
    #disconnect new-style signals
    # try:
    #     button_box.accepted.disconnect(form.accept)
    #     # button_box.rejected.disconnect(form.reject)
    # except Exception as e:
    #     pass

    # form.setStyleSheet( "QLineEdit { background: yellow }" )
    # button_box.accepted.connect(validate)
    # button_box.rejected.connect(form.reject)

    # layer.startEditing()

    # instudy_NameIndex = layer.fieldNameIndex("instudy")
    # QgsEditorWidgetWrapper.fromWidget( instudy ).setValue(1)

    # QgsEditorWidgetWrapper.fromWidget( height_field ).setValue(0)
    height_field.setText("0")
    height_field.setEnabled(False)
    # name_field.setText("")
    # name_field.setStyleSheet("background-color: rgba(255, 107, 107, 150);")
    # name_field.textChanged.connect(NameFieldChanged)

    name_field.textChanged.connect(lambda: validate(button_box))
    height_field.textChanged.connect(lambda: validate(button_box)) 
    type_field.currentTextChanged.connect(lambda: validate(button_box)) 

def NameFieldChanged():
    try:
        value = str(name_field.currentText()).strip()
    except:
        value = str(name_field.text()).strip()
    if not value:
        name_field.setStyleSheet("background-color: rgba(255, 107, 107, 150);")
    else:
        name_field.setStyleSheet("")

def validate(button_box):
    """
    This function validates that all of the required fields have been completed correctly. If they have, the attributes
    are committed to the feature. Otherwise an error message is displayed and the incorrect field is highlighted in red.
    """
    results = list()

    results.append(validate_field(name_field, "str"))
    results.append(validate_field(type_field, "str"))
    results.append(validate_field(height_field, "float"))

    # results = {"name field":validate_field(name_field, "str"),
    #            "type field":validate_field(type_field, "str"),
    #            "height field":validate_field(height_field, "str")
    #            }
    # for key_ in results.keys():
    #     if not results[key_]:
    #         QMessageBox.warning(form, "Error", "Please complete %s"%key_)

    # if False in results:
    #     msg = QtWidgets.QMessageBox()
    #     msg.setIcon(QtWidgets.QMessageBox.Critical)
    #     msg.setWindowTitle('Validation error')
    #     msg.setText("Please complete all fields.")
    #     # msg.setInformativeText(
    #     #     "It seems that some fields are empty. You need to provide values for all fields in red.")
    #     msg.exec_()
    #     return

    # else:
    #     form.save()

    if not ('False' in str(results)):
        if results[1] in ['PIER', 'REMOTE', 'CARGO']:
            button_box.button(button_box.Ok).blockSignals(False)
            button_box.accepted.connect(form.save)
        else:
            button_box.button(button_box.Ok).blockSignals(True)
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


def populate_combo_boxes():
    type_field.addItem("PIER")
    type_field.addItem("REMOTE")
    type_field.addItem("CARGO")


    # # Feature we will modify
    # feat = QgsFeature(layer.pendingFields())
    # feat_id = feat.id()
    # # # gate_height QgsField
    # height_idx = layer.pendingFields().fieldNameIndex("gate_height")
    # layer.dataProvider().changeAttributeValues({ feat.id() : { height_idx : 999 } })
    # layer.updateFeature(feat)
    # layer.changeAttributeValue(feat_id, height_idx, -999)
    # layer.updateFields()

    # layer.setFieldEditable( height_idx, False )
    # height_field.setEnabled(False)