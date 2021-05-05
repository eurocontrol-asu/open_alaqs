# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/Users/sst/Dropbox/WorkOn/Projects/OpenALAQS/code/open_alaqs/ui/ui_logfile.ui'
#
# Created by: PyQt5 UI code generator 5.13.0
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_DialogLogfile(object):
    def setupUi(self, DialogLogfile):
        DialogLogfile.setObjectName("DialogLogfile")
        DialogLogfile.resize(539, 406)
        self.gridLayout = QtWidgets.QGridLayout(DialogLogfile)
        self.gridLayout.setObjectName("gridLayout")
        self.verticalLayout = QtWidgets.QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.logfile_text_area = QtWidgets.QTextEdit(DialogLogfile)
        self.logfile_text_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.logfile_text_area.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        self.logfile_text_area.setObjectName("logfile_text_area")
        self.verticalLayout.addWidget(self.logfile_text_area)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.clear = QtWidgets.QPushButton(DialogLogfile)
        self.clear.setObjectName("clear")
        self.horizontalLayout.addWidget(self.clear)
        self.save = QtWidgets.QPushButton(DialogLogfile)
        self.save.setObjectName("save")
        self.horizontalLayout.addWidget(self.save)
        self.close = QtWidgets.QPushButton(DialogLogfile)
        self.close.setObjectName("close")
        self.horizontalLayout.addWidget(self.close)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.gridLayout.addLayout(self.verticalLayout, 0, 0, 1, 1)

        self.retranslateUi(DialogLogfile)
        QtCore.QMetaObject.connectSlotsByName(DialogLogfile)
        DialogLogfile.setTabOrder(self.logfile_text_area, self.clear)
        DialogLogfile.setTabOrder(self.clear, self.save)
        DialogLogfile.setTabOrder(self.save, self.close)

    def retranslateUi(self, DialogLogfile):
        _translate = QtCore.QCoreApplication.translate
        DialogLogfile.setWindowTitle(_translate("DialogLogfile", "OpenALAQS - Log File"))
        self.clear.setText(_translate("DialogLogfile", "Clear"))
        self.save.setText(_translate("DialogLogfile", "Save"))
        self.close.setText(_translate("DialogLogfile", "Close"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    DialogLogfile = QtWidgets.QDialog()
    ui = Ui_DialogLogfile()
    ui.setupUi(DialogLogfile)
    DialogLogfile.show()
    sys.exit(app.exec_())
