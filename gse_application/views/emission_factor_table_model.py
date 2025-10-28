# views/emission_factor_table_model.py

from PyQt5.QtCore import QAbstractTableModel, Qt, QVariant


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

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        factor = self.factors[index.row()]
        field = self.HEADERS[index.column()]
        if role == Qt.DisplayRole:
            return str(getattr(factor, field))
        return QVariant()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return QVariant()
