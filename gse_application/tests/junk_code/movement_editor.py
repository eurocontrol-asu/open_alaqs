from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QTableWidget,
    QTableWidgetItem, QCheckBox, QPushButton, QMessageBox, QSpinBox, QDoubleSpinBox
)
from PyQt5.QtCore import Qt
from dataclasses import dataclass
from functools import partial

@dataclass
class GSEAssignment:
    assigned: bool
    gse_obj: object
    time: float = 10.0
    count: int = 1
    deterioration_factor: float = 1.0

class MovementEditor(QDialog):
    def __init__(
        self, db, movements_df, icao_to_group, parent=None,
        existing_assignments=None, gse_list=None, reset_mode="reset"
    ):
        super().__init__(parent)
        self.resize(1000, 700)          # Wider and taller
        self.setMinimumSize(900, 600)   # Reasonable minimum

        self.db = db
        self.movements_df = movements_df.copy()
        self.icao_to_group = icao_to_group or {}
        self.gse_list = gse_list or []
        self.gse_columns = ['type', 'description', 'power', 'load', 'fuel', 'Stage']

        # --- Aircraft group mapping (use existing mapping!) ---
        if "ac_group" not in self.movements_df.columns:
            if "aircraft" in self.movements_df.columns and self.icao_to_group:
                self.movements_df["ac_group"] = self.movements_df["aircraft"].map(self.icao_to_group).fillna("UNKNOWN")
            else:
                self.movements_df["ac_group"] = "UNKNOWN"

        self.movement_codes = self.get_movement_codes()
        if not self.movement_codes:
            QMessageBox.critical(self, "Error", "No valid movements found in movements file!")
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
            QMessageBox.critical(self, "Missing Columns", f"Movements CSV is missing: {', '.join(missing)}")
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
        self.table.setHorizontalHeaderLabels(["Assigned"] + self.gse_columns + ["Time", "Count", "Deterioration Factor"])
        layout.addWidget(self.table)

        # Summary Table
        self.summary_table = QTableWidget()
        self.summary_table.setColumnCount(len(self.gse_columns) + 2)
        self.summary_table.setHorizontalHeaderLabels(self.gse_columns + ["Time", "Count", "Deterioration Factor"])
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
        if reset_mode == "append" and existing_assignments:
            for code in self.movement_codes:
                prev_assigns = []
                seen = set()
                for a in existing_assignments.get(code, []):
                    if isinstance(a, dict):
                        assign_obj = GSEAssignment(
                            a.get('assigned', False),
                            a.get('gse_obj', None),
                            a.get('time', 10.0),
                            a.get('count', 1),
                            a.get('deterioration_factor', 1.0)
                        )
                    else:
                        assign_obj = a
                    gse_obj = assign_obj.gse_obj
                    if gse_obj is None:
                        gse_id = None
                    elif hasattr(gse_obj, 'oid'):
                        gse_id = gse_obj.oid
                    elif isinstance(gse_obj, dict):
                        gse_id = gse_obj.get('oid', None)
                    else:
                        gse_id = None
                    if gse_id not in seen:
                        prev_assigns.append(assign_obj)
                        seen.add(gse_id)
                for g in self.gse_list:
                    if g is None:
                        gse_id = None
                    elif hasattr(g, 'oid'):
                        gse_id = g.oid
                    elif isinstance(g, dict):
                        gse_id = g.get('oid', None)
                    else:
                        gse_id = None
                    if gse_id not in seen:
                        prev_assigns.append(GSEAssignment(False, g, 10.0, 1, 1.0))
                        seen.add(gse_id)
                self.assignments[code] = prev_assigns
        else:
            for code in self.movement_codes:
                self.assignments[code] = [GSEAssignment(False, g, 10.0, 1, 1.0) for g in self.gse_list]

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
                val = gse.get(col, "") if isinstance(gse, dict) else getattr(gse, col, "")
                item = QTableWidgetItem(str(val))
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
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
            det_spin.setValue(float(getattr(assign, 'deterioration_factor', 1.0)))
            det_spin.valueChanged.connect(partial(self.update_deterioration, i))
            self.table.setCellWidget(i, 3 + len(self.gse_columns), det_spin)

        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()

    def refresh_summary_table(self):
        # Gather all assigned GSEs from all movement codes
        assigned = []
        for code, assigns in self.assignments.items():
            for a in assigns:
                if a.assigned:
                    assigned.append((code, a))

        self.summary_table.setRowCount(len(assigned))
        # +1 for movement code as first column
        total_columns = 1 + len(self.gse_columns) + 3  # code + gse_columns + [time, count, deterioration_factor]
        self.summary_table.setColumnCount(total_columns)

        headers = ['Movement'] + self.gse_columns + ['time', 'count', 'deterioration_factor']
        self.summary_table.setHorizontalHeaderLabels(headers)

        for i, (code, assign) in enumerate(assigned):
            self.summary_table.setItem(i, 0, QTableWidgetItem(str(code)))
            gse = assign.gse_obj
            for j, col in enumerate(self.gse_columns):
                val = gse.get(col, "") if isinstance(gse, dict) else getattr(gse, col, "")
                self.summary_table.setItem(i, 1 + j, QTableWidgetItem(str(val)))
            self.summary_table.setItem(i, 1 + len(self.gse_columns), QTableWidgetItem(str(assign.time)))
            self.summary_table.setItem(i, 2 + len(self.gse_columns), QTableWidgetItem(str(assign.count)))
            self.summary_table.setItem(i, 3 + len(self.gse_columns), QTableWidgetItem(str(getattr(assign, 'deterioration_factor', 1.0))))
        self.summary_table.resizeColumnsToContents()
        self.summary_table.resizeRowsToContents()
        # Make the summary table read-only:
        for i in range(self.summary_table.rowCount()):
            for j in range(self.summary_table.columnCount()):
                item = self.summary_table.item(i, j)
                if item:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)



    def toggle_assigned(self, row, state):
        idx = self.movement_combo.currentIndex()
        if idx < 0: return
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
