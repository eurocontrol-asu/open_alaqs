# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/Users/sst/Dropbox/WorkOn/Projects/OpenALAQS/code/open_alaqs/ui/ui_movements.ui'
#
# Created by: PyQt5 UI code generator 5.13.0
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_FormMovements(object):
    def setupUi(self, FormMovements):
        FormMovements.setObjectName("FormMovements")
        FormMovements.resize(400, 110)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(FormMovements.sizePolicy().hasHeightForWidth())
        FormMovements.setSizePolicy(sizePolicy)
        FormMovements.setModal(True)
        self.load = QtWidgets.QPushButton(FormMovements)
        self.load.setGeometry(QtCore.QRect(130, 70, 131, 31))
        self.load.setObjectName("load")
        self.cancel = QtWidgets.QPushButton(FormMovements)
        self.cancel.setGeometry(QtCore.QRect(270, 70, 121, 31))
        self.cancel.setObjectName("cancel")
        self.label_7 = QtWidgets.QLabel(FormMovements)
        self.label_7.setGeometry(QtCore.QRect(10, 10, 181, 20))
        self.label_7.setObjectName("label_7")
        self.filename = QtWidgets.QLineEdit(FormMovements)
        self.filename.setGeometry(QtCore.QRect(10, 40, 301, 20))
        self.filename.setText("")
        self.filename.setObjectName("filename")
        self.browse = QtWidgets.QPushButton(FormMovements)
        self.browse.setGeometry(QtCore.QRect(320, 40, 71, 23))
        self.browse.setObjectName("browse")

        self.retranslateUi(FormMovements)
        QtCore.QMetaObject.connectSlotsByName(FormMovements)
        FormMovements.setTabOrder(self.filename, self.browse)
        FormMovements.setTabOrder(self.browse, self.load)
        FormMovements.setTabOrder(self.load, self.cancel)

    def retranslateUi(self, FormMovements):
        _translate = QtCore.QCoreApplication.translate
        FormMovements.setWindowTitle(_translate("FormMovements", "Open an existing ALAQS database"))
        self.load.setText(_translate("FormMovements", "Load Movement File"))
        self.cancel.setText(_translate("FormMovements", "Cancel"))
        self.label_7.setText(_translate("FormMovements", "<html><head/><body><p><span style=\" font-size:10pt;\">Select a movement journal to open:</span></p></body></html>"))
        self.browse.setText(_translate("FormMovements", "Browse"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    FormMovements = QtWidgets.QDialog()
    ui = Ui_FormMovements()
    ui.setupUi(FormMovements)
    FormMovements.show()
    sys.exit(app.exec_())
