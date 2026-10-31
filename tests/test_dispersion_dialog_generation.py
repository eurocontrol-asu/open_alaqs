"""Calculate Dispersion dialog: the two Generate modes (from an OpenALAQS output file and
from CSV files) driven through the real dialog, offscreen.

Each test sets the dialog's controls, runs the Generate button's handler and checks the
written AUSTAL input files (austal.txt, series.dmna).
"""

import hashlib
import shutil
from pathlib import Path

import pytest
from qgis.testing import start_app

start_app()

from qgis.core import QgsSettings  # noqa: E402
from qgis.PyQt import QtCore  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
GENERIC_OUT = REPO / "tests" / "data" / "generic" / "generic_out.alaqs"
AIRPORT_A_OUT = REPO / "tests" / "data" / "AIRPORT_A" / "AIRPORT_A_out.alaqs"
CSV_SAMPLE = REPO / "scripts" / "austal_from_csv" / "sample_data"
POLLUTANTS = ("nox", "pm10", "co")


@pytest.fixture
def dialog():
    settings = QgsSettings()
    for key in settings.allKeys():
        if key.startswith(("OpenALAQS/", "open_alaqs/")):
            settings.remove(key)
    from open_alaqs.gui.DispersionAnalysis import OpenAlaqsDispersionAnalysis

    dlg = OpenAlaqsDispersionAnalysis()
    yield dlg
    dlg.deleteLater()


def _qdt(hour):
    return QtCore.QDateTime(2025, 12, 1, hour, 0, 0)


def generate(
    dlg,
    mode,
    tmp_path,
    receptors_csv=None,
    study_file=GENERIC_OUT,
    pollutants=POLLUTANTS,
):
    """Run the Generate button of `mode` ("alaqs" or "csv"); return the AUSTAL folder."""
    out = tmp_path / mode
    out.mkdir()
    if mode == "alaqs":
        study = tmp_path / "study_out.alaqs"
        shutil.copy(study_file, study)  # the calculation writes to the study file
        dlg.ui.generateFromAlaqsRadio.setChecked(True)
        dlg.ui.alaqs_output_file_path.setFilePath(str(study))
        dlg.ui.alaqs_output_work_dir_path.setFilePath(str(out))
        for p in pollutants:
            getattr(dlg.ui, "alaqs_pollutant_" + p).setChecked(True)
        if receptors_csv:
            dlg.ui.alaqs_receptors_csv_path.setFilePath(str(receptors_csv))
        dlg.ui.alaqs_start_dt_edit.setDateTime(_qdt(6))
        dlg.ui.alaqs_end_dt_edit.setDateTime(_qdt(7))
        dlg._generate_austal_input_files()
        status = dlg.ui.alaqsGenerationStatusLabel.text()
    else:
        dlg.ui.generateFromCsvRadio.setChecked(True)
        dlg.ui.output_directory_path.setFilePath(str(out))
        dlg.ui.emissions_csv_path.setFilePath(str(CSV_SAMPLE / "emissions.csv"))
        dlg.ui.meteo_csv_path.setFilePath(str(CSV_SAMPLE / "meteo.csv"))
        dlg.ui.gridSourceFilePath.setFilePath(str(CSV_SAMPLE / "grid.csv"))
        for p in pollutants:
            getattr(dlg.ui, "pollutant_" + p).setChecked(True)
        if receptors_csv:
            dlg.ui.csv_receptors_csv_path.setFilePath(str(receptors_csv))
        dlg.ui.csv_start_dt_edit.setDateTime(_qdt(6))
        dlg.ui.csv_end_dt_edit.setDateTime(_qdt(7))
        dlg._generate_austal_input_files()
        status = dlg.ui.external_files_feedback.text()
    assert "generated successfully" in status, status
    return out / "AUSTAL"


def austal_lines(austal_dir):
    return (austal_dir / "austal.txt").read_text().splitlines()


def austal_value(austal_dir, key):
    for line in austal_lines(austal_dir):
        if line.split("\t")[0] == key:
            return line.split("\t")[1:]
    raise KeyError(key)


def md5(path):
    return hashlib.md5(path.read_bytes()).hexdigest()


# ---- PM10 fine fraction in CSV mode -------------------------------------------------


def test_csv_mode_pm10_fine_fraction_is_written(dialog, tmp_path):
    assert dialog.ui.csv_pm10_fine_fraction_spinbox.value() == pytest.approx(0.9)
    dialog.ui.csv_pm10_fine_fraction_spinbox.setValue(0.6)
    assert dialog._get_austal_config_from_ui("csv")["pm10_fine_fraction"] == 0.6
    austal = generate(dialog, "csv", tmp_path)
    text = (austal / "austal.txt").read_text()
    assert "pm-1 (fraction 0.60)" in text
    assert "pm-2 (fraction 0.40)" in text


