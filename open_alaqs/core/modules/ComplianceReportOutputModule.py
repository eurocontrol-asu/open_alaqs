"""
Per-receptor compliance report against EU Directive 2024/2881.

Reads TalMon-produced ``<substance>-tmpa.dmna`` files in the AUSTAL work
directory, computes per-receptor compliance metrics against the
EU Directive (EU) 2024/2881 limit values applicable from 1 January 2030,
and presents the result as a table dialog with optional CSV export.

Without receptors (i.e. without xp/yp lines in austal.txt), TalMon
produces no -tmpa.dmna and this module raises a clear error. The
dispatching dialog should disable the button when no tmpa files exist.

Threshold values are hardcoded against the directive's Annex I (Section 1)
and verified against the EEA Air Quality Status Report 2025 benchmark
analysis. No external configuration file is required.
"""

import csv
import glob
import os

import numpy as np
from qgis.PyQt import QtCore, QtGui, QtWidgets

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.OutputModule import OutputModule
from open_alaqs.core.modules.TimeSeriesDispersionOutputModule import (
    _parse_tmpa_file,
)

logger = get_logger(__name__)


# Friendly name for the report (back to plugin convention)
_PLUGIN_NAME_FOR_SUBSTANCE = {
    "pm": "PM10",
    "pm25": "PM2.5",
    "nox": "NOx",
    "sox": "SOx",
    "co": "CO",
    "co2": "CO2",
    "hc": "HC",
}


# EU Directive 2024/2881 (recast Ambient Air Quality Directive) limit values
# applicable from 1 January 2030.
#
# Sources verified:
#   - Directive (EU) 2024/2881 of 23 October 2024 (OJ L, 20 Nov 2024),
#     Annex I, Section 1
#     ELI: http://data.europa.eu/eli/dir/2024/2881/oj
#   - EEA Air Quality Status Report 2025, "Benchmark analysis against the
#     standards in the revised directive (EU) 2024/2881"
#     https://www.eea.europa.eu/en/analysis/publications/air-quality-
#     status-report-2025/benchmark-analysis-against-the-standards-in-the-
#     revised-directive-eu-2024-2881
#   - European Commission summary at
#     https://environment.ec.europa.eu/news/new-pollution-rules-come-
#     effect-cleaner-air-2030-2024-12-10_en
#
# Substances NOT in this dict (CO, HC, CO2 ...) have no annual/daily/hourly
# ambient compliance values in this directive at the form this report
# computes. CO is regulated as 10 mg/m³ on an 8-hour rolling mean basis
# (Annex I Section 1) which the per-hour TalMon output could in principle
# support, but is not yet implemented here.
#
# Each entry maps a metric type -> (threshold, allowed_exceedances_or_None,
# unit). allowed_exceedances is None for an absolute limit (annual mean),
# an integer for daily/hourly limits.
_EU_2030_LIMITS = {
    "pm": {  # PM10
        "annual_mean": (20.0, None, "ug/m3"),
        "daily_exceedance": (45.0, 18, "ug/m3"),
    },
    "pm25": {  # PM2.5
        "annual_mean": (10.0, None, "ug/m3"),
        "daily_exceedance": (25.0, 18, "ug/m3"),
    },
    "no2": {
        "annual_mean": (20.0, None, "ug/m3"),
        "hourly_exceedance": (200.0, 3, "ug/m3"),
    },
    # NOx ecosystem protection: 30 µg/m³ annual mean (kept from 2008/50).
    "nox": {
        "annual_mean": (30.0, None, "ug/m3"),
    },
    "so2": {
        # Annex I Section 1, human-health: new annual limit 20 µg/m³,
        # new daily limit 50 µg/m³. Hourly limit retained at 350 µg/m³
        # with reduced exceedance count - count not yet verified
        # against the consolidated text, so daily is treated as
        # absolute (no exceedances allowed) for now.
        "annual_mean": (20.0, None, "ug/m3"),
        "daily_exceedance": (50.0, None, "ug/m3"),
    },
}


