# views/gse_table_model.py

from model.gse_types import GSE
from qgis.core import NULL
from qgis.PyQt.QtCore import QAbstractTableModel, QModelIndex, Qt
from qgis.PyQt.QtWidgets import QMessageBox


class GSETableModel(QAbstractTableModel):
    def __init__(self, gse_list):
        super().__init__()
        self._gse_list = gse_list
        self._headers = [
            "type",
            "description",
            "power",
            "load",
            "fuel",
            "Stage",
            "time",
            "deterioration_factor",
        ]
        self._valid_types = [
            "GPU",
            "PCA",
            "Baggage Tractor",
            "Pushback Tractor",
            "Catering Truck",
            "Fuel Truck",
            "Lavatory Truck",
            "Water Truck",
            "Cargo Loader",
            "Belt Loader",
            "Passenger Stairs",
            "Other",
            "GSE",
        ]
        self._valid_stages = [
            "Stage I",
            "Stage II",
            "Stage IIIA",
            "Stage IIIB",
            "Stage IV",
            "Stage V",
        ]
        self._valid_fuels = ["Diesel", "Gasoline", "Electric", "Hybrid"]

    def rowCount(self, parent=None):
        return len(self._gse_list)

    def columnCount(self, parent=None):
        return len(self._headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return NULL

        row = index.row()
        col = index.column()

        if row >= len(self._gse_list):
            return NULL

        gse = self._gse_list[row]
        attr = self._headers[col]

        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            return str(getattr(gse, attr, ""))

        return NULL

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False

        row = index.row()
        col = index.column()

        if row >= len(self._gse_list):
            return False

        gse = self._gse_list[row]
        attr = self._headers[col]

        # Validate the input
        if not self._validate_input(attr, value):
            return False

        # Convert value to appropriate type
        try:
            if attr in ["power", "load", "time", "deterioration_factor"]:
                value = float(value)
            else:
                value = str(value)
        except ValueError:
            QMessageBox.warning(
                None, "Invalid Input", f"Invalid value for {attr}: {value}"
            )
            return False

        # Set the value
        setattr(gse, attr, value)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
        return True

    def _validate_input(self, attr, value):
        """Validate input based on attribute type"""
        try:
            if attr == "type":
                if str(value) not in self._valid_types:
                    QMessageBox.warning(
                        None,
                        "Invalid Type",
                        f"Type must be one of: {", ".join(self._valid_types)}",
                    )
                    return False
            elif attr == "Stage":
                if str(value) not in self._valid_stages:
                    QMessageBox.warning(
                        None,
                        "Invalid Stage",
                        f"Stage must be one of: {", ".join(self._valid_stages)}",
                    )
                    return False
            elif attr == "fuel":
                if str(value) not in self._valid_fuels:
                    QMessageBox.warning(
                        None,
                        "Invalid Fuel",
                        f"Fuel must be one of: {", ".join(self._valid_fuels)}",
                    )
                    return False
            elif attr in ["power", "load", "time", "deterioration_factor"]:
                val = float(value)
                if val < 0:
                    QMessageBox.warning(None, "Invalid Value", f"{attr} must be >= 0")
                    return False
                if attr == "deterioration_factor" and val > 1.0:
                    QMessageBox.warning(
                        None,
                        "Invalid Value",
                        "Deterioration factor should typically be <= 1.0",
                    )
                    return False
            return True
        except ValueError:
            QMessageBox.warning(
                None, "Invalid Input", f"Invalid numeric value for {attr}: {value}"
            )
            return False

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.ItemIsEnabled
        return (
            Qt.ItemFlag.ItemIsEditable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return NULL
        if orientation == Qt.Orientation.Horizontal and section < len(self._headers):
            return self._headers[section]
        return NULL

    def insertRows(self, row, count, parent=None):
        """Insert new rows"""
        self.beginInsertRows(parent or QModelIndex(), row, row + count - 1)
        for i in range(count):
            # Create a new GSE with default values
            new_gse = GSE(
                type=self._valid_types[0],  # Default to first valid type
                description="Description",
                power=0.0,
                load=1.0,
                fuel=self._valid_fuels[0],  # Default to first valid fuel
                Stage=self._valid_stages[2],  # Default to Stage IIIA
                time=0.0,
                deterioration_factor=1.0,
            )
            self._gse_list.insert(row + i, new_gse)
        self.endInsertRows()
        return True

    def removeRows(self, row, count, parent=None):
        """Remove rows"""
        if row < 0 or row + count > len(self._gse_list):
            return False

        self.beginRemoveRows(parent or QModelIndex(), row, row + count - 1)
        for i in range(count):
            self._gse_list.pop(row)
        self.endRemoveRows()
        return True

    def get_gse_list(self):
        """Return the current GSE list"""
        return self._gse_list
