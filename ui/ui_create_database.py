# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/Users/sst/Dropbox/WorkOn/Projects/OpenALAQS/code/open_alaqs/ui/ui_create_database.ui'
#
# Created by: PyQt5 UI code generator 5.13.0
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_DialogCreateDatabase(object):
    def setupUi(self, DialogCreateDatabase):
        DialogCreateDatabase.setObjectName("DialogCreateDatabase")
        DialogCreateDatabase.resize(400, 112)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(DialogCreateDatabase.sizePolicy().hasHeightForWidth())
        DialogCreateDatabase.setSizePolicy(sizePolicy)
        DialogCreateDatabase.setModal(True)
        self.verticalLayout = QtWidgets.QVBoxLayout(DialogCreateDatabase)
        self.verticalLayout.setObjectName("verticalLayout")
        self.formLayout = QtWidgets.QFormLayout()
        self.formLayout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.formLayout.setContentsMargins(-1, 0, -1, -1)
        self.formLayout.setObjectName("formLayout")
        self.label_5 = QtWidgets.QLabel(DialogCreateDatabase)
        self.label_5.setObjectName("label_5")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.label_5)
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_3.setContentsMargins(-1, 0, -1, -1)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.lineEditDatabaseName = QtWidgets.QLineEdit(DialogCreateDatabase)
        self.lineEditDatabaseName.setObjectName("lineEditDatabaseName")
        self.horizontalLayout_3.addWidget(self.lineEditDatabaseName)
        self.label = QtWidgets.QLabel(DialogCreateDatabase)
        self.label.setObjectName("label")
        self.horizontalLayout_3.addWidget(self.label)
        self.formLayout.setLayout(0, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout_3)
        self.label_6 = QtWidgets.QLabel(DialogCreateDatabase)
        self.label_6.setObjectName("label_6")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.label_6)
        self.horizontalLayout_4 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_4.setContentsMargins(-1, 0, -1, -1)
        self.horizontalLayout_4.setObjectName("horizontalLayout_4")
        self.lineEditDatabaseDirectory = QtWidgets.QLineEdit(DialogCreateDatabase)
        self.lineEditDatabaseDirectory.setObjectName("lineEditDatabaseDirectory")
        self.horizontalLayout_4.addWidget(self.lineEditDatabaseDirectory)
        self.pushButtonBrowse = QtWidgets.QPushButton(DialogCreateDatabase)
        self.pushButtonBrowse.setObjectName("pushButtonBrowse")
        self.horizontalLayout_4.addWidget(self.pushButtonBrowse)
        self.formLayout.setLayout(1, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout_4)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setContentsMargins(-1, 0, 0, -1)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.formLayout.setLayout(2, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout)
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setContentsMargins(-1, 0, -1, -1)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout_2.addItem(spacerItem)
        self.pushButtonCreateDatabase = QtWidgets.QPushButton(DialogCreateDatabase)
        self.pushButtonCreateDatabase.setObjectName("pushButtonCreateDatabase")
        self.horizontalLayout_2.addWidget(self.pushButtonCreateDatabase)
        self.pushButtonCancel = QtWidgets.QPushButton(DialogCreateDatabase)
        self.pushButtonCancel.setObjectName("pushButtonCancel")
        self.horizontalLayout_2.addWidget(self.pushButtonCancel)
        self.formLayout.setLayout(3, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout_2)
        self.verticalLayout.addLayout(self.formLayout)

        self.retranslateUi(DialogCreateDatabase)
        QtCore.QMetaObject.connectSlotsByName(DialogCreateDatabase)

    def retranslateUi(self, DialogCreateDatabase):
        _translate = QtCore.QCoreApplication.translate
        DialogCreateDatabase.setWindowTitle(_translate("DialogCreateDatabase", "OpenALAQS - Create new ALAQS database"))
        self.label_5.setText(_translate("DialogCreateDatabase", "File Name"))
        self.label.setText(_translate("DialogCreateDatabase", ".alaqs"))
        self.label_6.setText(_translate("DialogCreateDatabase", "File Directory"))
        self.pushButtonBrowse.setText(_translate("DialogCreateDatabase", "Browse..."))
        self.pushButtonCreateDatabase.setText(_translate("DialogCreateDatabase", "Create Project Database"))
        self.pushButtonCancel.setText(_translate("DialogCreateDatabase", "Cancel"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    DialogCreateDatabase = QtWidgets.QDialog()
    ui = Ui_DialogCreateDatabase()
    ui.setupUi(DialogCreateDatabase)
    DialogCreateDatabase.show()
    sys.exit(app.exec_())
