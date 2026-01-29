from dataclasses import dataclass
from functools import partial

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


@dataclass
class GSEAssignment:
    assigned: bool
    gse_obj: object
    time: float = 10.0
    count: int = 1
    deterioration_factor: float = 1.0


class MovementEditor(QDialog):
    def __init__(
        self,
        db,
        movements_df,
        icao_to_group,
        parent=None,
        existing_assignments=None,
        gse_list=None,
        reset_mode="reset",
    ):
        super().__init__(parent)
        self.resize(1000, 700)  # Wider and taller
        self.setMinimumSize(900, 600)  # Reasonable minimum

        self.db = db
        self.movements_df = movements_df.copy()
        self.icao_to_group = icao_to_group or {}
        self.gse_list = gse_list or []
        self.gse_columns = ["type", "description", "power", "load", "fuel", "Stage"]

        # --- Aircraft group mapping (use existing mapping!) ---
        if "ac_group" not in self.movements_df.columns:
            if "aircraft" in self.movements_df.columns and self.icao_to_group:
                self.movements_df["ac_group"] = (
                    self.movements_df["aircraft"]
                    .map(self.icao_to_group)
                    .fillna("UNKNOWN")
                )
            else:
                self.movements_df["ac_group"] = "UNKNOWN"

        self.movement_codes = self.get_movement_codes()
        if not self.movement_codes:
            QMessageBox.critical(
                self, "Error", "No valid movements found in movements file!"
            )
            self.reject()
            return

        self.init_ui()
        self.setup_assignments(existing_assignments, reset_mode)
        self.current_movement_code = self.movement_codes[0]
        self.refresh_table()
        self.refresh_summary_table()

    def get_movement_codes(self):
        req_cols = ["ac_group", "gate_type", "departure_arrival"]
        missing = [c for c in req_cols if c not in self.movements_df.columns]
        if missing:
            QMessageBox.critical(
                self,
                "Missing Columns",
                f"Movements CSV is missing: {', '.join(missing)}",
            )
            return []
        # Drop duplicates on those three fields
        unique = self.movements_df.drop_duplicates(subset=req_cols)
        codes = [
            f"{row['ac_group']}/{row['gate_type']}/{row['departure_arrival']}"
            for _, row in unique.iterrows()
        ]
        return codes

    def init_ui(self):
        self.setWindowTitle("Assign GSE")
        layout = QVBoxLayout(self)

        # Movement Combo
        self.movement_combo = QComboBox()
        self.movement_combo.addItems(self.movement_codes)
        self.movement_combo.currentIndexChanged.connect(self.on_movement_change)
        layout.addWidget(self.movement_combo)

        # GSE Table
        self.table = QTableWidget()
        self.table.setColumnCount(1 + len(self.gse_columns) + 2)
        self.table.setHorizontalHeaderLabels(
            ["Assigned"] + self.gse_columns + ["Time", "Count", "Deterioration Factor"]
        )
        layout.addWidget(self.table)

        # Summary Table
        self.summary_table = QTableWidget()
        self.summary_table.setColumnCount(len(self.gse_columns) + 2)
        self.summary_table.setHorizontalHeaderLabels(
            self.gse_columns + ["Time", "Count", "Deterioration Factor"]
        )
        layout.addWidget(QLabel("Summary:"))
        layout.addWidget(self.summary_table)

        # OK/Cancel
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def setup_assignments(self, existing_assignments, reset_mode):
        self.assignments = {}

        if reset_mode == "modify" and existing_assignments:
            for code in self.movement_codes:
                # Start with existing assignments for this code
                prev_assigns = existing_assignments.get(code, [])

                # Get set of GSE types already assigned
                assigned_types = set()
                for a in prev_assigns:
                    gse_obj = (
                        a.gse_obj if hasattr(a, "gse_obj") else a.get("gse_obj", None)
                    )
                    if gse_obj:
                        gse_type = (
                            gse_obj.get("type", "")
                            if isinstance(gse_obj, dict)
                            else getattr(gse_obj, "type", "")
                        )
                        assigned_types.add(gse_type)

                # Add any GSE from gse_list that wasn't already assigned
                for g in self.gse_list:
                    gse_type = (
                        g.get("type", "")
                        if isinstance(g, dict)
                        else getattr(g, "type", "")
                    )
                    if gse_type not in assigned_types:
                        prev_assigns.append(GSEAssignment(False, g, 10.0, 1, 1.0))

                self.assignments[code] = prev_assigns
        else:
            # Reset mode - create new assignments with defaults
            for code in self.movement_codes:
                self.assignments[code] = [
                    GSEAssignment(False, g, 10.0, 1, 1.0) for g in self.gse_list
                ]

    def on_movement_change(self, idx):
        if 0 <= idx < len(self.movement_codes):
            self.current_movement_code = self.movement_codes[idx]
            self.refresh_table()
            self.refresh_summary_table()

    def update_time(self, row, value):
        code = self.current_movement_code
        self.assignments[code][row].time = value
        self.refresh_summary_table()

    def update_count(self, row, value):
        code = self.current_movement_code
        self.assignments[code][row].count = value
        self.refresh_summary_table()

    def update_deterioration(self, row, value):
        code = self.current_movement_code
        self.assignments[code][row].deterioration_factor = value
        self.refresh_summary_table()

    def refresh_table(self):
        code = self.current_movement_code
        assigns = self.assignments.get(code, [])
        self.table.setRowCount(len(assigns))
        for i, assign in enumerate(assigns):
            # Assigned checkbox in first column (no QTableWidgetItem here!)
            checkbox = QCheckBox()
            checkbox.setChecked(assign.assigned)
            checkbox.stateChanged.connect(partial(self.toggle_assigned, i))
            self.table.setCellWidget(i, 0, checkbox)

            # GSE columns (read-only)
            for j, col in enumerate(self.gse_columns):
                gse = assign.gse_obj
                val = (
                    gse.get(col, "") if isinstance(gse, dict) else getattr(gse, col, "")
                )
                item = QTableWidgetItem(str(val))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.table.setItem(i, 1 + j, item)

            # Time: editable, with spinbox
            time_spin = QDoubleSpinBox()
            time_spin.setDecimals(1)
            time_spin.setMinimum(0)
            time_spin.setMaximum(999)
            time_spin.setValue(float(assign.time))
            time_spin.valueChanged.connect(partial(self.update_time, i))
            self.table.setCellWidget(i, 1 + len(self.gse_columns), time_spin)

            # Count: editable, with spinbox
            count_spin = QSpinBox()
            count_spin.setMinimum(0)
            count_spin.setMaximum(99)
            count_spin.setValue(int(assign.count))
            count_spin.valueChanged.connect(partial(self.update_count, i))
            self.table.setCellWidget(i, 2 + len(self.gse_columns), count_spin)

            # Deterioration factor: editable, with spinbox
            det_spin = QDoubleSpinBox()
            det_spin.setDecimals(2)
            det_spin.setMinimum(0.5)
            det_spin.setMaximum(5.0)
            det_spin.setValue(float(getattr(assign, "deterioration_factor", 1.0)))
            det_spin.valueChanged.connect(partial(self.update_deterioration, i))
            self.table.setCellWidget(i, 3 + len(self.gse_columns), det_spin)

        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()

    def refresh_summary_table(self):
        rows = []
        for code, assigns in self.assignments.items():
            for a in assigns:
                if getattr(a, "assigned", False):
                    gse = a.gse_obj
                    gse_type = (
                        gse.get("type", "")
                        if isinstance(gse, dict)
                        else getattr(gse, "type", "")
                    )
                    parts = code.split("/")
                    ac_group = parts[0] if len(parts) > 0 else ""
                    gate_type = parts[1] if len(parts) > 1 else ""
                    dep_arr = parts[2] if len(parts) > 2 else ""
                    gse_desc = (
                        gse.get("description", "")
                        if isinstance(gse, dict)
                        else getattr(gse, "description", "")
                    )
                    power = (
                        gse.get("power", "")
                        if isinstance(gse, dict)
                        else getattr(gse, "power", "")
                    )

                    # Create unique key for each assignment
                    assignment_key = f"{ac_group}|{gate_type}|{dep_arr}|{gse_type}|{gse_desc}|{power}"

                    rows.append(
                        [
                            ac_group,
                            gate_type,
                            dep_arr,
                            gse_type,
                            gse_desc,
                            power,
                            a.time,
                            a.count,
                            getattr(a, "deterioration_factor", 1.0),
                            assignment_key,  # Hidden unique identifier
                        ]
                    )

        headers = [
            "Aircraft Group",
            "Gate Type",
            "Arr/Dep",
            "GSE Type",
            "Description",
            "Power",
            "Time",
            "Count",
            "Deterioration",
        ]

        self.summary_table.setRowCount(len(rows))
        self.summary_table.setColumnCount(len(headers))
        self.summary_table.setHorizontalHeaderLabels(headers)

        for i, row in enumerate(rows):
            for j, val in enumerate(row[:-1]):  # Skip the hidden key
                item = QTableWidgetItem(str(val))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.summary_table.setItem(i, j, item)

        self.summary_table.resizeColumnsToContents()

    def toggle_assigned(self, row, state):
        idx = self.movement_combo.currentIndex()
        if idx < 0:
            return
        code = self.movement_codes[idx]
        assign = self.assignments[code][row]
        assign.assigned = bool(state)
        # Optionally, could enable/disable editable fields here.
        self.refresh_summary_table()

    def get_assignments(self):
        for code, assigns in self.assignments.items():
            for i, assign in enumerate(assigns):
                # Time
                time_item = self.table.item(i, 1 + len(self.gse_columns))
                if time_item is not None:
                    try:
                        assign.time = float(time_item.text())
                    except Exception:
                        assign.time = 10.0
                # Count
                count_item = self.table.item(i, 2 + len(self.gse_columns))
                if count_item is not None:
                    try:
                        assign.count = int(count_item.text())
                    except Exception:
                        assign.count = 1
                # Deterioration Factor
                det_item = self.table.item(i, 3 + len(self.gse_columns))
                if det_item is not None:
                    try:
                        assign.deterioration_factor = float(det_item.text())
                    except Exception:
                        assign.deterioration_factor = 1.0
        return self.assignments
