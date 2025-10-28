import os
import sqlite3
import sys

import pandas as pd
from emissions_calculator import EmissionsCalculatorDialog
from model.database import GSEDatabase
from movement_editor import MovementEditor
from PyQt5.QtCore import QAbstractTableModel, Qt, QVariant
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QTableView,
    QTabWidget,
)
from views.emission_factor_table_model import EmissionFactorTableModel
from views.gse_table_model import GSETableModel
from views.ui_main import Ui_MainWindow

MOVEMENTS_HEADERS = [
    "runway_time",
    "block_time",
    "aircraft_registration",
    "aircraft",
    "gate",
    "departure_arrival",
    "runway",
    "engine_name",
    "profile_id",
    "track_id",
    "taxi_route",
    "tow_ratio",
    "apu_code",
    "taxi_engine_count",
    "set_time_of_main_engine_start_after_block_off_in_s",
    "set_time_of_main_engine_start_before_takeoff_in_s",
    "set_time_of_main_engine_off_after_runway_exit_in_s",
    "engine_thrust_level_for_taxiing",
    "taxi_fuel_ratio",
    "number_of_stop_and_gos",
    "domestic",
]


class PandasModel(QAbstractTableModel):
    def __init__(self, df):
        super().__init__()
        self._df = df

    def rowCount(self, parent=None):
        return self._df.shape[0]

    def columnCount(self, parent=None):
        return self._df.shape[1]

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and role == Qt.DisplayRole:
            return str(self._df.iloc[index.row(), index.column()])
        return QVariant()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return QVariant()
        if orientation == Qt.Horizontal:
            return str(self._df.columns[section])
        else:
            return str(section)


tab_stylesheet = """
QTabWidget::pane {
    border-top: 1px solid #cccccc;
    background: #f4f4f7;
    border-radius: 10px;
    padding: 5px;
}
QTabBar::tab {
    background: #e6e6e6;
    color: #333333;
    border: 1px solid #bbbbbb;
    border-bottom: none;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    min-width: 180px;
    min-height: 12px;
    padding: 10px 18px;
    font-size: 14px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #2c3e50;
    border: 2px solid #999999;
    border-bottom: none;
    font-weight: bold;
    margin-bottom: -1px;
}
QTabBar::tab:hover {
    background: #f0f0f0;
    color: #2c3e50;
    border: 1px solid #aaaaaa;
}
QTabBar::tab:!selected {
    margin-top: 3px;
}
"""

header_stylesheet = """
QHeaderView::section {
    background-color: #cfd8dc;
    color: black;
    padding: 0px 4px;
    font-weight: bold;
    font-size: 14px;
    border: 1px solid #dddddd;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTableCornerButton::section {
    background-color: #cfd8dc;
    border: 1px solid #dddddd;
}
"""