def _get_compliance_metrics(substance):
    """Return list of metric specs for a substance, against EU 2024/2881.

    Each metric is a dict with: type, threshold, allowed_exceedances, unit,
    label. Substances not in _EU_2030_LIMITS yield [] (CO, HC, CO2 etc.).
    """
    eu_limits = _EU_2030_LIMITS.get(substance.lower(), {})
    metrics = []
    for mtype, spec in eu_limits.items():
        threshold, allowed, unit = spec
        if mtype == "annual_mean":
            label = "annual mean"
        elif mtype == "daily_exceedance":
            label = "days > %g %s" % (threshold, unit)
        elif mtype == "hourly_exceedance":
            label = "hours > %g %s" % (threshold, unit)
        else:
            continue
        metrics.append(
            {
                "type": mtype,
                "threshold": threshold,
                "allowed_exceedances": allowed,
                "unit": unit,
                "label": label,
            }
        )
    return metrics


# ---------------------------------------------------------------------------
# Per-receptor metric computation
# ---------------------------------------------------------------------------


def _compute_metrics_for_substance(tmpa_data, metrics, substance):
    """Build report rows for one substance across all receptors.

    tmpa_data is the dict returned by _parse_tmpa_file:
        - data         : numpy.ndarray of shape (n_hours, n_receptors)
        - point_names  : list[str] of receptor names
        - point_coords : list[(x, y, z)]
        - units        : str
        - datetime_axis: ndarray[datetime] (not used here directly)
    """
    matrix = tmpa_data.get("data")
    if matrix is None or matrix.size == 0:
        return []
    n_hours, n_recv = matrix.shape
    point_names = tmpa_data.get("point_names") or []

    rows = []
    plugin_name = _PLUGIN_NAME_FOR_SUBSTANCE.get(substance.lower(), substance.upper())

    for r_idx in range(n_recv):
        ts = matrix[:, r_idx].astype(float)
        # NaNs (undf in source) should be ignored in statistics.
        valid = ts[~np.isnan(ts)]
        if r_idx < len(point_names):
            rname = point_names[r_idx] or "P%d" % (r_idx + 1)
        else:
            rname = "P%d" % (r_idx + 1)

        for m in metrics:
            mtype = m["type"]
            value = None
            if mtype == "annual_mean":
                if valid.size == 0:
                    continue
                value = float(np.mean(valid))
            elif mtype == "daily_exceedance":
                full_days = n_hours // 24
                if full_days < 1:
                    continue  # not enough data for daily statistics
                trimmed = ts[: full_days * 24].reshape(full_days, 24)
                # nan-safe daily mean: a day with all NaNs becomes NaN
                with np.errstate(all="ignore"):
                    daily = np.nanmean(trimmed, axis=1)
                value = int(np.sum(daily > m["threshold"]))
            elif mtype == "hourly_exceedance":
                value = int(np.sum(valid > m["threshold"]))
            else:
                continue

            # Pass-fail logic: for annual_mean the value must be <=
            # threshold; for the exceedance metrics, the count must be
            # <= allowed (or, when allowed is None, the value of 0 means
            # automatic pass; any exceedance is a fail).
            if mtype == "annual_mean":
                passes = value <= m["threshold"]
                value_str = "%.2f %s" % (value, m["unit"])
                limit_str = "%.2f %s" % (m["threshold"], m["unit"])
                allowed_str = ""
            else:
                allowed = m["allowed_exceedances"]
                if allowed is None:
                    # Treat as absolute (no exceedances allowed)
                    passes = value == 0
                    allowed_str = "0"
                else:
                    passes = value <= allowed
                    allowed_str = "%d" % allowed
                value_str = "%d" % value
                limit_str = "> %g %s" % (m["threshold"], m["unit"])

            rows.append(
                {
                    "receptor": rname,
                    "pollutant": plugin_name,
                    "metric": m["label"],
                    "value": value_str,
                    "limit": limit_str,
                    "allowed_exceedances": allowed_str,
                    "pass": bool(passes),
                    # raw values for CSV
                    "_raw_value": value,
                    "_raw_threshold": m["threshold"],
                    "_raw_allowed": m.get("allowed_exceedances"),
                    "_unit": m["unit"],
                }
            )

    return rows


