"""
TimeSeriesDispersionOutputModule
================================

Plots an AUSTAL TalMon time-series at user-defined monitor points.

Input file: ``<pollutant>-tmpa.dmna`` in the AUSTAL work directory.
This file is written by TalMon (the AUSTAL companion that extracts
time-series at monitor points) when AUSTAL is run with the NOTALUFT
option AND ``xp / yp`` lines are present in ``austal.txt``.

The file contains a ``time x point`` matrix (typically 8760 x N where
N is the number of monitor points) plus header metadata describing
each point's name, coordinates, grid cell and the run start time.

This module replaces a prior implementation that read 8760 separate
grid files and pulled one cell from each. TalMon's ``-tmpa`` already
contains exactly the time series we need, in one ~1 MB file.
"""

import os
from collections import OrderedDict
from datetime import datetime, timedelta

import matplotlib
import numpy as np
import pandas as pd

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.OutputModule import OutputModule

matplotlib.use("Qt5Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_qt5agg import FigureCanvas  # noqa: E402
from matplotlib.backends.backend_qt5agg import (
    NavigationToolbar2QT as NavigationToolbar,
)  # noqa: E402
from matplotlib.dates import DateFormatter  # noqa: E402
from qgis.PyQt import QtWidgets  # noqa: E402

logger = get_logger(__name__)


def _austal_substance_for_results(plugin_pollutant):
    """Map plugin pollutant name to AUSTAL substance name for output files.

    AUSTAL writes <substance>-y00a.dmna, <substance>-tmpa.dmna, etc.
    Most plugin names lowercase directly to the AUSTAL substance name
    (NOx -> nox, CO -> co, HC -> hc), but PM is special:
        PM10 -> 'pm'    (AUSTAL sums components 1+2 into pm-y00a.dmna)
        PM2.5 -> 'pm25' (single-component substance)
    """
    if not plugin_pollutant:
        return ""
    p = plugin_pollutant.upper()
    if p == "PM10":
        return "pm"
    if p in ("PM25", "PM2.5", "PM-2.5"):
        return "pm25"
    return plugin_pollutant.lower()


# ---------------------------------------------------------------------------
# DMNA tmpa parser
# ---------------------------------------------------------------------------


def _parse_tmpa_file(path):
    """Parse a TalMon ``<pollutant>-tmpa.dmna`` file.

    Returns a dict with:
        datetime_axis  ndarray[datetime] of length n_time
        data           ndarray[n_time, n_points] of float (NaN for undf)
        point_names    list[str]
        point_coords   list[tuple[float, float, float]]   (x, y, z metres
                       relative to ref origin)
        units          str   (typically "ug/m3")
        project_name   str   (from ``idnt`` in header, may be empty)
        pollutant      str   (from ``name`` in header, lowercased)
    """
    with open(path, encoding="latin-1", errors="ignore") as f:
        raw = [line.rstrip("\n").rstrip("\r") for line in f]

    header = OrderedDict()
    data_start = None
    for i, line in enumerate(raw):
        stripped = line.strip().replace('"', "")
        if not stripped:
            continue
        if stripped.startswith("*"):
            data_start = i + 1
            break
        parts = stripped.split()
        if parts:
            header[parts[0]] = parts[1:]

    if data_start is None:
        raise Exception(
            "DMNA file '%s' has no data-block delimiter '*'; "
            "the file appears truncated or malformed." % path
        )

    for required in ("mntn", "mntx", "mnty", "rdat", "dt", "hghb", "unit"):
        if required not in header:
            raise Exception(
                "DMNA file '%s' is missing required header key '%s'. "
                "This may not be a TalMon -tmpa file." % (path, required)
            )

    point_names = list(header["mntn"])
    mntx = [float(v) for v in header["mntx"]]
    mnty = [float(v) for v in header["mnty"]]
    mntz = [float(v) for v in header.get("mntz", ["0.0"] * len(point_names))]
    point_coords = list(zip(mntx, mnty, mntz))

    n_time = int(header["hghb"][0])
    n_points = int(header["hghb"][1])
    if len(point_names) != n_points:
        logger.warning(
            "tmpa file '%s': mntn count (%d) doesn't match hghb point "
            "count (%d). Adjusting to hghb count.",
            path,
            len(point_names),
            n_points,
        )
        if len(point_names) < n_points:
            point_names = point_names + [
                str(i + 1) for i in range(len(point_names), n_points)
            ]
        else:
            point_names = point_names[:n_points]
        if len(point_coords) < n_points:
            point_coords = point_coords + [(0.0, 0.0, 0.0)] * (
                n_points - len(point_coords)
            )
        else:
            point_coords = point_coords[:n_points]

    rdat_str = header["rdat"][0]
    try:
        t0 = datetime.fromisoformat(rdat_str).replace(tzinfo=None)
    except Exception:
        logger.warning(
            "Could not parse rdat='%s'; defaulting to 2025-01-01",
            rdat_str,
        )
        t0 = datetime(2025, 1, 1)

    dt_str = header["dt"][0]
    try:
        h, m, s = dt_str.split(":")
        delta = timedelta(hours=int(h), minutes=int(m), seconds=int(s))
        if delta.total_seconds() <= 0:
            delta = timedelta(hours=1)
    except Exception:
        delta = timedelta(hours=1)

    datetime_axis = np.array([t0 + i * delta for i in range(n_time)])

    flat = []
    for line in raw[data_start:]:
        line = line.strip()
        if not line or line.startswith("*"):
            continue
        for token in line.split():
            try:
                flat.append(float(token))
            except ValueError:
                pass

    expected = n_time * n_points
    if len(flat) < expected:
        raise Exception(
            "DMNA data short: expected %d values (%d time x %d points), "
            "got %d in '%s'." % (expected, n_time, n_points, len(flat), path)
        )
    data = np.array(flat[:expected], dtype=float).reshape(n_time, n_points)
    undf = float(header.get("undf", ["-1"])[0])
    data = np.where(data == undf, np.nan, data)

    return {
        "datetime_axis": datetime_axis,
        "data": data,
        "point_names": point_names,
        "point_coords": point_coords,
        "units": header["unit"][0] if header["unit"] else "",
        "project_name": (header.get("idnt", [""])[0] if header.get("idnt") else ""),
        "pollutant": (
            header.get("name", [""])[0].lower() if header.get("name") else ""
        ),
    }


# ---------------------------------------------------------------------------
# Plot dialog
# ---------------------------------------------------------------------------


class TimeSeriesPlotDialog(QtWidgets.QDialog):
    """Plot dialog: one line per monitor point, with a smoothing combo."""

    SMOOTHING_OPTIONS = [
        ("Raw (hourly)", "raw"),
        ("8-hour rolling mean", "8h"),
        ("24-hour rolling mean", "24h"),
        ("Monthly mean", "monthly"),
    ]

    def __init__(self, parent, parsed, pollutant_label, time_start=None, time_end=None):
        super().__init__(parent)
        self.setWindowTitle("Time Series - %s" % pollutant_label.upper())
        self.resize(950, 620)

        self._datetime_axis = parsed["datetime_axis"]
        self._data = parsed["data"]
        self._point_names = parsed["point_names"]
        self._point_coords = parsed["point_coords"]
        self._units = parsed["units"]
        self._project_name = parsed["project_name"]
        self._pollutant_label = pollutant_label

        if time_start is not None or time_end is not None:
            mask = np.ones(len(self._datetime_axis), dtype=bool)
            if time_start is not None:
                mask &= self._datetime_axis >= time_start
            if time_end is not None:
                mask &= self._datetime_axis <= time_end
            if mask.any():
                self._datetime_axis = self._datetime_axis[mask]
                self._data = self._data[mask, :]
            else:
                logger.warning(
                    "Time-window [%s, %s] excludes all tmpa data; "
                    "showing full year.",
                    time_start,
                    time_end,
                )

        plt.ioff()
        self._figure = plt.figure(figsize=(9, 5))
        self._axes = self._figure.add_subplot(111)
        self._canvas = FigureCanvas(self._figure)
        self._canvas.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self._toolbar = NavigationToolbar(self._canvas, parent=self)

        self._smoothing_combo = QtWidgets.QComboBox()
        for label, _ in self.SMOOTHING_OPTIONS:
            self._smoothing_combo.addItem(label)
        self._smoothing_combo.currentIndexChanged.connect(self._redraw)

        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(QtWidgets.QLabel("Smoothing:"))
        controls.addWidget(self._smoothing_combo)
        controls.addStretch(1)
        export_btn = QtWidgets.QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        controls.addWidget(export_btn)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        controls.addWidget(close_btn)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(self._toolbar)
        layout.addWidget(self._canvas)
        self.setLayout(layout)

        self._redraw()

    def _smoothed(self, key):
        x = self._datetime_axis
        y = self._data
        if key == "raw":
            return x, y
        if key in ("8h", "24h"):
            window = 8 if key == "8h" else 24
            df = pd.DataFrame(y)
            ys = df.rolling(window=window, min_periods=1).mean().values
            return x, ys
        if key == "monthly":
            df = pd.DataFrame(y, index=pd.DatetimeIndex(x))
            monthly = df.resample("MS").mean()
            return monthly.index.to_pydatetime(), monthly.values
        return x, y

    def _redraw(self, *_args):
        idx = self._smoothing_combo.currentIndex()
        label, key = self.SMOOTHING_OPTIONS[idx]
        x, y = self._smoothed(key)

        self._axes.clear()
        for i, name in enumerate(self._point_names):
            self._axes.plot(x, y[:, i], label="P%s" % name, linewidth=1.0)

        title = "%s time series" % self._pollutant_label.upper()
        if self._project_name:
            title += " - %s" % self._project_name
        if key != "raw":
            title += " (%s)" % label
        self._axes.set_title(title)
        self._axes.set_ylabel("Concentration [%s]" % self._units)
        self._axes.set_xlabel("Time")
        self._axes.legend(loc="best", fontsize=8, ncol=min(4, len(self._point_names)))
        self._axes.grid(True, alpha=0.3)

        if key == "monthly":
            self._axes.xaxis.set_major_formatter(DateFormatter("%Y-%m"))
        else:
            self._axes.xaxis.set_major_formatter(DateFormatter("%Y-%m-%d"))
        self._figure.autofmt_xdate()
        self._figure.tight_layout()
        self._canvas.draw()

    def _export_csv(self):
        suggested = "%s_timeseries.csv" % self._pollutant_label.lower()
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Time Series CSV", suggested, "CSV files (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    "datetime," + ",".join("P%s" % n for n in self._point_names) + "\n"
                )
                for i, ts in enumerate(self._datetime_axis):
                    row = [ts.isoformat()] + [
                        "" if np.isnan(v) else "%.4g" % v for v in self._data[i, :]
                    ]
                    f.write(",".join(row) + "\n")
            QtWidgets.QMessageBox.information(
                self,
                "Export OK",
                "CSV written to:\n%s" % path,
            )
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Export failed", str(e))


# ---------------------------------------------------------------------------
# Output module class (called by DispersionAnalysis.runOutputModule)
# ---------------------------------------------------------------------------


class TimeSeriesDispersionModule(OutputModule):
    """Plot AUSTAL TalMon time-series at monitor points."""

    settings_schema = {}

    @staticmethod
    def getModuleName():
        return "TimeSeriesDispersionModule"

    @staticmethod
    def getModuleDisplayName():
        return "Time Series"

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        OutputModule.__init__(self, values_dict)
        self._parent = values_dict.get("parent")
        # Plugin pollutant name (e.g. "PM10"); we keep both this and the
        # AUSTAL substance code (e.g. "pm") because AUSTAL output filenames
        # use the substance code, not the plugin name.
        plugin_poll = (values_dict.get("pollutant") or "").strip()
        self._pollutant = plugin_poll.lower()  # used for display labels
        self._austal_substance = _austal_substance_for_results(plugin_poll)
        self._concentration_database = values_dict.get("concentration_path")
        self._time_start = values_dict.get("start_dt_inclusive")
        self._time_end = values_dict.get("end_dt_inclusive")
        self._parsed = None

    def beginJob(self):
        if not self._pollutant:
            raise Exception(
                "No pollutant selected. Please pick a pollutant in the "
                "result visualisation panel before plotting."
            )
        if not self._concentration_database:
            raise Exception(
                "No work directory available. Run AUSTAL or load existing "
                "results first."
            )
        wd = str(self._concentration_database)
        if not os.path.isdir(wd):
            raise Exception("Work directory does not exist: %s" % wd)

        tmpa_path = os.path.join(wd, "%s-tmpa.dmna" % self._austal_substance)
        if not os.path.isfile(tmpa_path):
            # Distinguish the two failure modes with a list of what IS
            # available in this work directory:
            #   - "no tmpa files at all" -> NOTALUFT/receptors missing,
            #     re-run AUSTAL
            #   - "tmpa files exist for other pollutants" -> the user
            #     picked a pollutant that wasn't in the AUSTAL run,
            #     point them at what is available
            import glob as _glob

            existing = sorted(_glob.glob(os.path.join(wd, "*-tmpa.dmna")))
            if not existing:
                raise FileNotFoundError(
                    "No TalMon time-series files in this work directory:\n"
                    "  %s\n\n"
                    "Plot Time Series requires the AUSTAL run to have:\n"
                    "  1. Output Mode set to 'Per-hour series (NOTALUFT)' "
                    "(checkbox in the Generate tab), AND\n"
                    "  2. Monitor points (xp / yp lines) defined in "
                    "austal.txt (provide a Receptors CSV in the Generate "
                    "tab, or populate shapes_receptor_points in the "
                    ".alaqs file).\n\n"
                    "Re-run AUSTAL with both conditions met to produce "
                    "<pollutant>-tmpa.dmna files." % wd
                )
            available = sorted({os.path.basename(p).split("-")[0] for p in existing})
            # Map AUSTAL substance back to plugin pollutant name
            sub_to_plugin = {
                "pm": "PM10",
                "pm25": "PM2.5",
                "nox": "NOx",
                "sox": "SOx",
                "co": "CO",
                "co2": "CO2",
                "hc": "HC",
                "no2": "NO2",
                "so2": "SO2",
            }
            available_plugin_names = [
                sub_to_plugin.get(s, s.upper()) for s in available
            ]
            requested_plugin = self._pollutant.upper() if self._pollutant else "?"
            raise FileNotFoundError(
                "Time-series file not found for the selected pollutant: %s\n"
                "  expected: %s\n\n"
                "This pollutant is not in the current AUSTAL run output. "
                "Available pollutants in this work directory:\n"
                "  %s\n\n"
                "Either pick one of the available pollutants in the result "
                "panel, or re-run AUSTAL with %s included in the pollutant "
                "selection (Generate tab)."
                % (
                    requested_plugin,
                    tmpa_path,
                    ", ".join(available_plugin_names),
                    requested_plugin,
                )
            )

        try:
            self._parsed = _parse_tmpa_file(tmpa_path)
        except Exception as e:
            raise Exception("Failed to parse TalMon file '%s': %s" % (tmpa_path, e))

        file_pollutant = (self._parsed.get("pollutant") or "").lower()
        if file_pollutant and file_pollutant != self._austal_substance:
            logger.warning(
                "tmpa file pollutant tag '%s' differs from expected "
                "AUSTAL substance '%s' (plugin pollutant: %s)",
                file_pollutant,
                self._austal_substance,
                self._pollutant,
            )
        return True

    def process(self, **_kwargs):
        return True

    def endJob(self):
        if self._parsed is None:
            return None
        dialog = TimeSeriesPlotDialog(
            parent=self._parent,
            parsed=self._parsed,
            pollutant_label=self._pollutant,
            time_start=self._time_start,
            time_end=self._time_end,
        )
        return dialog
