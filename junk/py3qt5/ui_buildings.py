# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/Users/sst/Dropbox/WorkOn/Projects/OpenALAQS/code/open_alaqs/ui/ui_buildings.ui'
#
# Created by: PyQt5 UI code generator 5.13.0
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_BuildingsDialog(object):
    def setupUi(self, BuildingsDialog):
        BuildingsDialog.setObjectName("BuildingsDialog")
        BuildingsDialog.resize(309, 211)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(BuildingsDialog.sizePolicy().hasHeightForWidth())
        BuildingsDialog.setSizePolicy(sizePolicy)
        BuildingsDialog.setMinimumSize(QtCore.QSize(0, 0))
        self.formLayout = QtWidgets.QFormLayout(BuildingsDialog)
        self.formLayout.setSizeConstraint(QtWidgets.QLayout.SetFixedSize)
        self.formLayout.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        self.formLayout.setObjectName("formLayout")
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setContentsMargins(-1, 0, -1, -1)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout_2.addItem(spacerItem)
        self.instudy = QtWidgets.QCheckBox(BuildingsDialog)
        self.instudy.setEnabled(True)
        self.instudy.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.instudy.setChecked(False)
        self.instudy.setObjectName("instudy")
        self.horizontalLayout_2.addWidget(self.instudy)
        self.formLayout.setLayout(0, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout_2)
        self.label = QtWidgets.QLabel(BuildingsDialog)
        self.label.setObjectName("label")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.LabelRole, self.label)
        self.building_id = QtWidgets.QLineEdit(BuildingsDialog)
        self.building_id.setObjectName("building_id")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.FieldRole, self.building_id)
        self.label_2 = QtWidgets.QLabel(BuildingsDialog)
        self.label_2.setObjectName("label_2")
        self.formLayout.setWidget(3, QtWidgets.QFormLayout.LabelRole, self.label_2)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setContentsMargins(-1, 0, -1, -1)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.height = QtWidgets.QLineEdit(BuildingsDialog)
        self.height.setEnabled(True)
        self.height.setText("")
        self.height.setObjectName("height")
        self.horizontalLayout.addWidget(self.height)
        self.formLayout.setLayout(3, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout)
        self.buttonBox = QtWidgets.QDialogButtonBox(BuildingsDialog)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.formLayout.setWidget(5, QtWidgets.QFormLayout.SpanningRole, self.buttonBox)

        self.retranslateUi(BuildingsDialog)
        self.buttonBox.accepted.connect(BuildingsDialog.accept)
        self.buttonBox.rejected.connect(BuildingsDialog.reject)
        QtCore.QMetaObject.connectSlotsByName(BuildingsDialog)
        BuildingsDialog.setTabOrder(self.building_id, self.buttonBox)

    def retranslateUi(self, BuildingsDialog):
        _translate = QtCore.QCoreApplication.translate
        BuildingsDialog.setWindowTitle(_translate("BuildingsDialog", "Building Editor"))
        self.instudy.setText(_translate("BuildingsDialog", "In Study"))
        self.label.setText(_translate("BuildingsDialog", "Building Name"))
        self.building_id.setToolTip(_translate("BuildingsDialog", "Enter a unique name for your gate"))
        self.label_2.setText(_translate("BuildingsDialog", "Buiding Height [m]"))
        self.height.setToolTip(_translate("BuildingsDialog", "Enter a height for this building"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    BuildingsDialog = QtWidgets.QDialog()
    ui = Ui_BuildingsDialog()
    ui.setupUi(BuildingsDialog)
    BuildingsDialog.show()
    sys.exit(app.exec_())
