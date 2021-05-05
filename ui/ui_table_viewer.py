# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/Users/sst/Dropbox/WorkOn/Projects/OpenALAQS/code/open_alaqs/ui/ui_table_viewer.ui'
#
# Created by: PyQt5 UI code generator 5.13.0
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_FormDataBrowser(object):
    def setupUi(self, FormDataBrowser):
        FormDataBrowser.setObjectName("FormDataBrowser")
        FormDataBrowser.resize(568, 353)
        self.gridLayout = QtWidgets.QGridLayout(FormDataBrowser)
        self.gridLayout.setObjectName("gridLayout")
        self.verticalLayout = QtWidgets.QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.table = QtWidgets.QComboBox(FormDataBrowser)
        self.table.setObjectName("table")
        self.verticalLayout.addWidget(self.table)
        self.data = QtWidgets.QTableWidget(FormDataBrowser)
        self.data.setObjectName("data")
        self.data.setColumnCount(0)
        self.data.setRowCount(0)
        self.verticalLayout.addWidget(self.data)
        self.buttonBox = QtWidgets.QDialogButtonBox(FormDataBrowser)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.buttonBox.sizePolicy().hasHeightForWidth())
        self.buttonBox.setSizePolicy(sizePolicy)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)
        self.verticalLayout.setStretch(0, 1)
        self.verticalLayout.setStretch(1, 1)
        self.verticalLayout.setStretch(2, 1)
        self.gridLayout.addLayout(self.verticalLayout, 0, 0, 1, 1)

        self.retranslateUi(FormDataBrowser)
        self.buttonBox.accepted.connect(FormDataBrowser.accept)
        self.buttonBox.rejected.connect(FormDataBrowser.reject)
        QtCore.QMetaObject.connectSlotsByName(FormDataBrowser)
        FormDataBrowser.setTabOrder(self.table, self.data)
        FormDataBrowser.setTabOrder(self.data, self.buttonBox)

    def retranslateUi(self, FormDataBrowser):
        _translate = QtCore.QCoreApplication.translate
        FormDataBrowser.setWindowTitle(_translate("FormDataBrowser", "OpenALAQS - Browse Data"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    FormDataBrowser = QtWidgets.QDialog()
    ui = Ui_FormDataBrowser()
    ui.setupUi(FormDataBrowser)
    FormDataBrowser.show()
    sys.exit(app.exec_())
