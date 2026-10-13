import csv
import re
import sqlite3

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
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
    def __init__(
        self,
        db,
        assignments,
        movements_df,
        ef_list,
        backend,
        path,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Emissions Calculator")
        self.resize(1100, 650)
        self.db = db
        self.assignments = assignments
        self.movements_df = movements_df
        self.ef_list = ef_list
        self.emissions_output = []

        # Get the type of backend to know how to solve the db
        self.backend = backend

        # Get the path to the imported database to update it directly when saving the emissions
        self.path = path

        # Handler to catch the export status(T/F)
        self.export_completed = False

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

        # Export button csv, bottom right
        export_row_csv = QHBoxLayout()
        export_row_csv.addStretch()
        self.btn_export_csv = QPushButton("Export table to CSV")
        self.btn_export_csv.setEnabled(False)
        export_row_csv.addWidget(self.btn_export_csv)
        layout.addLayout(export_row_csv)

        # Export button OpenALAQS, bottom right
        export_row_alaqs = QHBoxLayout()
        export_row_alaqs.addStretch()
        self.btn_export_alaqs = QPushButton("Update the OpenALAQS database")
        self.btn_export_alaqs.setEnabled(False)
        export_row_alaqs.addWidget(self.btn_export_alaqs)
        layout.addLayout(export_row_alaqs)

        # Connections
        self.btn_calculate.clicked.connect(self.fill_output_table)
        self.btn_export_csv.clicked.connect(self.export_emissions_table_csv)
        self.btn_export_alaqs.clicked.connect(self.export_emissions_table_alaqs)

    def closeEvent(self, event):

        # Only show prompt if there are calculated emissions to save and they were not saved before
        if self.emissions_output and not self.export_completed:
            reply = QMessageBox.question(
                self,
                "Warning",
                "You have calculated emission results. Would you like to export them before closing?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )

            if reply == QMessageBox.StandardButton.Yes:
                # Show export format choice dialog
                format_choice = QMessageBox()
                format_choice.setWindowTitle("Choose Export Format")
                format_choice.setText("Which export format would you like to use?")

                csv_button = format_choice.addButton(
                    "CSV Format", QMessageBox.ButtonRole.ActionRole
                )
                alaqs_button = format_choice.addButton(
                    "Update OpenALAQS database", QMessageBox.ButtonRole.ActionRole
                )
                _ = format_choice.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

                format_choice.setDefaultButton(csv_button)
                format_choice.exec()

                if format_choice.clickedButton() == csv_button:
                    self.export_emissions_table_csv()
                    # Only close if export was successful (user didn't cancel file dialog)
                    if hasattr(self, "_export_completed") and self.export_completed:
                        event.accept()  # Close dialog
                    else:
                        event.ignore()  # Keep dialog open if export was cancelled
                elif format_choice.clickedButton() == alaqs_button:
                    self.export_emissions_table_alaqs()
                    # Only close if export was successful (user didn't cancel file dialog)
                    if hasattr(self, "_export_completed") and self.export_completed:
                        event.accept()  # Close dialog
                    else:
                        event.ignore()  # Keep dialog open if export was cancelled
                else:  # Cancel
                    event.ignore()  # Keep dialog open
            elif reply == QMessageBox.StandardButton.No:
                event.accept()  # Close without saving
            else:  # Cancel
                event.ignore()  # Keep dialog open
        else:
            # No emissions calculated, just close
            event.accept()

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
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            emissions = self.reconfigure_emissions_table()
            if not emissions:
                self.table_output.setRowCount(0)
                self.table_output.setColumnCount(0)

                # Change events for the exoport buttons to not be pressable
                self.btn_export_csv.setEnabled(False)
                self.btn_export_alaqs.setEnabled(False)
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

            # Change events for the export buttons to be pressable
            self.btn_export_csv.setEnabled(True)
            self.btn_export_alaqs.setEnabled(True)

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
                "SOx_g_per_h": 0.0,
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
                sox = (
                    float(ef_row.get("SOx_g_per_kWh", 0))
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
                            "SOx_g_per_h": 0.0,
                            "kWh": 0.0,
                        }
                    gpu_rows[key]["A_min"] += A_min
                    gpu_rows[key]["D_min"] += D_min
                    gpu_rows[key]["CO_g_per_h"] += co
                    gpu_rows[key]["HC_g_per_h"] += hc
                    gpu_rows[key]["NOx_g_per_h"] += nox
                    gpu_rows[key]["PM_g_per_h"] += pm
                    gpu_rows[key]["SOx_g_per_h"] += sox
                    gpu_rows[key]["kWh"] += kwh
                else:
                    gse_accum["A_min"] += A_min
                    gse_accum["D_min"] += D_min
                    gse_accum["CO_g_per_h"] += co
                    gse_accum["HC_g_per_h"] += hc
                    gse_accum["NOx_g_per_h"] += nox
                    gse_accum["PM_g_per_h"] += pm
                    gse_accum["SOx_g_per_h"] += sox
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
                    "gate_type": v["gate_type"],
                    "ac_group": v["ac_group"],
                    "emis_type": v.get("gse_type", ""),
                    "A_min": round(v["A_min"], 2),
                    "D_min": round(v["D_min"], 2),
                    "co": round(v["CO_g_per_h"], 2),
                    "hc": round(v["HC_g_per_h"], 2),
                    "nox": round(v["NOx_g_per_h"], 2),
                    "sox": round(v.get("SOx_g_per_h", 0.0), 2),
                    "pm10": round(v["PM_g_per_h"], 2),
                    # "kWh": round(v["kWh"], 2) # kWh still calculated but not included in the output_list
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

    def reconfigure_emissions_table(self):
        try:
            # Get the default emissions dict from the calculator
            emissions = self.calculate_emissions_from_assignments()

            # Adapt the emissions dict to match the OpenALAQS format
            reconfigured_emissions = []
            idx = 0

            for entry in emissions:
                print(entry)
                # First dict based on arrival time
                dict1 = {
                    "oid": int(idx + 1),
                    "gate_type": entry["gate_type"],
                    "ac_group": entry["ac_group"],
                    "emis_type": entry["emis_type"],
                    "time_unit": str("minutes"),
                    "op_type": str("A"),
                    "time": float(entry["A_min"]),
                    "emis_unit": str("grams/hour"),
                    "co": entry["co"],
                    "hc": entry["hc"],
                    "nox": entry["nox"],
                    "sox": entry["sox"],
                    "pm10": entry["pm10"],
                    "source": str("GSE Application"),
                }

                # Second dict based on departure time
                dict2 = {
                    "oid": int(idx + 2),
                    "gate_type": entry["gate_type"],
                    "ac_group": entry["ac_group"],
                    "emis_type": entry["emis_type"],
                    "time_unit": str("minutes"),
                    "op_type": str("D"),
                    "time": float(entry["D_min"]),
                    "emis_unit": str("grams/hour"),
                    "co": entry["co"],
                    "hc": entry["hc"],
                    "nox": entry["nox"],
                    "sox": entry["sox"],
                    "pm10": entry["pm10"],
                    "source": str("GSE Application"),
                }

                # Update the index counter
                idx += 2

                reconfigured_emissions.extend([dict1, dict2])

            return reconfigured_emissions

        except Exception as e:
            QMessageBox.critical(self, "Converting to OpenALAQS Format Failed", str(e))

    def export_emissions_table_alaqs(self):
        # Export to OpenALAQS format only if the database imported is in that format
        if self.backend != "sqlite":
            QMessageBox.critical(
                self,
                "Cannot save in OpenALAQS Format",
                "Either import a valid .alaqs file or save as .csv",
            )
        else:
            try:
                # Get the emissions data in OpenALAQS format
                emissions = self.reconfigure_emissions_table()
                if not emissions:
                    self.export_completed = False
                    return

                # Connect to the database
                conn = sqlite3.connect(self.path)
                cursor = conn.cursor()

                # Check if the table exists, create if not
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS default_gate_profiles (
                        oid INTEGER PRIMARY KEY,
                        gate_type TEXT,
                        ac_group TEXT,
                        emis_type TEXT,
                        time_unit TEXT,
                        op_type TEXT,
                        time REAL,
                        emis_unit TEXT,
                        co REAL,
                        hc REAL,
                        nox REAL,
                        sox REAL,
                        pm10 REAL,
                        source TEXT
                    )
                """)

                # Optional: Clear existing data (if you want to overwrite)
                cursor.execute("DELETE FROM default_gate_profiles")

                # Get the current max oid in the table
                cursor.execute("SELECT MAX(oid) FROM default_gate_profiles")
                result = cursor.fetchone()
                last_oid = result[0] if result and result[0] is not None else 0

                # Shift all oids in emissions by last_oid
                for entry in emissions:
                    entry["oid"] = entry["oid"] + last_oid

                # Insert emissions data
                for entry in emissions:
                    cursor.execute(
                        """
                        INSERT INTO default_gate_profiles (
                            oid, gate_type, ac_group, emis_type, time_unit, op_type, time, emis_unit,
                            co, hc, nox, sox, pm10, source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            entry["oid"],
                            entry["gate_type"],
                            entry["ac_group"],
                            entry["emis_type"],
                            entry["time_unit"],
                            entry["op_type"],
                            entry["time"],
                            entry["emis_unit"],
                            entry["co"],
                            entry["hc"],
                            entry["nox"],
                            entry["sox"],
                            entry["pm10"],
                            entry["source"],
                        ),
                    )

                conn.commit()
                conn.close()
                QMessageBox.information(
                    self,
                    "Update Successful",
                    "Emissions table was successfully updated in the database.",
                )
                self.export_completed = True

                self.close()  # Close the window

            except Exception as e:
                QMessageBox.critical(self, "Update Failed", str(e))
                self.export_completed = False

    def export_emissions_table_csv(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Emissions Table", "", "CSV Files (*.csv)"
        )
        if not filename:
            self.export_completed = False
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
            self.export_completed = True

            self.close()  # Close the window
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))
            self.export_completed = False
