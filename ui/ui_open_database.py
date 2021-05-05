# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/Users/sst/Dropbox/WorkOn/Projects/OpenALAQS/code/open_alaqs/ui/ui_open_database.ui'
#
# Created by: PyQt5 UI code generator 5.13.0
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets
# from qgis.PyQt import QtWidgets, QtCore, QtGui

class Ui_DialogOpenDatabase(object):
    def setupUi(self, DialogOpenDatabase):
        DialogOpenDatabase.setObjectName("DialogOpenDatabase")
        DialogOpenDatabase.resize(559, 74)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(DialogOpenDatabase.sizePolicy().hasHeightForWidth())
        DialogOpenDatabase.setSizePolicy(sizePolicy)
        DialogOpenDatabase.setModal(True)
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(DialogOpenDatabase)
        self.verticalLayout_2.setSizeConstraint(QtWidgets.QLayout.SetFixedSize)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setContentsMargins(-1, 0, -1, -1)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.pushButtonBrowse = QtWidgets.QPushButton(DialogOpenDatabase)
        self.pushButtonBrowse.setObjectName("pushButtonBrowse")
        self.horizontalLayout.addWidget(self.pushButtonBrowse)
        self.lineEditFilename = QtWidgets.QLineEdit(DialogOpenDatabase)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.lineEditFilename.sizePolicy().hasHeightForWidth())
        self.lineEditFilename.setSizePolicy(sizePolicy)
        self.lineEditFilename.setMinimumSize(QtCore.QSize(400, 0))
        self.lineEditFilename.setText("")
        self.lineEditFilename.setObjectName("lineEditFilename")
        self.horizontalLayout.addWidget(self.lineEditFilename)
        self.verticalLayout_2.addLayout(self.horizontalLayout)
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setContentsMargins(-1, 0, -1, -1)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout_2.addItem(spacerItem)
        self.pushButtonOpenDatabase = QtWidgets.QPushButton(DialogOpenDatabase)
        self.pushButtonOpenDatabase.setObjectName("pushButtonOpenDatabase")
        self.horizontalLayout_2.addWidget(self.pushButtonOpenDatabase)
        self.pushButtonCancel = QtWidgets.QPushButton(DialogOpenDatabase)
        self.pushButtonCancel.setObjectName("pushButtonCancel")
        self.horizontalLayout_2.addWidget(self.pushButtonCancel)
        self.verticalLayout_2.addLayout(self.horizontalLayout_2)

        self.retranslateUi(DialogOpenDatabase)
        QtCore.QMetaObject.connectSlotsByName(DialogOpenDatabase)

    def retranslateUi(self, DialogOpenDatabase):
        _translate = QtCore.QCoreApplication.translate
        DialogOpenDatabase.setWindowTitle(_translate("DialogOpenDatabase", "Open an existing ALAQS database"))
        self.pushButtonBrowse.setText(_translate("DialogOpenDatabase", "Browse"))
        self.pushButtonOpenDatabase.setText(_translate("DialogOpenDatabase", "Open Project Database"))
        self.pushButtonCancel.setText(_translate("DialogOpenDatabase", "Cancel"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    DialogOpenDatabase = QtWidgets.QDialog()
    ui = Ui_DialogOpenDatabase()
    ui.setupUi(DialogOpenDatabase)
    DialogOpenDatabase.show()
    sys.exit(app.exec_())
