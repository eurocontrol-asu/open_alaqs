# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/Users/sst/Dropbox/WorkOn/Projects/OpenALAQS/code/open_alaqs/ui/ui_taxiways.ui'
#
# Created by: PyQt5 UI code generator 5.13.0
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_TaxiwayDialog(object):
    def setupUi(self, TaxiwayDialog):
        TaxiwayDialog.setObjectName("TaxiwayDialog")
        TaxiwayDialog.resize(262, 153)
        self.formLayout = QtWidgets.QFormLayout(TaxiwayDialog)
        self.formLayout.setObjectName("formLayout")
        self.label = QtWidgets.QLabel(TaxiwayDialog)
        self.label.setObjectName("label")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.LabelRole, self.label)
        self.taxiway_id = QtWidgets.QLineEdit(TaxiwayDialog)
        self.taxiway_id.setObjectName("taxiway_id")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.FieldRole, self.taxiway_id)
        self.label_2 = QtWidgets.QLabel(TaxiwayDialog)
        self.label_2.setObjectName("label_2")
        self.formLayout.setWidget(3, QtWidgets.QFormLayout.LabelRole, self.label_2)
        self.time = QtWidgets.QLineEdit(TaxiwayDialog)
        self.time.setObjectName("time")
        self.formLayout.setWidget(3, QtWidgets.QFormLayout.FieldRole, self.time)
        self.label_3 = QtWidgets.QLabel(TaxiwayDialog)
        self.label_3.setObjectName("label_3")
        self.formLayout.setWidget(4, QtWidgets.QFormLayout.LabelRole, self.label_3)
        self.speed = QtWidgets.QLineEdit(TaxiwayDialog)
        self.speed.setObjectName("speed")
        self.formLayout.setWidget(4, QtWidgets.QFormLayout.FieldRole, self.speed)
        self.buttonBox = QtWidgets.QDialogButtonBox(TaxiwayDialog)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.formLayout.setWidget(5, QtWidgets.QFormLayout.SpanningRole, self.buttonBox)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setContentsMargins(-1, 0, -1, -1)
        self.horizontalLayout.setObjectName("horizontalLayout")
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.instudy = QtWidgets.QCheckBox(TaxiwayDialog)
        self.instudy.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.instudy.setChecked(True)
        self.instudy.setObjectName("instudy")
        self.horizontalLayout.addWidget(self.instudy)
        self.formLayout.setLayout(1, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout)

        self.retranslateUi(TaxiwayDialog)
        self.buttonBox.accepted.connect(TaxiwayDialog.accept)
        self.buttonBox.rejected.connect(TaxiwayDialog.reject)
        QtCore.QMetaObject.connectSlotsByName(TaxiwayDialog)
        TaxiwayDialog.setTabOrder(self.taxiway_id, self.time)
        TaxiwayDialog.setTabOrder(self.time, self.speed)
        TaxiwayDialog.setTabOrder(self.speed, self.buttonBox)

    def retranslateUi(self, TaxiwayDialog):
        _translate = QtCore.QCoreApplication.translate
        TaxiwayDialog.setWindowTitle(_translate("TaxiwayDialog", "Taxiway Editor"))
        self.label.setText(_translate("TaxiwayDialog", "Name"))
        self.taxiway_id.setToolTip(_translate("TaxiwayDialog", "Enter a unique name for your taxiway"))
        self.label_2.setText(_translate("TaxiwayDialog", "Time (minutes)"))
        self.time.setToolTip(_translate("TaxiwayDialog", "Enter a time in minutes that an aircraft takes to clear this taxiway"))
        self.label_3.setText(_translate("TaxiwayDialog", "Speed (km/h)"))
        self.speed.setToolTip(_translate("TaxiwayDialog", "Enter the speed that the aircraft travels on this taxiway"))
        self.instudy.setText(_translate("TaxiwayDialog", "In Study"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    TaxiwayDialog = QtWidgets.QDialog()
    ui = Ui_TaxiwayDialog()
    ui.setupUi(TaxiwayDialog)
    TaxiwayDialog.show()
    sys.exit(app.exec_())
