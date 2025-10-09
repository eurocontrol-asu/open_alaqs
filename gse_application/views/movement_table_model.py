# views/movement_table_model.py

from PyQt5.QtCore import QAbstractTableModel, Qt, QVariant
from model.types import Movement

class MovementTableModel(QAbstractTableModel):
    HEADERS = ["Gate type", "Aircraft group", "GSE type", "Count", "Time"]

    def __init__(self, movements):
        super().__init__()
        self.movements = movements

    def rowCount(self, parent=None):
        return len(self.movements)

    def columnCount(self, parent=None):
        return len(self.HEADERS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        movement = self.movements[index.row()]
        field = self.HEADERS[index.column()]
        if role == Qt.DisplayRole:
            return str(getattr(movement, field))
        return QVariant()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return QVariant()