# ---- site parameters (z0, d0, ha) ---------------------------------------------------


def _set_site(dlg, mode, z0, d0, ha):
    widget = dlg._site_parameter_widgets[mode]
    for key, value in zip(
        ("roughness_length_m", "displacement_height_m", "anemometer_height_m"),
        (z0, d0, ha),
    ):
        widget.get_widget(key).setValue(value)


def test_site_parameter_controls_default_to_derive(dialog):
    for mode in ("alaqs", "csv"):
        values = dialog._site_parameter_widgets[mode].get_values()
        assert values == {
            "roughness_length_m": 0.1,
            "displacement_height_m": 0.0,
            "anemometer_height_m": 0.0,
        }
        assert dialog._site_parameters_from_ui(mode) == (0.1, 0.6, 10.6)
    # the labels are those of the AUSTAL module (Dispersion Models tab)
    from open_alaqs.core.modules.AUSTALOutputModule import AUSTALDispersionModule

    label = dialog._site_parameter_widgets["csv"]._settings_labels["roughness_length_m"]
    schema = AUSTALDispersionModule.settings_schema["roughness_length_m"]
    assert label.text() == schema["label"]
    # the module's own default is not changed by the dialog's 0 = derive
    assert AUSTALDispersionModule.settings_schema["displacement_height_m"][
        "initial_value"
    ] == pytest.approx(0.6)


@pytest.mark.parametrize("mode", ["alaqs", "csv"])
def test_site_parameters_are_written_to_austal_txt(dialog, tmp_path, mode):
    _set_site(dialog, mode, 0.5, 0, 0)
    austal = generate(dialog, mode, tmp_path)
    assert austal_value(austal, "z0")[0] == "0.5"
    assert austal_value(austal, "d0")[0] == "3.0"
    assert austal_value(austal, "ha")[0] == "13.0"


def test_explicit_site_parameters_are_kept(dialog, tmp_path):
    _set_site(dialog, "csv", 0.2, 1.2, 11.2)
    austal = generate(dialog, "csv", tmp_path)
    assert [austal_value(austal, k)[0] for k in ("z0", "d0", "ha")] == [
        "0.2",
        "1.2",
        "11.2",
    ]


def test_invalid_site_parameters_stop_the_generation(dialog, tmp_path):
    _set_site(dialog, "csv", 0.1, 5.0, 4.0)  # anemometer below the displacement height
    with pytest.raises(AssertionError, match="ha > d0"):
        generate(dialog, "csv", tmp_path)


# ---- emission settings of Generate from OpenALAQS output ----------------------------


def test_emission_settings_reuse_the_configuration_tab(dialog):
    from open_alaqs.core.EmissionCalculatorService import EmissionCalculatorService
    from open_alaqs.openalaqsdialog import OpenAlaqsResultsAnalysis

    tab = OpenAlaqsResultsAnalysis.settings_schema
    widget = dialog._emission_settings_widget
    # defaults: the settings the dialog used before it had these controls
    assert widget.get_values() == {
        "method": "bymode",
        "should_apply_nox_corrections": False,
        "atmosphere_model": "standard_lapse",
        "bffm2_ff_source": "trajectory",
        "source_dynamics": "none",
    }
    for key in ("atmosphere_model", "bffm2_ff_source", "source_dynamics"):
        combo = widget.get_widget(key)
        assert [combo.itemData(i) for i in range(combo.count())] == list(
            tab[key]["widget_config"]["options"]
        )
        assert widget._settings_labels[key].text() == tab[key]["label"]
    method = widget.get_widget("method")
    assert [method.itemData(i) for i in range(method.count())] == list(
        EmissionCalculatorService().supported_methods
    )
    nox = widget.get_widget("should_apply_nox_corrections")
    assert nox.text() == tab["should_apply_nox_corrections"]["label"]


def _series_columns(austal_dir):
    lines = (austal_dir / "series.dmna").read_text().splitlines()
    form = next(line for line in lines if line.startswith("form")).split("\t")[1:]
    names = [f.strip('"').split("%")[0] for f in form]
    start = lines.index("*") + 1
    rows = [line.split() for line in lines[start:]]
    rows = [row for row in rows if len(row) == len(names)]  # drop the closing ***
    return {name: [row[i] for row in rows] for i, name in enumerate(names)}


def _changed_columns(a, b):
    return sorted(k for k in a if a[k] != b[k])


def _set_emission_settings(dlg, **settings):
    widget = dlg._emission_settings_widget
    for key, value in settings.items():
        control = widget.get_widget(key)
        if isinstance(value, bool):
            control.setChecked(value)
        else:
            control.setCurrentIndex(control.findData(value))
    assert {k: widget.get_values()[k] for k in settings} == settings


