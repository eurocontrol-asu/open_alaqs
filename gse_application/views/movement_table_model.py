# views/movement_table_model.py

from qgis.core import NULL
from qgis.PyQt.QtCore import QAbstractTableModel, Qt


class MovementTableModel(QAbstractTableModel):
    HEADERS = ["Gate type", "Aircraft group", "GSE type", "Count", "Time"]

    def __init__(self, movements):
        super().__init__()
        self.movements = movements

    def rowCount(self, parent=None):
        return len(self.movements)

    def columnCount(self, parent=None):
        return len(self.HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return NULL
        movement = self.movements[index.row()]
        field = self.HEADERS[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return str(getattr(movement, field))
        return NULL

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
        ):
            return self.HEADERS[section]
        return NULL
