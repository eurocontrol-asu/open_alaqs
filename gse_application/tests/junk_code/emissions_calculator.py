import csv
import re

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class EmissionsCalculatorDialog(QDialog):
    def __init__(self, db, assignments, movements_df, ef_list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Emissions Calculator")
        self.resize(1100, 650)
        self.db = db
        self.assignments = assignments
        self.movements_df = movements_df
        self.ef_list = ef_list
        self.emissions_output = []

        layout = QVBoxLayout(self)

        # Top: GSE List by Movement
        lbl_gse = QLabel("GSE List by Movement")
        layout.addWidget(lbl_gse)
        self.table_gse = QTableWidget()
        layout.addWidget(self.table_gse)
        self.fill_gse_table()

        # Center: Calculate button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_calculate = QPushButton("Calculate Emissions")
        btn_row.addWidget(self.btn_calculate)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Bottom: Output Emissions table
        lbl_emis = QLabel("Output Emissions")
        layout.addWidget(lbl_emis)
        self.table_output = QTableWidget()
        self.table_output.setMaximumHeight(200)  # Make it shorter
        layout.addWidget(self.table_output)

        # Export button, bottom right
        export_row = QHBoxLayout()
        export_row.addStretch()
        self.btn_export = QPushButton("Export table to CSV")
        self.btn_export.setEnabled(False)
        export_row.addWidget(self.btn_export)
        layout.addLayout(export_row)

        # Connections
        self.btn_calculate.clicked.connect(self.fill_output_table)
        self.btn_export.clicked.connect(self.export_emissions_table)

    def fill_gse_table(self):
        rows = []
        for movement_code, gse_list in self.assignments.items():
            for assign in gse_list:
                if not getattr(assign, "assigned", False):
                    continue  # Only show assigned
                row = {"movement_code": movement_code}

                gse_obj = getattr(assign, "gse_obj", None)
                if gse_obj is not None:
                    if isinstance(gse_obj, dict):
                        row.update(gse_obj)
                    else:
                        for attr in ["type", "description", "power", "load", "fuel"]:
                            row[attr] = getattr(gse_obj, attr, "")
                row["time"] = getattr(assign, "time", "")
                row["count"] = getattr(assign, "count", "")
                row["deterioration_factor"] = getattr(
                    assign, "deterioration_factor", 1.0
                )
                rows.append(row)
        if not rows:
            self.table_gse.setRowCount(0)
            self.table_gse.setColumnCount(0)
            return
        # --- Remove unwanted columns ---
        unwanted = {"stage", "oid"}
        headers = [k for k in rows[0].keys() if k not in unwanted]
        self.table_gse.setColumnCount(len(headers))
        self.table_gse.setHorizontalHeaderLabels(headers)
        self.table_gse.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, col in enumerate(headers):
                self.table_gse.setItem(i, j, QTableWidgetItem(str(row.get(col, ""))))
        self.table_gse.resizeColumnsToContents()

    def fill_output_table(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            emissions = self.calculate_emissions_from_assignments()
            if not emissions:
                self.table_output.setRowCount(0)
                self.table_output.setColumnCount(0)
                self.btn_export.setEnabled(False)
                return
            headers = list(emissions[0].keys())
            self.table_output.setColumnCount(len(headers))
            self.table_output.setHorizontalHeaderLabels(headers)
            self.table_output.setRowCount(len(emissions))
            for i, row in enumerate(emissions):
                for j, col in enumerate(headers):
                    self.table_output.setItem(
                        i, j, QTableWidgetItem(str(row.get(col, "")))
                    )
            self.table_output.resizeColumnsToContents()
            self.emissions_output = emissions
            self.btn_export.setEnabled(True)
        except Exception as err:
            QMessageBox.critical(self, "Calculation Error", str(err))
        finally:
            QApplication.restoreOverrideCursor()

    def calculate_emissions_from_assignments(self):
        ef_table = [
            ef.__dict__ if hasattr(ef, "__dict__") else dict(ef) for ef in self.ef_list
        ]
        output_rows = {}

        for movement_code, gse_list in self.assignments.items():
            if not gse_list:
                continue
            ac_group, gate_type, dep_arr = movement_code.split("/")
            gse_accum = {
                "ac_group": ac_group,
                "gate_type": gate_type,
                "gse_type": "GSE",
                "A_min": 0.0,
                "D_min": 0.0,
                "CO_g_per_h": 0.0,
                "HC_g_per_h": 0.0,
                "NOx_g_per_h": 0.0,
                "PM_g_per_h": 0.0,
                "kWh": 0.0,
            }
            gpu_rows = {}

            for assign in gse_list:
                if not getattr(assign, "assigned", False):
                    continue
                gse_obj = getattr(assign, "gse_obj", None)
                gse_type = ""
                stage = "Stage IIIA"
                description = ""
                power = 0.0
                load_factor = 1.0
                if gse_obj:
                    if isinstance(gse_obj, dict):
                        gse_type = gse_obj.get("type", "")
                        stage = gse_obj.get("Stage", "") or "Stage IIIA"
                        description = gse_obj.get("description", "")
                        power = float(gse_obj.get("power", 0))
                        load_factor = float(gse_obj.get("load", 1.0))
                    else:
                        gse_type = getattr(gse_obj, "type", "")
                        stage = getattr(gse_obj, "Stage", "Stage IIIA")
                        description = getattr(gse_obj, "description", "")
                        power = float(getattr(gse_obj, "power", 0))
                        load_factor = float(getattr(gse_obj, "load", 1.0))
                time = float(getattr(assign, "time", 0))
                count = int(getattr(assign, "count", 1))
                deter_factor = float(getattr(assign, "deterioration_factor", 1.0))
                operation = dep_arr
                A_min = time if operation == "A" else 0.0
                D_min = time if operation == "D" else 0.0
                # Find emission factors row
                ef_row = None
                for ef in ef_table:
                    if ef.get("stage") == stage and self.in_power_range(
                        power, ef.get("power_range", "")
                    ):
                        ef_row = ef
                        break
                if not ef_row:
                    continue  # skip if no factor found (could log)
                minutes = A_min + D_min
                hours = minutes / 60.0
                co = (
                    float(ef_row.get("CO_g_per_kWh", 0))
                    * power
                    * hours
                    * count
                    * load_factor
                    * deter_factor
                )
                hc = (
                    float(ef_row.get("HC_g_per_kWh", 0))
                    * power
                    * hours
                    * count
                    * load_factor
                    * deter_factor
                )
                nox = (
                    float(ef_row.get("NOx_g_per_kWh", 0))
                    * power
                    * hours
                    * count
                    * load_factor
                    * deter_factor
                )
                pm = (
                    float(ef_row.get("PM_g_per_kWh", 0))
                    * power
                    * hours
                    * count
                    * load_factor
                    * deter_factor
                )
                kwh = power * hours * count
                if gse_type == "GPU":
                    key = (ac_group, gate_type, description)
                    if key not in gpu_rows:
                        gpu_rows[key] = {
                            "ac_group": ac_group,
                            "gate_type": gate_type,
                            "gse_type": gse_type,
                            "A_min": 0.0,
                            "D_min": 0.0,
                            "CO_g_per_h": 0.0,
                            "HC_g_per_h": 0.0,
                            "NOx_g_per_h": 0.0,
                            "PM_g_per_h": 0.0,
                            "kWh": 0.0,
                        }
                    gpu_rows[key]["A_min"] += A_min
                    gpu_rows[key]["D_min"] += D_min
                    gpu_rows[key]["CO_g_per_h"] += co
                    gpu_rows[key]["HC_g_per_h"] += hc
                    gpu_rows[key]["NOx_g_per_h"] += nox
                    gpu_rows[key]["PM_g_per_h"] += pm
                    gpu_rows[key]["kWh"] += kwh
                else:
                    gse_accum["A_min"] += A_min
                    gse_accum["D_min"] += D_min
                    gse_accum["CO_g_per_h"] += co
                    gse_accum["HC_g_per_h"] += hc
                    gse_accum["NOx_g_per_h"] += nox
                    gse_accum["PM_g_per_h"] += pm
                    gse_accum["kWh"] += kwh
            # Save rows
            if gse_accum["A_min"] > 0 or gse_accum["D_min"] > 0:
                output_rows[(ac_group, gate_type, "GSE")] = gse_accum
            for k, v in gpu_rows.items():
                if v["A_min"] > 0 or v["D_min"] > 0:
                    output_rows[k] = v

        # Convert to list for output (with desired columns)
        output_list = []
        for v in output_rows.values():
            output_list.append(
                {
                    "ac_group": v["ac_group"],
                    "gate_type": v["gate_type"],
                    "gse_type": v.get("gse_type", ""),
                    "A_min": round(v["A_min"], 2),
                    "D_min": round(v["D_min"], 2),
                    "CO_g_per_h": round(v["CO_g_per_h"], 2),
                    "HC_g_per_h": round(v["HC_g_per_h"], 2),
                    "NOx_g_per_h": round(v["NOx_g_per_h"], 2),
                    "PM_g_per_h": round(v["PM_g_per_h"], 2),
                    "kWh": round(v["kWh"], 2),
                }
            )
        return output_list

    def in_power_range(self, power, power_range_str):
        # Example: '75 <= P < 130'
        match = re.match(r"(\d+)\s*<=\s*P\s*<\s*(\d+)", power_range_str)
        if match:
            low, high = float(match.group(1)), float(match.group(2))
            return low <= power < high
        match = re.match(r"(\d+)\s*<=\s*P\s*<=\s*(\d+)", power_range_str)
        if match:
            low, high = float(match.group(1)), float(match.group(2))
            return low <= power <= high
        return False

    def export_emissions_table(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Emissions Table", "", "CSV Files (*.csv)"
        )
        if not filename:
            return
        try:
            with open(filename, "w", newline="") as csvfile:
                writer = csv.writer(csvfile)
                # Get data from output table
                headers = [
                    self.table_output.horizontalHeaderItem(i).text()
                    for i in range(self.table_output.columnCount())
                ]
                writer.writerow(headers)
                for row in range(self.table_output.rowCount()):
                    writer.writerow(
                        [
                            (
                                self.table_output.item(row, col).text()
                                if self.table_output.item(row, col)
                                else ""
                            )
                            for col in range(self.table_output.columnCount())
                        ]
                    )
            QMessageBox.information(
                self, "Export Successful", "Emissions table was successfully exported."
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))