def test_emission_settings_reach_the_calculation(tmp_path):
    from open_alaqs.gui.DispersionAnalysis import OpenAlaqsDispersionAnalysis

    def run(name, **settings):
        dlg = OpenAlaqsDispersionAnalysis()
        _set_emission_settings(dlg, **settings)
        (tmp_path / name).mkdir()
        austal = generate(dlg, "alaqs", tmp_path / name, study_file=AIRPORT_A_OUT)
        return _series_columns(austal)

    default = run("default")
    nox = run("nox", should_apply_nox_corrections=True)
    assert _changed_columns(default, nox) == ["01.nox"]
    bffm2 = run("bffm2", method="BFFM2")
    # BFFM2: CO, HC and NOx emission indices and the fuel flow; the other pollutants
    # follow the BFFM2 fuel flow with their per-mode indices, as in the calculation.
    assert {"01.nox", "02.co"} <= set(_changed_columns(default, bffm2))
    anchor = run("anchor", method="BFFM2", bffm2_ff_source="mode_anchor")
    assert _changed_columns(bffm2, anchor)


def test_surface_layer_atmosphere_uses_the_dialog_site_parameters(tmp_path):
    from open_alaqs.gui.DispersionAnalysis import OpenAlaqsDispersionAnalysis

    def run(name, z0):
        dlg = OpenAlaqsDispersionAnalysis()
        _set_emission_settings(dlg, method="BFFM2", atmosphere_model="surface_layer")
        _set_site(dlg, "alaqs", z0, 0, 0)
        (tmp_path / name).mkdir()
        austal = generate(dlg, "alaqs", tmp_path / name, study_file=AIRPORT_A_OUT)
        return _series_columns(austal), {
            f.relative_to(austal): f.read_bytes() for f in austal.rglob("e*.dmna")
        }

    # series.dmna has 4 significant digits: the ambient conditions aloft of a rougher
    # site show in the emission rates or in their vertical distribution
    (smooth, smooth_grids), (rough, rough_grids) = run("smooth", 0.1), run("rough", 2.0)
    assert _changed_columns(smooth, rough) or smooth_grids != rough_grids


# ---- NOTALUFT keeps SCINOTAT --------------------------------------------------------


@pytest.mark.parametrize("mode", ["alaqs", "csv"])
def test_notaluft_keeps_scientific_notation(dialog, tmp_path, mode):
    getattr(dialog.ui, mode + "_notaluft_checkbox").setChecked(True)
    austal = generate(dialog, mode, tmp_path)
    assert austal_value(austal, "os")[0] == '"NOSTANDARD;NOTALUFT;SCINOTAT;Kmax=1"'


def test_tmpa_reader_parses_scientific_notation(tmp_path):
    """The receptor time-series reader (Plot Time Series, Compliance Report) reads the
    hourly values that AUSTAL writes with SCINOTAT."""
    from open_alaqs.core.modules.TimeSeriesDispersionOutputModule import (
        _parse_tmpa_file,
    )

    tmpa = tmp_path / "no2-tmpa.dmna"
    tmpa.write_text(
        "\n".join(
            [
                'idnt\t"test"',
                'unit\t"ug/m3"',
                "rdat\t2025-01-01T00:00:00",
                "dt\t01:00:00",
                "mntn\t01\t02",
                "mntx\t0.0\t10.0",
                "mnty\t0.0\t10.0",
                "hghb\t2\t2",
                "undf\t-1",
                "*",
                "1.234e-05\t2.500e+01",
                "3.000e-30\t4.5",
                "***",
            ]
        )
    )
    data = _parse_tmpa_file(str(tmpa))["data"]
    assert data.tolist() == [[1.234e-05, 25.0], [3e-30, 4.5]]


# ---- receptor heights ---------------------------------------------------------------


@pytest.mark.parametrize("mode", ["alaqs", "csv"])
def test_receptor_csv_heights_reach_austal_txt(dialog, tmp_path, mode):
    receptors = tmp_path / "receptors.csv"
    receptors.write_text(
        "id,longitude,latitude,height\n"
        "R1,4.44,51.96,4.0\n"
        "R2,4.45,51.965,\n"  # empty: 1.5 m
        "R3,4.45,51.97,12.5\n"
    )
    austal = generate(dialog, mode, tmp_path, receptors_csv=receptors)
    assert austal_value(austal, "hp")[:3] == ["4.0", "1.5", "12.5"]
    assert austal_value(austal, "xp")[:2] == ["0.0", "675.98"]


def test_receptor_csv_without_height_uses_1_5_m(dialog, tmp_path):
    receptors = tmp_path / "receptors.csv"
    receptors.write_text("id,longitude,latitude\nR1,4.44,51.96\nR2,4.45,51.965\n")
    austal = generate(dialog, "csv", tmp_path, receptors_csv=receptors)
    assert austal_value(austal, "hp")[:2] == ["1.5", "1.5"]


