#!/usr/bin/env python3
"""
GUI for migrate_alaqs.py — exposes every CLI flag, plus a live
stdout/stderr log panel.

Place this file in the SAME directory as migrate_alaqs.py and run with the
same Python that has PyQt5 (QGIS's bundled Python works):

    C:\\PROGRA~1\\QGIS34~1.13\\bin\\python.exe migrate_alaqs_gui.py

The script's auto-template-selection looks at sibling paths
(open_alaqs/core/templates/*.alaqs and open_alaqs/database/data/), so
the GUI must sit next to migrate_alaqs.py for those defaults to resolve.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

# Import the migration logic from the sibling file.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    import migrate_alaqs  # type: ignore
except ImportError as exc:
    raise SystemExit(
        f"Could not import migrate_alaqs.py from {HERE}.\n"
        f"Place this GUI in the same directory as migrate_alaqs.py."
    ) from exc


# --- stdout/stderr capture --------------------------------------------------


class _SignalStream(io.TextIOBase):
    """File-like object whose .write emits a Qt signal (thread-safe via Qt)."""

    def __init__(self, emit_fn):
        super().__init__()
        self._emit = emit_fn

    def writable(self):
        return True

    def write(self, s):
        if s:
            self._emit(s)
        return len(s) if s else 0

    def flush(self):
        pass


# --- Worker -----------------------------------------------------------------


class MigrationWorker(QObject):
    log = pyqtSignal(str)
    finished = pyqtSignal(int)  # exit code from migrate_alaqs.main

    def __init__(self, argv):
        super().__init__()
        self._argv = argv

    def run(self):
        old_out, old_err = sys.stdout, sys.stderr
        stream = _SignalStream(self.log.emit)
        sys.stdout = stream
        sys.stderr = stream
        try:
            try:
                rc = migrate_alaqs.main(self._argv)
            except SystemExit as e:
                rc = e.code if isinstance(e.code, int) else 1
            except Exception as e:  # noqa: BLE001
                print(f"\nUNCAUGHT ERROR: {e!r}")
                rc = 1
        finally:
            sys.stdout = old_out
            sys.stderr = old_err
        self.finished.emit(rc if rc is not None else 0)


# --- Main window ------------------------------------------------------------

DESTRUCTIVE_QSS = (
    "QGroupBox { color: #b00020; font-weight: bold; border: 1px solid #b00020;"
    " border-radius: 4px; margin-top: 8px; padding-top: 8px; }"
    "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
)
APPLY_QSS = (
    "QPushButton { background-color: #b00020; color: white; font-weight: bold;"
    " padding: 6px 18px; border: none; border-radius: 3px; }"
    "QPushButton:disabled { background-color: #888; }"
    "QPushButton:hover:!disabled { background-color: #d00028; }"
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ALAQS migration")
        self.resize(960, 820)
        self._thread = None
        self._worker = None
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        intro = QLabel(
            "Migrate a legacy .alaqs file to the current Open-ALAQS schema. "
            "Two operations: update the database structure (tables and "
            "columns) by diffing against a template, then optionally refresh "
            "reference-data tables from CSV. Hover any field for details."
        )
        intro.setStyleSheet("color: #444; padding: 4px 2px;")
        intro.setWordWrap(True)
        root.addWidget(intro)

        root.addWidget(self._build_files_box())
        root.addWidget(self._build_phase1_box())
        root.addWidget(self._build_phase2_box())
        root.addWidget(self._build_destructive_box())
        root.addLayout(self._build_actions_row())

        root.addWidget(QLabel("Log:"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        mono = QFont("Courier New")
        mono.setStyleHint(QFont.Monospace)
        self.log_view.setFont(mono)
        self.log_view.setMinimumHeight(220)
        root.addWidget(self.log_view, 1)

    @staticmethod
    def _hint(text, indent=0):
        """Small italic gray helper label shown under a control."""
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color: #666; font-style: italic;"
            + (f" padding-left: {indent}px;" if indent else "")
        )
        lbl.setWordWrap(True)
        return lbl

    def _build_files_box(self):
        box = QGroupBox("Files")
        grid = QGridLayout(box)
        row = 0

        # --- Source
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("path to source .alaqs")
        self.source_edit.setToolTip(
            "The legacy .alaqs file you want to migrate.\n\n"
            "This is your project file (or *_out.alaqs inventory) created with "
            "an older Open-ALAQS version, whose schema needs to be brought up "
            "to date.\n\n"
            "The file is modified in place. A timestamped .bak copy is created "
            "next to it unless --no-backup is set."
        )
        src_btn = QPushButton("Browse…")
        src_btn.clicked.connect(self._pick_source)
        grid.addWidget(QLabel("Source .alaqs:"), row, 0)
        grid.addWidget(self.source_edit, row, 1)
        grid.addWidget(src_btn, row, 2)
        row += 1
        grid.addWidget(
            self._hint("the legacy .alaqs to migrate; modified in place"),
            row,
            1,
            1,
            2,
        )
        row += 1

        # --- Reference
        self.ref_edit = QLineEdit()
        self.ref_edit.setPlaceholderText("(blank = auto-select from filename)")
        self.ref_edit.setToolTip(
            "The canonical template that the source is migrated TO.\n\n"
            "Leave blank to auto-select:\n"
            "  *_out.alaqs      ->  core/templates/inventory.alaqs\n"
            "  everything else  ->  core/templates/project.alaqs\n\n"
            "Set this only to override the auto-selection (e.g. testing "
            "against a custom template)."
        )
        ref_btn = QPushButton("Browse…")
        ref_btn.clicked.connect(self._pick_reference)
        ref_clear = QPushButton("Clear")
        ref_clear.clicked.connect(self.ref_edit.clear)
        ref_h = QHBoxLayout()
        ref_h.setContentsMargins(0, 0, 0, 0)
        ref_h.addWidget(ref_btn)
        ref_h.addWidget(ref_clear)
        grid.addWidget(QLabel("Reference (override):"), row, 0)
        grid.addWidget(self.ref_edit, row, 1)
        grid.addLayout(ref_h, row, 2)
        row += 1
        grid.addWidget(
            self._hint(
                "leave blank to auto-select: inventory.alaqs for *_out.alaqs, "
                "project.alaqs otherwise"
            ),
            row,
            1,
            1,
            2,
        )
        row += 1

        # --- Data dir
        self.data_dir_edit = QLineEdit(str(migrate_alaqs.DEFAULT_DATA_DIR))
        self.data_dir_edit.setToolTip(
            "Directory containing the default_*.csv files used by the "
            "reference-data refresh.\n\n"
            "Defaults to open_alaqs/database/data/, resolved relative to "
            "migrate_alaqs.py's location.\n\n"
            "Ignored unless the refresh step is enabled."
        )
        data_btn = QPushButton("Browse…")
        data_btn.clicked.connect(self._pick_data_dir)
        grid.addWidget(QLabel("Data dir (refresh):"), row, 0)
        grid.addWidget(self.data_dir_edit, row, 1)
        grid.addWidget(data_btn, row, 2)
        row += 1
        grid.addWidget(
            self._hint(
                "folder containing default_*.csv; only used when the refresh step is enabled"
            ),
            row,
            1,
            1,
            2,
        )

        grid.setColumnStretch(1, 1)
        return box

    def _build_phase1_box(self):
        box = QGroupBox("Update database structure  (schema migration)")
        lay = QVBoxLayout(box)
        self.skip_schema = QCheckBox(
            "Skip this step  (--skip-schema; only useful when the refresh below is enabled)"
        )
        self.skip_schema.setToolTip(
            "Skip the schema migration step.\n\n"
            "Only useful for data-only refresh runs (combine with the refresh "
            "section below). The script refuses to run if both this and the "
            "refresh are off — there would be nothing to do."
        )
        lay.addWidget(self.skip_schema)
        return box

    def _build_phase2_box(self):
        box = QGroupBox(
            "Refresh reference data  (optional — airports, emission factors, etc.)"
        )
        lay = QVBoxLayout(box)

        self.refresh_enable = QCheckBox("Enable this step  (--refresh-reference-data)")
        self.refresh_enable.setToolTip(
            "Refresh reference-data tables from CSV files.\n\n"
            "DELETE+INSERT, not merge: rows in the selected tables are wiped "
            "and replaced with the CSV contents. Customizations to refreshed "
            "tables WILL BE LOST.\n\n"
            "User project data tables (user_*, shapes_*) are hardcoded as "
            "never-refreshable and are silently dropped from the refresh list "
            "with a warning, regardless of selection."
        )
        self.refresh_enable.toggled.connect(self._update_phase2_enabled)
        lay.addWidget(self.refresh_enable)

        self.tables_group = QButtonGroup(self)
        self.rad_default = QRadioButton("Update standard reference data  (recommended)")
        self.rad_default.setToolTip(
            "Refreshes these "
            f"{len(migrate_alaqs.DEFAULT_REFRESH_TABLES)} tables:\n  • "
            + "\n  • ".join(migrate_alaqs.DEFAULT_REFRESH_TABLES)
        )
        self.rad_default.setChecked(True)
        self.rad_extended = QRadioButton(
            "Update everything, including aircraft and gates  "
            "(--refresh-include-user-extensible)"
        )
        self.rad_extended.setToolTip(
            "Refreshes the standard tables PLUS these "
            f"{len(migrate_alaqs.USER_EXTENSIBLE_REFRESH_TABLES)} "
            "user-extensible ones:\n  • "
            + "\n  • ".join(migrate_alaqs.USER_EXTENSIBLE_REFRESH_TABLES)
            + "\n\nWILL OVERWRITE any rows you've added to these tables."
        )
        self.rad_custom = QRadioButton("Specific tables only  (--refresh-tables):")
        for i, b in enumerate((self.rad_default, self.rad_extended, self.rad_custom)):
            self.tables_group.addButton(b, i)

        hint_default = self._hint(
            "Airports, vehicle emission factors, stationary source data, "
            "engine modes, APU times. Does not touch aircraft, engines, "
            "profiles, or gate tables.",
            indent=22,
        )
        hint_extended = self._hint(
            "Adds aircraft, aircraft engines, flight profiles, APU & start "
            "emission factors, helicopter engines, and gate profiles. "
            "⚠ Replaces any aircraft or profiles you've customized.",
            indent=22,
        )
        lay.addWidget(self.rad_default)
        lay.addWidget(hint_default)
        lay.addWidget(self.rad_extended)
        lay.addWidget(hint_extended)

        custom_h = QHBoxLayout()
        custom_h.setContentsMargins(0, 0, 0, 0)
        custom_h.addWidget(self.rad_custom)
        self.custom_tables = QLineEdit()
        self.custom_tables.setPlaceholderText("table1,table2,table3")
        self.custom_tables.setToolTip(
            "Comma-separated list of tables to refresh from CSV.\n\n"
            "Looks for <table>.csv inside the data directory.\n\n"
            "User-data tables (user_*, shapes_*) listed here are silently "
            "dropped from the list with a warning in the log."
        )
        custom_h.addWidget(self.custom_tables, 1)
        lay.addLayout(custom_h)

        self.rad_custom.toggled.connect(self.custom_tables.setEnabled)

        self._phase2_children = (
            self.rad_default,
            self.rad_extended,
            self.rad_custom,
            self.custom_tables,
            hint_default,
            hint_extended,
        )
        self._update_phase2_enabled(False)
        return box

    def _build_destructive_box(self):
        box = QGroupBox(
            "Risky options — these can MODIFY or DELETE data and cannot be undone"
        )
        box.setStyleSheet(DESTRUCTIVE_QSS)
        lay = QVBoxLayout(box)

        self.no_backup = QCheckBox("Skip the safety backup  (--no-backup)")
        self.no_backup.setToolTip(
            "Skip the .bak-<timestamp> safety copy of the source file.\n\n"
            "The SQLite transaction still gives you atomic rollback if the "
            "migration itself errors out, but a corrupted source file CANNOT "
            "be recovered without a backup. Recommended only for already-"
            "backed-up files or throwaway test runs."
        )
        lay.addWidget(self.no_backup)
        lay.addWidget(
            self._hint(
                "By default, a timestamped .bak-<UTC>.alaqs copy is saved next to "
                "your source before any change. Disable only if you have your own "
                "backup elsewhere.",
                indent=22,
            )
        )

        self.drop_tables_chk = QCheckBox(
            "Delete tables that aren't in the template  (--drop-extra-tables)"
        )
        self.drop_tables_chk.setToolTip(
            "During the structure update: tables present in YOUR FILE but "
            "absent from the TEMPLATE will be DROPPED.\n\n"
            "Without this flag, extras are reported in the log and left in "
            "place. SpatiaLite virtual tables (SpatialIndex, KNN2, "
            "ElementaryGeometries) are filtered from the diff and never "
            "affected either way."
        )
        lay.addWidget(self.drop_tables_chk)
        lay.addWidget(
            self._hint(
                "Removes any tables in your file that don't exist in the template. "
                "Without this, extras are listed in the log but kept in place.",
                indent=22,
            )
        )

        self.drop_cols_chk = QCheckBox(
            "Delete columns that aren't in the template  (--drop-extra-columns)"
        )
        self.drop_cols_chk.setToolTip(
            "During the structure update: columns present in YOUR FILE but "
            "absent from the TEMPLATE will be DROPPED via the create-copy-"
            "rename pattern (SQLite < 3.35 has no DROP COLUMN).\n\n"
            "Without this flag, extras are reported in the log and left in "
            "place."
        )
        lay.addWidget(self.drop_cols_chk)
        lay.addWidget(
            self._hint(
                "Removes any columns in your file that don't exist in the template. "
                "Without this, extras are listed in the log but kept in place.",
                indent=22,
            )
        )

        return box

    def _build_actions_row(self):
        row = QHBoxLayout()
        row.addStretch(1)
        self.dry_btn = QPushButton("Dry run")
        self.dry_btn.setToolTip(
            "Run the structure update (and refresh, if enabled) in plan-only "
            "mode.\n\n"
            "Prints the edit plan and the list of tables that would be "
            "refreshed. Does NOT modify the source file or create a backup. "
            "Safe to run as many times as you like."
        )
        self.dry_btn.clicked.connect(lambda: self._run(dry=True))
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setToolTip(
            "Execute the migration.\n\n"
            "Creates a timestamped .bak copy unless --no-backup is set. The "
            "whole run is wrapped in a SQLite transaction: if anything "
            "fails, the source file is rolled back and (if backup was "
            "enabled) restored from .bak."
        )
        self.apply_btn.setStyleSheet(APPLY_QSS)
        self.apply_btn.clicked.connect(lambda: self._run(dry=False))
        row.addWidget(self.dry_btn)
        row.addWidget(self.apply_btn)
        return row

    # ------------------------------------------------------------------
    # File pickers
    def _pick_source(self):
        p, _ = QFileDialog.getOpenFileName(
            self,
            "Select source .alaqs",
            self.source_edit.text() or str(Path.home()),
            "ALAQS files (*.alaqs);;All files (*)",
        )
        if p:
            self.source_edit.setText(p)

    def _pick_reference(self):
        p, _ = QFileDialog.getOpenFileName(
            self,
            "Select reference template",
            self.ref_edit.text() or str(HERE),
            "ALAQS files (*.alaqs);;All files (*)",
        )
        if p:
            self.ref_edit.setText(p)

    def _pick_data_dir(self):
        p = QFileDialog.getExistingDirectory(
            self,
            "Select data directory",
            self.data_dir_edit.text() or str(HERE),
        )
        if p:
            self.data_dir_edit.setText(p)

    # ------------------------------------------------------------------
    def _update_phase2_enabled(self, enabled):
        for w in self._phase2_children:
            w.setEnabled(enabled)
        # Custom-tables field is also gated by the radio selection.
        self.custom_tables.setEnabled(enabled and self.rad_custom.isChecked())

    # ------------------------------------------------------------------
    # argv assembly
    def _build_argv(self, dry):
        src = self.source_edit.text().strip()
        if not src:
            QMessageBox.warning(self, "Missing source", "Pick a source .alaqs file.")
            return None
        if not Path(src).is_file():
            QMessageBox.warning(self, "Not found", f"Source file not found:\n{src}")
            return None

        argv = [src]

        ref = self.ref_edit.text().strip()
        if ref:
            argv += ["--reference", ref]

        if dry:
            argv.append("--dry-run")
        if self.no_backup.isChecked():
            argv.append("--no-backup")
        if self.drop_tables_chk.isChecked():
            argv.append("--drop-extra-tables")
        if self.drop_cols_chk.isChecked():
            argv.append("--drop-extra-columns")
        if self.skip_schema.isChecked():
            argv.append("--skip-schema")

        if self.refresh_enable.isChecked():
            argv.append("--refresh-reference-data")
            data_dir = self.data_dir_edit.text().strip()
            if data_dir:
                argv += ["--data-dir", data_dir]
            sel = self.tables_group.checkedId()
            if sel == 1:
                argv.append("--refresh-include-user-extensible")
            elif sel == 2:
                custom = self.custom_tables.text().strip()
                if not custom:
                    QMessageBox.warning(
                        self,
                        "Missing tables",
                        "Custom is selected but the table list is empty.",
                    )
                    return None
                argv += ["--refresh-tables", custom]

        return argv

    # ------------------------------------------------------------------
    def _run(self, dry):
        if self._thread is not None:
            QMessageBox.information(self, "Busy", "A run is already in progress.")
            return

        argv = self._build_argv(dry=dry)
        if argv is None:
            return

        if not dry and not self._confirm_destructive():
            return

        self._append_log(
            "\n" + "=" * 70 + "\n"
            "$ python migrate_alaqs.py "
            + " ".join(self._shell_quote(a) for a in argv)
            + "\n"
            + "=" * 70
            + "\n"
        )

        self._set_running(True)

        self._thread = QThread()
        self._worker = MigrationWorker(argv)
        self._worker.moveToThread(self._thread)
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _confirm_destructive(self):
        warnings = []
        if self.no_backup.isChecked():
            warnings.append(
                "• No safety backup will be made (--no-backup) — original "
                "modified in place"
            )
        if self.drop_tables_chk.isChecked():
            warnings.append(
                "• Tables not in the template will be DELETED " "(--drop-extra-tables)"
            )
        if self.drop_cols_chk.isChecked():
            warnings.append(
                "• Columns not in the template will be DELETED "
                "(--drop-extra-columns)"
            )
        if self.refresh_enable.isChecked() and self.tables_group.checkedId() == 1:
            warnings.append(
                "• Aircraft, engine, profile, APU, helicopter, and gate "
                "tables will be OVERWRITTEN — any custom rows you've added "
                "to those will be lost (--refresh-include-user-extensible)"
            )
        if self.refresh_enable.isChecked():
            warnings.append(
                "• The selected reference tables will be wiped and reloaded " "from CSV"
            )

        msg = QMessageBox(self)
        msg.setWindowTitle("Confirm migration")
        msg.setIcon(QMessageBox.Warning if warnings else QMessageBox.Question)
        text = "Apply the migration to the source file?"
        if warnings:
            text += "\n\n" + "\n".join(warnings)
        msg.setText(text)
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Cancel)
        return msg.exec_() == QMessageBox.Ok

    @staticmethod
    def _shell_quote(a):
        if not a:
            return '""'
        if any(ch in a for ch in ' \t"'):
            return '"' + a.replace('"', '\\"') + '"'
        return a

    def _set_running(self, running):
        self.dry_btn.setEnabled(not running)
        self.apply_btn.setEnabled(not running)

    def _append_log(self, text):
        self.log_view.moveCursor(QTextCursor.End)
        self.log_view.insertPlainText(text)
        self.log_view.moveCursor(QTextCursor.End)

    def _on_finished(self, rc):
        self._append_log(f"\n[exit code: {rc}]\n")
        self._thread.quit()
        self._thread.wait()
        self._thread = None
        self._worker = None
        self._set_running(False)

    def closeEvent(self, e):
        if self._thread is not None:
            r = QMessageBox.question(
                self,
                "Run in progress",
                "A migration run is in progress. Close anyway?\n"
                "(SQLite transactions roll back atomically; the source file "
                "stays consistent, but the log of what happened will be lost.)",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if r != QMessageBox.Yes:
                e.ignore()
                return
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ALAQS migration")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
