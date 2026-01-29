# views/emission_factor_table_model.py

from qgis.core import NULL
from qgis.PyQt.QtCore import QAbstractTableModel, Qt


class EmissionFactorTableModel(QAbstractTableModel):
    HEADERS = [
        "stage",
        "category",
        "power_range",
        "valid_as_of",
        "CO_g_per_kWh",
        "HC_g_per_kWh",
        "NOx_g_per_kWh",
        "PM_g_per_kWh",
        "SOx_g_per_kWh",
    ]

    def __init__(self, factors):
        super().__init__()
        self.factors = factors

    def rowCount(self, parent=None):
        return len(self.factors)

    def columnCount(self, parent=None):
        return len(self.HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return NULL
        factor = self.factors[index.row()]
        field = self.HEADERS[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return str(getattr(factor, field))
        return NULL

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
        ):
            return self.HEADERS[section]
        return NULL
