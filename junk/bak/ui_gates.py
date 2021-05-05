# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/Users/sst/Dropbox/WorkOn/Projects/OpenALAQS/code/open_alaqs/ui/ui_gates.ui'
#
# Created by: PyQt5 UI code generator 5.13.0
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_GatesDialog(object):
    def setupUi(self, GatesDialog):
        GatesDialog.setObjectName("GatesDialog")
        GatesDialog.resize(278, 153)
        self.formLayout = QtWidgets.QFormLayout(GatesDialog)
        self.formLayout.setObjectName("formLayout")
        self.label = QtWidgets.QLabel(GatesDialog)
        self.label.setObjectName("label")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.LabelRole, self.label)
        self.gate_id = QtWidgets.QLineEdit(GatesDialog)
        self.gate_id.setObjectName("gate_id")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.FieldRole, self.gate_id)
        self.label_5 = QtWidgets.QLabel(GatesDialog)
        self.label_5.setObjectName("label_5")
        self.formLayout.setWidget(3, QtWidgets.QFormLayout.LabelRole, self.label_5)
        self.gate_type = QtWidgets.QComboBox(GatesDialog)
        self.gate_type.setObjectName("gate_type")
        self.formLayout.setWidget(3, QtWidgets.QFormLayout.FieldRole, self.gate_type)
        self.label_2 = QtWidgets.QLabel(GatesDialog)
        self.label_2.setObjectName("label_2")
        self.formLayout.setWidget(4, QtWidgets.QFormLayout.LabelRole, self.label_2)
        self.gate_height = QtWidgets.QLineEdit(GatesDialog)
        self.gate_height.setObjectName("gate_height")
        self.formLayout.setWidget(4, QtWidgets.QFormLayout.FieldRole, self.gate_height)
        self.buttonBox = QtWidgets.QDialogButtonBox(GatesDialog)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.formLayout.setWidget(5, QtWidgets.QFormLayout.SpanningRole, self.buttonBox)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setContentsMargins(-1, 0, -1, -1)
        self.horizontalLayout.setObjectName("horizontalLayout")
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.instudy = QtWidgets.QCheckBox(GatesDialog)
        self.instudy.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.instudy.setChecked(True)
        self.instudy.setObjectName("instudy")
        self.horizontalLayout.addWidget(self.instudy)
        self.formLayout.setLayout(0, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout)

        self.retranslateUi(GatesDialog)
        self.buttonBox.accepted.connect(GatesDialog.accept)
        self.buttonBox.rejected.connect(GatesDialog.reject)
        QtCore.QMetaObject.connectSlotsByName(GatesDialog)
        GatesDialog.setTabOrder(self.gate_id, self.gate_type)
        GatesDialog.setTabOrder(self.gate_type, self.gate_height)
        GatesDialog.setTabOrder(self.gate_height, self.buttonBox)

    def retranslateUi(self, GatesDialog):
        _translate = QtCore.QCoreApplication.translate
        GatesDialog.setWindowTitle(_translate("GatesDialog", "Gate Editor"))
        self.label.setText(_translate("GatesDialog", "Gate Name"))
        self.gate_id.setToolTip(_translate("GatesDialog", "Enter a unique name for your gate"))
        self.label_5.setText(_translate("GatesDialog", "Gate Type"))
        self.gate_type.setToolTip(_translate("GatesDialog", "Choose the gate type this gate relates to"))
        self.label_2.setText(_translate("GatesDialog", "Gate Height"))
        self.gate_height.setToolTip(_translate("GatesDialog", "Enter a height for this gate"))
        self.instudy.setText(_translate("GatesDialog", "In Study"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    GatesDialog = QtWidgets.QDialog()
    ui = Ui_GatesDialog()
    ui.setupUi(GatesDialog)
    GatesDialog.show()
    sys.exit(app.exec_())