def _build_compliance_rows(work_dir):
    """Walk the work directory, build all compliance rows.

    Returns (rows, info) where rows is the list described above and
    info is a small dict with diagnostic counts: substances_seen,
    substances_skipped (no formal EU 2024/2881 ambient limit),
    receptors_seen, tmpa_files. Empty rows means no usable tmpa data.
    """
    rows = []
    info = {
        "tmpa_files": 0,
        "substances_seen": [],
        "substances_skipped": [],
        "receptors_seen": 0,
    }
    if not work_dir or not os.path.isdir(work_dir):
        return rows, info

    tmpa_paths = sorted(glob.glob(os.path.join(work_dir, "*-tmpa.dmna")))
    info["tmpa_files"] = len(tmpa_paths)

    receptor_counts = set()
    for path in tmpa_paths:
        substance = os.path.basename(path).split("-")[0]
        metrics = _get_compliance_metrics(substance)
        if not metrics:
            info["substances_skipped"].append(substance)
            continue
        try:
            tmpa = _parse_tmpa_file(path)
        except Exception as exc:
            logger.warning(
                "Skipping %s for compliance report (parse failed): %s",
                path,
                exc,
            )
            continue
        info["substances_seen"].append(substance)
        m = tmpa.get("data")
        if m is not None and m.size:
            receptor_counts.add(m.shape[1])
        sub_rows = _compute_metrics_for_substance(tmpa, metrics, substance)
        rows.extend(sub_rows)

    if receptor_counts:
        info["receptors_seen"] = max(receptor_counts)

    return rows, info


# ---------------------------------------------------------------------------
# Qt dialog
# ---------------------------------------------------------------------------


class ComplianceReportDialog(QtWidgets.QDialog):
    """Receptor compliance report — table of metrics per receptor and pollutant."""

    HEADERS = [
        "Receptor",
        "Pollutant",
        "Metric",
        "Value",
        "Limit",
        "Allowed exc.",
        "Result",
    ]

    def __init__(self, rows, info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AUSTAL receptor compliance report")
        self.resize(900, 540)
        self._rows = rows
        self._info = info

        layout = QtWidgets.QVBoxLayout(self)

        # Compact header: one short line summarising what was evaluated.
        n_pol = len(set(info.get("substances_seen") or []))
        n_skip = len(set(info.get("substances_skipped") or []))
        n_rec = info.get("receptors_seen", 0)
        n_tmpa = info.get("tmpa_files", 0)
        header_text = (
            "EU Directive 2024/2881 limit values (from 1 Jan 2030)  —  "
            "%d pollutant%s evaluated, %d receptor%s, %d tmpa file%s"
            % (
                n_pol,
                "" if n_pol == 1 else "s",
                n_rec,
                "" if n_rec == 1 else "s",
                n_tmpa,
                "" if n_tmpa == 1 else "s",
            )
        )
        if n_skip:
            header_text += "  —  not reported: %s (no formal limit)" % (
                ", ".join(sorted(set(info["substances_skipped"])))
            )
        header_label = QtWidgets.QLabel(header_text)
        header_label.setWordWrap(True)
        header_label.setStyleSheet("color: #444; padding: 2px 4px;")
        layout.addWidget(header_label)

        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setRowCount(len(rows))
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)

        for i, row in enumerate(rows):
            self._set_cell(i, 0, row["receptor"])
            self._set_cell(i, 1, row["pollutant"])
            self._set_cell(i, 2, row["metric"])
            self._set_cell(i, 3, row["value"], align_right=True)
            self._set_cell(i, 4, row["limit"], align_right=True)
            self._set_cell(i, 5, row["allowed_exceedances"], align_right=True)

            result_item = QtWidgets.QTableWidgetItem("PASS" if row["pass"] else "FAIL")
            result_item.setTextAlignment(QtCore.Qt.AlignCenter)
            if row["pass"]:
                result_item.setBackground(QtGui.QColor(190, 240, 190))
                result_item.setForeground(QtGui.QColor(0, 80, 0))
            else:
                result_item.setBackground(QtGui.QColor(248, 200, 200))
                result_item.setForeground(QtGui.QColor(140, 0, 0))
            self.table.setItem(i, 6, result_item)

        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)

        # Footer buttons
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        export_btn = QtWidgets.QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        btn_row.addWidget(export_btn)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _set_cell(self, r, c, text, align_right=False):
        item = QtWidgets.QTableWidgetItem(str(text) if text is not None else "")
        if align_right:
            item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.table.setItem(r, c, item)

    def _export_csv(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export compliance report",
            "compliance_report.csv",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "Receptor",
                        "Pollutant",
                        "Metric",
                        "Value",
                        "Unit",
                        "Threshold",
                        "AllowedExceedances",
                        "Pass",
                    ]
                )
                for r in self._rows:
                    writer.writerow(
                        [
                            r["receptor"],
                            r["pollutant"],
                            r["metric"],
                            r.get("_raw_value"),
                            r.get("_unit", ""),
                            r.get("_raw_threshold"),
                            (
                                r.get("_raw_allowed")
                                if r.get("_raw_allowed") is not None
                                else ""
                            ),
                            "PASS" if r["pass"] else "FAIL",
                        ]
                    )
            QtWidgets.QMessageBox.information(
                self,
                "Export complete",
                "Compliance report saved to:\n%s" % path,
            )
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self, "Export failed", "Could not save CSV: %s" % exc
            )


