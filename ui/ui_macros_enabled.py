# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ui_macros_enabled.ui'
#
# Created by: PyQt5 UI code generator 5.15.4
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_DialogEnabledMacros(object):
    def setupUi(self, DialogEnabledMacros):
        DialogEnabledMacros.setObjectName("DialogEnabledMacros")
        DialogEnabledMacros.setEnabled(True)
        DialogEnabledMacros.resize(277, 120)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(DialogEnabledMacros.sizePolicy().hasHeightForWidth())
        DialogEnabledMacros.setSizePolicy(sizePolicy)
        DialogEnabledMacros.setMinimumSize(QtCore.QSize(277, 120))
        DialogEnabledMacros.setMaximumSize(QtCore.QSize(277, 120))
        DialogEnabledMacros.setSizeGripEnabled(False)
        self.pushButton = QtWidgets.QPushButton(DialogEnabledMacros)
        self.pushButton.setGeometry(QtCore.QRect(190, 90, 75, 24))
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.pushButton.sizePolicy().hasHeightForWidth())
        self.pushButton.setSizePolicy(sizePolicy)
        self.pushButton.setObjectName("pushButton")
        self.label = QtWidgets.QLabel(DialogEnabledMacros)
        self.label.setEnabled(True)
        self.label.setGeometry(QtCore.QRect(10, 10, 251, 80))
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label.sizePolicy().hasHeightForWidth())
        self.label.setSizePolicy(sizePolicy)
        self.label.setTextFormat(QtCore.Qt.AutoText)
        self.label.setWordWrap(True)
        self.label.setObjectName("label")

        self.retranslateUi(DialogEnabledMacros)
        QtCore.QMetaObject.connectSlotsByName(DialogEnabledMacros)

    def retranslateUi(self, DialogEnabledMacros):
        _translate = QtCore.QCoreApplication.translate
        DialogEnabledMacros.setWindowTitle(_translate("DialogEnabledMacros", "OpenALAQS - Macros Enabled"))
        self.pushButton.setText(_translate("DialogEnabledMacros", "Ok"))
        self.label.setText(_translate("DialogEnabledMacros", "To use the Open-ALAQS plugin, Python macros need to be enabled. We have enabled them for you. To change this go to \'Settings > Options > General > Enable macros\'"))
from . import alaqs_resources_rc