class MainController(QMainWindow):
    def __init__(self, db_source, backend="csv"):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.menuBar().setVisible(False)
        self.tabWidget = QTabWidget()
        self.setCentralWidget(self.tabWidget)
        self.resize(1000, 800)
        self.setMinimumSize(800, 600)

        # Setup tabs
        self.gseTableView = QTableView()
        self.gseTableView.setObjectName("GSETableView")
        self.tabWidget.addTab(self.gseTableView, "GSE")

        self.emissionFactorTableView = QTableView()
        self.tabWidget.addTab(self.emissionFactorTableView, "Emission Standards")

        self.movementTableView = QTableView()
        self.tabWidget.addTab(self.movementTableView, "Movements")

        self.tabWidget.setStyleSheet(tab_stylesheet)
        self.tabWidget.currentChanged.connect(self.on_tab_changed)

        # Action connections
        self.ui.actionOpen.triggered.connect(self.open_database_dialog)
        self.ui.actionDefine_Movements.setEnabled(True)
        self.ui.actionDefine_Movements.setText("Assign GSE")
        self.ui.actionDefine_Movements.triggered.connect(self.open_movement_editor)

        self.ui.actionCalculate_Emissions.setEnabled(True)
        self.ui.actionCalculate_Emissions.triggered.connect(self.on_calculate_emissions)

        # Initial state
        self.db_source = db_source
        db_folder = os.path.dirname(self.db_source)
        try:
            self.icao_to_group = self.load_ac_mapping(db_folder)
        except Exception as e:
            QMessageBox.warning(self, "Aircraft Mapping Error", str(e))
            self.icao_to_group = {}

        self.backend = backend
        self.db = None
        self.movements_df = pd.DataFrame(columns=MOVEMENTS_HEADERS)
        self.movement_assignments = []

        self.load_all_tabs()

    def load_ac_mapping(self, db_folder):
        """
        Loads aircraft type mapping from default_aircraft.csv in the database folder.
        Returns a dict: icao -> ac_group.
        """
        csv_path = os.path.join(db_folder, "default_aircraft.csv")
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Aircraft mapping file not found: {csv_path}")
        # Try ; first, fallback to ,
        try:
            df = pd.read_csv(csv_path, delimiter=",")
        except Exception:
            df = pd.read_csv(csv_path)
        # Defensive: lower-case and strip for robustness
        df["icao"] = df["icao"].astype(str).str.strip()
        df["ac_group"] = df["ac_group"].astype(str).str.strip()
        return dict(zip(df["icao"], df["ac_group"]))

    # --- Separate loading for each tab ---
    def load_movements_tab(self):
        self.movements_df = pd.DataFrame(columns=MOVEMENTS_HEADERS)
        gate_mapping = {}

        if self.backend == "csv":
            # Look for user_aircraft_movements.csv or movements.csv
            csv_names = ["user_aircraft_movements.csv", "movements.csv"]
            found_csv = None
            for name in csv_names:
                test_path = os.path.join(os.path.dirname(self.db_source), name)
                if os.path.exists(test_path):
                    found_csv = test_path
                    break
            if found_csv:
                try:
                    df = pd.read_csv(found_csv, delimiter=";")
                    missing = [h for h in MOVEMENTS_HEADERS if h not in df.columns]
                    if missing:
                        QMessageBox.warning(
                            self,
                            "Movements CSV Error",
                            f"Missing required columns in {os.path.basename(found_csv)}:\n{', '.join(missing)}",
                        )
                    elif df.empty:
                        QMessageBox.warning(
                            self,
                            "Movements CSV Error",
                            f"{os.path.basename(found_csv)} is empty!",
                        )
                    else:
                        self.movements_df = df[MOVEMENTS_HEADERS]
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Movements Load Error",
                        f"Error loading {os.path.basename(found_csv)}: {e}",
                    )
            # # --- Gate mapping from CSV ---
            # mapping_csv = os.path.join(os.path.dirname(self.db_source), "gate_mapping.csv")
            # if os.path.exists(mapping_csv):
            #     try:
            #         map_df = pd.read_csv(mapping_csv)
            #         gate_mapping = dict(zip(map_df['gate_name'], map_df['gate_type']))
            #     except Exception as e:
            #         QMessageBox.warning(self, "Gate Mapping Error", f"Could not read gate_mapping.csv: {e}")
            # else:
            #     QMessageBox.warning(self, "Gate Mapping", "No gate_mapping.csv found—gate_type will be set to UNKNOWN.")

        elif self.backend == "sqlite":
            try:
                conn = sqlite3.connect(self.db_source)
                tables = pd.read_sql_query(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='user_aircraft_movements';",
                    conn,
                )
                if tables.empty:
                    QMessageBox.warning(
                        self,
                        "Movements Table Error",
                        "SQLite database does not contain 'user_aircraft_movements' table.",
                    )
                else:
                    df = pd.read_sql_query(
                        "SELECT * FROM user_aircraft_movements", conn
                    )
                    missing = [h for h in MOVEMENTS_HEADERS if h not in df.columns]
                    if missing:
                        QMessageBox.warning(
                            self,
                            "Movements Table Error",
                            f"Table 'user_aircraft_movements' missing columns:\n{', '.join(missing)}",
                        )
                    elif df.empty:
                        QMessageBox.warning(
                            self,
                            "Movements Table Error",
                            "Table 'user_aircraft_movements' is empty!",
                        )
                    else:
                        self.movements_df = df[MOVEMENTS_HEADERS]

                # --- Gate mapping from shapes_gates table ---
                try:
                    gate_df = pd.read_sql_query(
                        "SELECT gate_id, gate_type FROM shapes_gates", conn
                    )
                    gate_mapping = dict(zip(gate_df["gate_id"], gate_df["gate_type"]))
                except Exception as e:
                    QMessageBox.warning(
                        self,
                        "Gate Mapping Error",
                        f"Could not read shapes_gates table: {e}",
                    )
                conn.close()
            except Exception as e:
                QMessageBox.critical(
                    self, "Movements Load Error", f"Error loading from SQLite: {e}"
                )

        # --- Apply gate mapping (add gate_type column) ---
        if not self.movements_df.empty:
            self.movements_df["gate_type"] = (
                self.movements_df["gate"].map(gate_mapping).fillna("UNKNOWN")
            )
            # Warn about any gates that could not be mapped
            missing_gates = set(
                self.movements_df.loc[
                    self.movements_df["gate_type"] == "UNKNOWN", "gate"
                ]
            )
            if missing_gates:
                QMessageBox.warning(
                    self,
                    "Gate Mapping Warning",
                    "The following gates could not be mapped to a type and will be set as UNKNOWN:\n"
                    + ", ".join(sorted(missing_gates)),
                )

        model = PandasModel(self.movements_df)
        self.movementTableView.setModel(model)
        self.movementTableView.horizontalHeader().setStyleSheet(header_stylesheet)
        self.movementTableView.horizontalHeader().setStretchLastSection(True)
        self.movementTableView.verticalHeader().setVisible(False)

    def load_gse_tab(self):
        try:
            gse_list = self.db.gse
            gse_model = GSETableModel(gse_list)
            self.gseTableView.setModel(gse_model)
            self.gseTableView.setStyleSheet(header_stylesheet)
            self.gseTableView.verticalHeader().setVisible(False)
            self.gseTableView.horizontalHeader().setDefaultAlignment(
                Qt.AlignLeft | Qt.AlignVCenter
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load GSE: {e}")

    def load_emission_tab(self):
        try:
            ef_list = self.db.emission_factors
            ef_model = EmissionFactorTableModel(ef_list)
            self.emissionFactorTableView.setModel(ef_model)
            self.emissionFactorTableView.horizontalHeader().setStyleSheet(
                header_stylesheet
            )
            self.emissionFactorTableView.verticalHeader().setVisible(False)
            self.emissionFactorTableView.horizontalHeader().setDefaultAlignment(
                Qt.AlignLeft | Qt.AlignVCenter
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to load Emission Standards: {e}"
            )

    def load_all_tabs(self):
        # (Re-)open DB before loading tabs
        try:
            self.db = GSEDatabase(self.db_source, backend=self.backend)
            self.db.open()
        except Exception as e:
            QMessageBox.critical(
                self, "Database Error", f"Failed to open database: {e}"
            )
            return
        self.load_gse_tab()
        self.load_emission_tab()
        self.load_movements_tab()

    def open_database_dialog(self):
        file_or_folder, _ = QFileDialog.getOpenFileName(
            self,
            "Select Database File or Folder",
            os.path.dirname(self.db_source),
            "SQLite Database (*.alaqs *.db);;CSV File (*.csv);;All Files (*)",
        )
        if not file_or_folder:
            return
        if file_or_folder.lower().endswith((".alaqs", ".db")):
            self.db_source = file_or_folder
            self.backend = "sqlite"
        elif file_or_folder.lower().endswith(".csv"):
            self.db_source = file_or_folder
            self.backend = "csv"
        else:
            QMessageBox.critical(
                self, "Error", "No .alaqs/.db database file or movements.csv found."
            )
            return
        self.load_movements_tab()

    def on_tab_changed(self, idx):
        tab_text = self.tabWidget.tabText(idx)
        if tab_text == "Movements" and (
            self.movements_df is None or self.movements_df.empty
        ):
            QMessageBox.warning(
                self,
                "No Movements Data",
                "No valid user_aircraft_movements table or movements.csv file found, or it is empty or invalid.\n"
                "You must import a valid movements table or CSV using the Open Database button.",
            )

    def open_movement_editor(self):
        # Determine if there are previous assignments
        existing_assignments = getattr(self, "movement_assignments", None)
        reset_assignments = False

        if existing_assignments:
            msgbox = QMessageBox(self)
            msgbox.setWindowTitle("Existing Assignments Found")
            msgbox.setText(
                "<b>You have existing GSE assignments. What would you like to do?</b><br><br>"
                "<b>Reset</b>: Start over and remove all previous assignments.<br>"
                "<b>Append</b>: Add new assignments to the existing ones.<br>"
                "<b>Cancel</b>: Do nothing."
            )
            reset_button = msgbox.addButton("Reset", QMessageBox.ActionRole)
            append_button = msgbox.addButton("Append", QMessageBox.ActionRole)
            cancel_button = msgbox.addButton("Cancel", QMessageBox.RejectRole)
            msgbox.setDefaultButton(cancel_button)
            msgbox.exec_()

            if msgbox.clickedButton() == reset_button:
                existing_assignments = None
                reset_assignments = True
            elif msgbox.clickedButton() == append_button:
                reset_assignments = False
            elif msgbox.clickedButton() == cancel_button:
                return  # User cancelled

        dlg = MovementEditor(
            db=self.db,
            movements_df=self.movements_df,
            icao_to_group=self.icao_to_group,
            parent=self,
            existing_assignments=None if reset_assignments else existing_assignments,
            gse_list=getattr(
                self.db, "gse", None
            ),  # <<<<< FIXED: Pass loaded GSE list!
        )

        if dlg.exec_():
            new_assignments = dlg.get_assignments()
            if not reset_assignments and existing_assignments:
                # Merge new assignments into ALL previous
                self.movement_assignments = self.merge_assignment_dicts(
                    existing_assignments, new_assignments
                )
            else:
                self.movement_assignments = new_assignments

            # Correct assignment count:
            total_assigned = sum(
                sum(1 for a in assigns if getattr(a, "assigned", False))
                for assigns in self.movement_assignments.values()
            )
            QMessageBox.information(
                self, "Assignments Saved", f"{total_assigned} GSE assignments recorded."
            )

    def on_calculate_emissions(self):
        if not self.movement_assignments:
            QMessageBox.warning(
                self,
                "Missing Data",
                "Please assign GSE to movements before calculating emissions.",
            )
            return
        ef_list = getattr(self.db, "emission_factors", [])
        dlg = EmissionsCalculatorDialog(
            db=self.db,
            assignments=self.movement_assignments,
            movements_df=self.movements_df,
            ef_list=ef_list,
            parent=self,
        )
        dlg.exec_()

    def merge_assignment_dicts(self, old, new):
        """
        Merge two assignment dicts: old and new.
        For each movement_code, update existing GSE assignments and add new ones.
        """
        if not old:
            return dict(new)
        merged = dict(old)
        for code, new_gse_list in new.items():
            existing = merged.get(code, [])

            # Map by unique GSE key (by 'oid' if available, else type+desc)
            def gse_key(a):
                g = getattr(a, "gse_obj", None)
                if g is None:
                    return None
                if hasattr(g, "oid"):
                    return getattr(g, "oid")
                elif isinstance(g, dict):
                    return g.get("oid") or (g.get("type", ""), g.get("description", ""))
                else:
                    return id(g)

            exist_map = {gse_key(a): a for a in existing if gse_key(a) is not None}
            for a in new_gse_list:
                k = gse_key(a)
                if k in exist_map:
                    # Overwrite values with new assignment
                    exist_map[k].assigned = getattr(a, "assigned", False)
                    exist_map[k].time = getattr(a, "time", 10.0)
                    exist_map[k].count = getattr(a, "count", 1)
                    exist_map[k].deterioration_factor = getattr(
                        a, "deterioration_factor", 1.0
                    )
                else:
                    existing.append(a)
            merged[code] = existing
        return merged


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    dbdir = os.path.join(os.path.dirname(__file__), "model", "database")
    db_source = os.path.join(dbdir, "default_gse.csv")
    backend = "csv"
    controller = MainController(db_source, backend)
    controller.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
