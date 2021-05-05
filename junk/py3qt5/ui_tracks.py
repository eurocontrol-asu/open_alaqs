# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/Users/sst/Dropbox/WorkOn/Projects/OpenALAQS/code/open_alaqs/ui/ui_tracks.ui'
#
# Created by: PyQt5 UI code generator 5.13.0
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_TracksDialog(object):
    def setupUi(self, TracksDialog):
        TracksDialog.setObjectName("TracksDialog")
        TracksDialog.resize(292, 153)
        self.formLayout = QtWidgets.QFormLayout(TracksDialog)
        self.formLayout.setObjectName("formLayout")
        self.label = QtWidgets.QLabel(TracksDialog)
        self.label.setObjectName("label")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.LabelRole, self.label)
        self.track_id = QtWidgets.QLineEdit(TracksDialog)
        self.track_id.setObjectName("track_id")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.FieldRole, self.track_id)
        self.label_5 = QtWidgets.QLabel(TracksDialog)
        self.label_5.setObjectName("label_5")
        self.formLayout.setWidget(3, QtWidgets.QFormLayout.LabelRole, self.label_5)
        self.runway = QtWidgets.QComboBox(TracksDialog)
        self.runway.setObjectName("runway")
        self.formLayout.setWidget(3, QtWidgets.QFormLayout.FieldRole, self.runway)
        self.label_2 = QtWidgets.QLabel(TracksDialog)
        self.label_2.setObjectName("label_2")
        self.formLayout.setWidget(4, QtWidgets.QFormLayout.LabelRole, self.label_2)
        self.departure_arrival = QtWidgets.QComboBox(TracksDialog)
        self.departure_arrival.setObjectName("departure_arrival")
        self.formLayout.setWidget(4, QtWidgets.QFormLayout.FieldRole, self.departure_arrival)
        self.buttonBox = QtWidgets.QDialogButtonBox(TracksDialog)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.formLayout.setWidget(5, QtWidgets.QFormLayout.SpanningRole, self.buttonBox)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setContentsMargins(-1, 0, -1, -1)
        self.horizontalLayout.setObjectName("horizontalLayout")
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.instudy = QtWidgets.QCheckBox(TracksDialog)
        self.instudy.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.instudy.setChecked(True)
        self.instudy.setObjectName("instudy")
        self.horizontalLayout.addWidget(self.instudy)
        self.formLayout.setLayout(0, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout)

        self.retranslateUi(TracksDialog)
        self.buttonBox.accepted.connect(TracksDialog.accept)
        self.buttonBox.rejected.connect(TracksDialog.reject)
        QtCore.QMetaObject.connectSlotsByName(TracksDialog)
        TracksDialog.setTabOrder(self.track_id, self.runway)
        TracksDialog.setTabOrder(self.runway, self.departure_arrival)
        TracksDialog.setTabOrder(self.departure_arrival, self.buttonBox)

    def retranslateUi(self, TracksDialog):
        _translate = QtCore.QCoreApplication.translate
        TracksDialog.setWindowTitle(_translate("TracksDialog", "Track Editor"))
        self.label.setText(_translate("TracksDialog", "Name"))
        self.track_id.setToolTip(_translate("TracksDialog", "Enter a unique name for your track"))
        self.label_5.setText(_translate("TracksDialog", "Runway"))
        self.runway.setToolTip(_translate("TracksDialog", "Choose the runway this track relates to"))
        self.label_2.setText(_translate("TracksDialog", "Arrival/Departure"))
        self.departure_arrival.setToolTip(_translate("TracksDialog", "Choose whether this is an arrival or departure track"))
        self.instudy.setText(_translate("TracksDialog", "In Study"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    TracksDialog = QtWidgets.QDialog()
    ui = Ui_TracksDialog()
    ui.setupUi(TracksDialog)
    TracksDialog.show()
    sys.exit(app.exec_())
