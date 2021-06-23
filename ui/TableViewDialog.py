# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/Users/sst/Dropbox/WorkOn/Projects/OpenALAQS/code/open_alaqs/alaqs_core/modules/ui/TableViewDialog.ui'
#
# Created by: PyQt5 UI code generator 5.13.0
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_TableViewDialog(object):
    def setupUi(self, TableViewDialog):
        TableViewDialog.setObjectName("TableViewDialog")
        TableViewDialog.resize(707, 540)
        self.verticalLayout_3 = QtWidgets.QVBoxLayout(TableViewDialog)
        self.verticalLayout_3.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.data_table = QtWidgets.QTableWidget(TableViewDialog)
        self.data_table.setObjectName("data_table")
        self.data_table.setColumnCount(0)
        self.data_table.setRowCount(0)
        self.verticalLayout_3.addWidget(self.data_table)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.buttonBox = QtWidgets.QDialogButtonBox(TableViewDialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.buttonBox.sizePolicy().hasHeightForWidth())
        self.buttonBox.setSizePolicy(sizePolicy)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Close)
        self.buttonBox.setCenterButtons(False)
        self.buttonBox.setObjectName("buttonBox")
        self.horizontalLayout.addWidget(self.buttonBox)
        self.verticalLayout_3.addLayout(self.horizontalLayout)

        self.retranslateUi(TableViewDialog)
        self.buttonBox.rejected.connect(TableViewDialog.reject)
        self.buttonBox.accepted.connect(TableViewDialog.accept)
        QtCore.QMetaObject.connectSlotsByName(TableViewDialog)

    def retranslateUi(self, TableViewDialog):
        _translate = QtCore.QCoreApplication.translate
        TableViewDialog.setWindowTitle(_translate("TableViewDialog", "OpenALAQS - Results"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    TableViewDialog = QtWidgets.QDialog()
    ui = Ui_TableViewDialog()
    ui.setupUi(TableViewDialog)
    TableViewDialog.show()
    sys.exit(app.exec_())
