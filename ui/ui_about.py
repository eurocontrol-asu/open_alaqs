# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/Users/sst/Dropbox/WorkOn/Projects/OpenALAQS/code/open_alaqs/ui/ui_about.ui'
#
# Created by: PyQt5 UI code generator 5.13.0
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets
# from qgis.PyQt import QtGui, QtCore, QtWidgets

class Ui_DialogAbout(object):
    def setupUi(self, DialogAbout):
        DialogAbout.setObjectName("DialogAbout")
        DialogAbout.setEnabled(True)
        DialogAbout.resize(593, 156)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(DialogAbout.sizePolicy().hasHeightForWidth())
        DialogAbout.setSizePolicy(sizePolicy)
        DialogAbout.setSizeGripEnabled(False)
        self.formLayout = QtWidgets.QFormLayout(DialogAbout)
        self.formLayout.setSizeConstraint(QtWidgets.QLayout.SetFixedSize)
        self.formLayout.setObjectName("formLayout")
        self.label = QtWidgets.QLabel(DialogAbout)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label.sizePolicy().hasHeightForWidth())
        self.label.setSizePolicy(sizePolicy)
        self.label.setObjectName("label")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.label)
        self.label_2 = QtWidgets.QLabel(DialogAbout)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_2.sizePolicy().hasHeightForWidth())
        self.label_2.setSizePolicy(sizePolicy)
        self.label_2.setMaximumSize(QtCore.QSize(101, 61))
        self.label_2.setText("")
        self.label_2.setPixmap(QtGui.QPixmap(":/logo/eurocontrol_logo.png"))
        self.label_2.setScaledContents(True)
        self.label_2.setObjectName("label_2")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.label_2)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setContentsMargins(-1, 0, -1, -1)
        self.horizontalLayout.setObjectName("horizontalLayout")
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)

        # self.AddWatermarkButton = QtWidgets.QPushButton(DialogAbout)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        # sizePolicy.setHeightForWidth(self.AddWatermarkButton.sizePolicy().hasHeightForWidth())
        # self.AddWatermarkButton.setSizePolicy(sizePolicy)
        # self.AddWatermarkButton.setMaximumSize(QtCore.QSize(121, 23))
        # self.AddWatermarkButton.setObjectName("AddWatermarkButton")
        # self.horizontalLayout.addWidget(self.AddWatermarkButton)
        self.formLayout.setLayout(3, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout)

        self.retranslateUi(DialogAbout)
        QtCore.QMetaObject.connectSlotsByName(DialogAbout)

    def retranslateUi(self, DialogAbout):
        _translate = QtCore.QCoreApplication.translate
        DialogAbout.setWindowTitle(_translate("DialogAbout", "About"))
        self.label.setText(_translate("DialogAbout",
                                      "<html><head/><body><p align=\"center\"><span style=\" font-size:12pt; "
                                      "font-weight:600;\">Open ALAQS: Airport Local Air Quality Studies</span><br/>"
                                      "Version 3.0 (November 2019)</p><p align=\"center\">"
                                      "This is a version of the ALAQS local air quality software released for QGIS3.<br/>"
                                      "It is provided free of charge under the GPL3 software Licence.</p><p align=\"center\">"
                                      "For more information, contact open-alaqs@eurocontrol.int</p></body></html>"))
        # self.AddWatermarkButton.setText(_translate("DialogAbout", "Add watermark to layer"))

# from . import alaqs_resources_rc

if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    DialogAbout = QtWidgets.QDialog()
    ui = Ui_DialogAbout()
    ui.setupUi(DialogAbout)
    DialogAbout.show()
    sys.exit(app.exec_())

    # from PyQt5 import QtGui, QtCore, uic, QtWidgets
    # from PyQt5.QtWidgets import QMainWindow, QApplication
    # from PyQt5.QtCore import *
    #
    # uifile = "./ui_about.ui"
    # Ui_MainWindow, QtBaseClass = uic.loadUiType(uifile)
    # Ui_Dialog = uic.loadUiType(uifile)

