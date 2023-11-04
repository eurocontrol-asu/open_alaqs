# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/Users/sst/Dropbox/WorkOn/Projects/OpenALAQS/code/open_alaqs/ui/ui_calculation_dialog.ui'
#
# Created by: PyQt5 UI code generator 5.13.0
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog(object):
    def setupUi(self, Dialog):
        Dialog.setObjectName("Dialog")
        Dialog.resize(540, 424)
        self.pushButton = QtWidgets.QPushButton(Dialog)
        self.pushButton.setGeometry(QtCore.QRect(324, 380, 101, 23))
        self.pushButton.setObjectName("pushButton")
        self.listView = QtWidgets.QListView(Dialog)
        self.listView.setGeometry(QtCore.QRect(10, 90, 221, 161))
        self.listView.setObjectName("listView")
        self.label = QtWidgets.QLabel(Dialog)
        self.label.setGeometry(QtCore.QRect(20, 100, 241, 101))
        self.label.setObjectName("label")
        self.label_3 = QtWidgets.QLabel(Dialog)
        self.label_3.setGeometry(QtCore.QRect(10, 70, 101, 16))
        self.label_3.setObjectName("label_3")
        self.pushButton_2 = QtWidgets.QPushButton(Dialog)
        self.pushButton_2.setGeometry(QtCore.QRect(440, 380, 75, 23))
        self.pushButton_2.setObjectName("pushButton_2")
        self.pushButton_3 = QtWidgets.QPushButton(Dialog)
        self.pushButton_3.setGeometry(QtCore.QRect(270, 260, 101, 23))
        self.pushButton_3.setObjectName("pushButton_3")
        self.label_4 = QtWidgets.QLabel(Dialog)
        self.label_4.setGeometry(QtCore.QRect(270, 70, 101, 16))
        self.label_4.setObjectName("label_4")
        self.listView_2 = QtWidgets.QListView(Dialog)
        self.listView_2.setGeometry(QtCore.QRect(270, 90, 221, 161))
        self.listView_2.setObjectName("listView_2")
        self.label_2 = QtWidgets.QLabel(Dialog)
        self.label_2.setGeometry(QtCore.QRect(280, 100, 241, 101))
        self.label_2.setObjectName("label_2")

        self.retranslateUi(Dialog)
        QtCore.QMetaObject.connectSlotsByName(Dialog)

    def retranslateUi(self, Dialog):
        _translate = QtCore.QCoreApplication.translate
        Dialog.setWindowTitle(_translate("Dialog", "OpenALAQS - Dialog"))
        self.pushButton.setText(_translate("Dialog", "Run calculation"))
        self.label.setText(_translate("Dialog", "<html><head/><body><p>Calculate emissions of stationary sources</p><p>Calculate roadway emissions</p><p>Calculate aircraft emissions</p><p>Save results to SQL database</p><p><br/></p></body></html>"))
        self.label_3.setText(_translate("Dialog", "Available modules"))
        self.pushButton_2.setText(_translate("Dialog", "Cancel"))
        self.pushButton_3.setText(_translate("Dialog", "Configure module"))
        self.label_4.setText(_translate("Dialog", "Selected modules"))
        self.label_2.setText(_translate("Dialog", "<html><head/><body><p>Calculate aircraft emissions</p><p>Save results to SQL database</p><p><br/></p></body></html>"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog = QtWidgets.QDialog()
    ui = Ui_Dialog()
    ui.setupUi(Dialog)
    Dialog.show()
    sys.exit(app.exec_())