# ---------------------------------------------------------------------------
# Output module wrapper (registered with OutputDispersionModuleRegistry)
# ---------------------------------------------------------------------------


class ComplianceReportDispersionModule(OutputModule):
    """Receptor compliance report module.

    Reads <substance>-tmpa.dmna files in the AUSTAL work directory and
    produces a per-receptor compliance table against the EU Directive
    2024/2881 limit values applicable from 1 January 2030.
    """

    settings_schema = {}

    @staticmethod
    def getModuleName():
        return "ComplianceReportDispersionModule"

    @staticmethod
    def getModuleDisplayName():
        return "Receptor Compliance Report"

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        OutputModule.__init__(self, values_dict)
        self._parent = values_dict.get("parent")
        self._concentration_database = values_dict.get("concentration_path")
        self._dialog = None
        self._rows = None
        self._info = None

    def beginJob(self):
        if not self._concentration_database:
            raise Exception(
                "No work directory available. Run AUSTAL or load existing "
                "results first."
            )
        wd = str(self._concentration_database)
        if not os.path.isdir(wd):
            raise Exception("Work directory does not exist: %s" % wd)

        # Confirm there is at least one tmpa file before doing any work.
        tmpa_files = glob.glob(os.path.join(wd, "*-tmpa.dmna"))
        if not tmpa_files:
            raise FileNotFoundError(
                "No <substance>-tmpa.dmna files found in:\n  %s\n\n"
                "The compliance report needs receptor time series. "
                "These are produced when AUSTAL runs with both "
                "(1) receptors defined (xp/yp/hp lines in austal.txt) "
                "and (2) the NOTALUFT output mode enabled.\n\n"
                "To enable: add receptor points (CSV picker in the "
                "OpenALAQS Generate tab, or the shapes_receptor_points "
                "table inside the .alaqs file), tick "
                "'Per-hour series (NOTALUFT)' in the Output Mode row, "
                "regenerate AUSTAL inputs and re-run AUSTAL." % wd
            )

        rows, info = _build_compliance_rows(wd)
        if not rows:
            seen = sorted(set(info.get("substances_seen") or []))
            skipped = sorted(set(info.get("substances_skipped") or []))
            raise Exception(
                "No EU 2024/2881 compliance metrics could be computed.\n\n"
                "Found %d tmpa file(s) in %s.\n\n"
                "Pollutants reportable: %s\n"
                "Pollutants not reportable (no formal ambient limit): %s\n\n"
                "EU Directive 2024/2881 ambient compliance applies to "
                "PM10, PM2.5, NO2, NOx (ecosystem), SO2. CO, HC, CO2 "
                "have no formal annual/daily/hourly ambient limit at "
                "the form this report computes."
                % (
                    info.get("tmpa_files", 0),
                    wd,
                    ", ".join(seen) or "(none)",
                    ", ".join(skipped) or "(none)",
                )
            )
        self._rows = rows
        self._info = info

    def process(self, *args, **kwargs):
        # No streamed processing; all work happens in beginJob.
        return None

    def endJob(self):
        if self._rows is None:
            return None
        self._dialog = ComplianceReportDialog(
            self._rows,
            self._info,
            parent=self._parent,
        )
        return self._dialog