def test_receptors_of_the_study_file_keep_their_height(dialog, tmp_path):
    import sqlite3

    study = tmp_path / "study_out.alaqs"
    shutil.copy(GENERIC_OUT, study)
    conn = sqlite3.connect(study)
    conn.enable_load_extension(True)
    conn.load_extension("mod_spatialite")  # the table's triggers need SpatiaLite
    with conn:
        conn.executemany(
            "INSERT INTO shapes_receptor_points "
            "(source_id, xcoord, ycoord, height, instudy) VALUES (?, ?, ?, ?, ?)",
            [
                ("RA", 494000.0, 6791000.0, 3.0, "Y"),
                ("RB", 494500.0, 6791500.0, None, None),
                ("RC", 495000.0, 6792000.0, 2.0, "N"),  # not in the study
            ],
        )
    conn.close()
    gdf = dialog._read_receptors_from_alaqs_db(str(study))
    assert gdf is not None and list(gdf["id"]) == ["RA", "RB"]
    assert [p.z for p in gdf.geometry] == [3.0, 1.5]


# ---- a user who changes nothing gets the files of 506696a ---------------------------

# md5 of the files written at 506696a (before the dialog had site parameter, emission
# setting and CSV fine-fraction controls) with the dialog's defaults.
DEFAULT_MD5 = {
    ("alaqs", "austal.txt"): "c0d70c1cbc60ec03b6009399e35c201d",
    ("alaqs", "series.dmna"): "3e5de61f1f0746053710b236ccc084e0",
    ("csv", "austal.txt"): "5a307f0b970cf65b2b4fe70f38375b86",
    ("csv", "series.dmna"): "4c705a3fa4572365a23b4d62a2100549",
}


@pytest.mark.parametrize("mode", ["alaqs", "csv"])
def test_defaults_write_the_same_files_as_before(dialog, tmp_path, mode):
    austal = generate(dialog, mode, tmp_path)
    for name in ("austal.txt", "series.dmna"):
        assert md5(austal / name) == DEFAULT_MD5[(mode, name)], name


# ---- same emissions as the Dispersion Models tab ------------------------------------


def test_inventory_option_matches_the_dispersion_models_tab(dialog, tmp_path):
    """Generate from OpenALAQS output writes the NOx of the emission calculation of the
    Dispersion Models tab (EmissionCalculatorService with the AUSTAL module) for the same
    study, period and settings. AIRPORT_A has flight segments beyond its 10 km grid: the
    tab clips them to the grid (grid_bounds), so must the dialog."""
    import sqlite3
    from datetime import datetime, timedelta

    from open_alaqs.core.EmissionCalculatorService import (
        EmissionCalculationConfig,
        EmissionCalculatorService,
    )

    (tmp_path / "dialog").mkdir()
    austal = generate(
        dialog,
        "alaqs",
        tmp_path / "dialog",
        study_file=AIRPORT_A_OUT,
        pollutants=("nox",),
    )
    dialog_cols = _series_columns(austal)

    study = tmp_path / "tab_out.alaqs"
    shutil.copy(AIRPORT_A_OUT, study)
    with sqlite3.connect(study) as conn:
        row = conn.execute(
            "SELECT x_cells, y_cells, z_cells, x_resolution, y_resolution, "
            "z_resolution, reference_latitude, reference_longitude "
            "FROM grid_3d_definition LIMIT 1"
        ).fetchone()
    keys = (
        "x_cells",
        "y_cells",
        "z_cells",
        "x_resolution",
        "y_resolution",
        "z_resolution",
        "reference_latitude",
        "reference_longitude",
    )
    grid_config = dict(zip(keys, row), reference_altitude=0.0)
    austal_cfg = dialog._get_austal_config_from_ui("alaqs")
    austal_cfg.update(output_path=str(tmp_path / "tab"), title="tab")
    result = EmissionCalculatorService().calculate_emissions(
        EmissionCalculationConfig(
            db_path=str(study),
            start_dt_inclusive=datetime(2025, 12, 1, 6),
            end_dt_inclusive=datetime(2025, 12, 1, 7),
            time_interval=timedelta(hours=1),
            pollutant="NOx",
            grid_config=grid_config,
            dispersion_modules_config={"AUSTAL": austal_cfg},
        )
    )
    assert result.success, result.error_message
    tab_cols = _series_columns(tmp_path / "tab")
    nox = sorted(k for k in dialog_cols if k.endswith(".nox"))
    assert nox and nox == sorted(k for k in tab_cols if k.endswith(".nox"))
    assert [dialog_cols[k] for k in nox] == [tab_cols[k] for k in nox]
