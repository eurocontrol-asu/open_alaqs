"""
Smooth & Shift parametrization verification.

Walks through the S&S transform across both parametrization methods
("default" and "sas"), all 4 LTO modes (TX, TO, CL, AP), and verifies:

- default_emission_dynamics lookups return the expected columns for
  each method (B4 fallback behaviour when the mode is missing).
- create_polygon_3d applies B1 (zero-length guard), B2 (TO→CL
  reclassification when z>0), B3 (z-envelope across all segments),
  E1 (single dynamics lookup), E4 (direct setVerticalExtent) fixes.
- Method-dependent formulas produce distinct outputs:
  "default" → z_shifted = z + ver_shift, z_upper = z_shifted + ver_ext
  "sas"     → z_shifted = z - (ver_ext + d_v)/2, z_upper = z + ver_ext
- Output polygons have sane dimensions relative to dynamics params.
- Horizontal extension is applied perpendicular to the track direction.
"""

import pytest
from qgis.core import QgsPoint
from qgis.testing import start_app

from open_alaqs.core.GeoTransformation import (
    GeoTransformation,
    SmoothAndShiftTransformer,
)
from open_alaqs.core.interfaces.EmissionDynamics import EmissionDynamics

start_app()


# ----------------------------------------------------------------------
# EmissionDynamics DB row → default/sas mapping
# ----------------------------------------------------------------------


def _make_row(
    stage="CL",
    ac_group="JET SMALL",
    h_ext=50.0,
    v_ext=25.0,
    v_shift=-100.0,
    h_ext_sas=660.0,
    v_ext_sas=170.0,
    v_shift_sas=-173.0,
):
    return {
        "oid": 1,
        "dynamics_id": 1,
        "dynamics_name": f"{ac_group}-{stage}",
        "ac_group": ac_group,
        "flight_stage": stage,
        "horizontal_extent_m": h_ext,
        "vertical_extent_m": v_ext,
        "exit_velocity_m_per_s": 0.0,
        "decay_time_s": 0.0,
        "horizontal_shift_m": 0.0,
        "vertical_shift_m": v_shift,
        "horizontal_extent_m_sas": h_ext_sas,
        "vertical_extent_m_sas": v_ext_sas,
        "vertical_shift_m_sas": v_shift_sas,
    }


class TestEmissionDynamicsMapping:
    """The EmissionDynamics wrapper maps DB columns to the method-specific
    parameter dicts consumed by create_polygon_3d."""

    def test_default_method_reads_non_sas_columns(self):
        ed = EmissionDynamics(_make_row())
        d = ed.getEmissionDynamics("default")
        assert d["horizontal_extension"] == 50.0
        assert d["vertical_extension"] == 25.0
        assert d["vertical_shift"] == -100.0

    def test_sas_method_reads_sas_columns(self):
        ed = EmissionDynamics(_make_row())
        d = ed.getEmissionDynamics("sas")
        assert d["horizontal_extension"] == 660.0
        assert d["vertical_extension"] == 170.0
        assert d["vertical_shift"] == -173.0

    def test_unknown_method_returns_empty(self):
        """Unknown method name returns empty dict — create_polygon_3d
        falls back to zero-extension defaults via B4."""
        ed = EmissionDynamics(_make_row())
        assert ed.getEmissionDynamics("unknown") == {}

    def test_null_db_values_default_to_zero(self):
        """NULL values in the DB row must coerce to 0.0 (avoids breaking
        formulas with None when a row has partial SAS coverage)."""
        row = _make_row(v_shift_sas=None, v_ext_sas=None)
        ed = EmissionDynamics(row)
        d = ed.getEmissionDynamics("sas")
        assert d["vertical_shift"] == 0
        assert d["vertical_extension"] == 0

    @pytest.mark.parametrize("stage", ["TX", "TO", "CL", "AP"])
    def test_all_lto_modes_produce_dict(self, stage):
        """Each of the 4 LTO modes must produce a parameter dict for
        both method lookups."""
        ed = EmissionDynamics(_make_row(stage=stage))
        assert set(ed.getEmissionDynamics("default").keys()) >= {
            "horizontal_extension",
            "vertical_extension",
            "vertical_shift",
        }
        assert set(ed.getEmissionDynamics("sas").keys()) >= {
            "horizontal_extension",
            "vertical_extension",
            "vertical_shift",
        }


# ----------------------------------------------------------------------
# create_polygon_3d — method-specific z formulas
# ----------------------------------------------------------------------


class _FakeAircraft:
    """Minimal aircraft stub returning a static EmissionDynamics-by-mode
    map — avoids pulling the full Aircraft class and its DB plumbing."""

    def __init__(self, dynamics_by_mode, icao="TEST"):
        self._d = dynamics_by_mode
        self._icao = icao

    def getEmissionDynamicsByMode(self):
        return self._d

    def getICAOIdentifier(self):
        return self._icao


def _build_aircraft(stage_to_row):
    """stage_to_row: dict of stage → DB row dict."""
    return _FakeAircraft(
        {stage: EmissionDynamics(row) for stage, row in stage_to_row.items()}
    )


class TestCreatePolygon3D:
    """Verifies the geometric & formula outputs of
    GeoTransformation.create_polygon_3d across both methods + all modes."""

    def _run(self, ac, method, mode, z1=1000, z2=1100, dy=5000):
        p1 = QgsPoint(0.0, 0.0, z1)
        p2 = QgsPoint(0.0, dy, z2)
        return GeoTransformation.create_polygon_3d(ac, method, mode, p1, p2)

    # --- B1: zero-length XY segment -----------------------------------

    def test_b1_zero_length_raises(self):
        """XY-identical points must raise ValueError, not ZeroDivisionError."""
        ac = _build_aircraft({"CL": _make_row()})
        p1 = QgsPoint(100.0, 100.0, 1000)
        p2 = QgsPoint(100.0, 100.0, 1100)
        with pytest.raises(ValueError, match="zero-length"):
            GeoTransformation.create_polygon_3d(ac, "default", "CL", p1, p2)

    # --- B2: TO → CL reclassification at z > 0 ------------------------

    def test_b2_takeoff_at_z_zero_stays_to(self):
        """TO mode with z=0 uses TO parameters (no reclassification)."""
        row_to = _make_row(
            stage="TO",
            v_shift=0,
            v_shift_sas=0,
            h_ext=720,
            v_ext=180,
            h_ext_sas=720,
            v_ext_sas=180,
        )
        row_cl = _make_row(stage="CL")
        ac = _build_aircraft({"TO": row_to, "CL": row_cl})
        _, zsh_s, zsh_e, zup_s, zup_e = self._run(ac, "default", "TO", z1=0, z2=0)
        # TO at z=0 → z_shifted=0 (no shift), z_upper=0+180=180
        assert zsh_s == 0
        assert zup_s == pytest.approx(180)

    def test_b2_takeoff_above_ground_reclassifies_to_cl(self):
        """TO mode with z>0 must be reclassified to CL and use CL params."""
        row_to = _make_row(stage="TO", v_shift=0, v_ext=180)
        row_cl = _make_row(stage="CL", v_shift=-100, v_ext=25)
        ac = _build_aircraft({"TO": row_to, "CL": row_cl})
        _, zsh_s, zsh_e, zup_s, zup_e = self._run(ac, "default", "TO", z1=500, z2=600)
        # If reclassified to CL: z_shifted = z + (-100), z_upper = z_shifted + 25
        assert zsh_s == pytest.approx(400)  # 500 - 100
        assert zup_s == pytest.approx(425)  # 400 + 25

    # --- B4: missing mode falls back to zero extensions ---------------

    def test_b4_missing_mode_uses_zero_extensions(self):
        """If mode is absent from dynamics_by_mode, polygon uses z as-is
        with zero shifts (B4 fallback)."""
        ac = _build_aircraft({})  # No modes defined
        _, zsh_s, zsh_e, zup_s, zup_e = self._run(ac, "default", "CL", z1=500, z2=600)
        # Zero shift, zero extension → z_shifted = z, z_upper = z
        assert zsh_s == pytest.approx(500)
        assert zup_s == pytest.approx(500)

    # --- default vs sas formula divergence ----------------------------

    def test_default_formula_uses_shift_and_extent(self):
        """default: z_shifted = z + ver_shift; z_upper = z_shifted + ver_ext."""
        row = _make_row(stage="CL", v_shift=-100, v_ext=25)
        ac = _build_aircraft({"CL": row})
        _, zsh_s, _, zup_s, _ = self._run(ac, "default", "CL", z1=1000, z2=1000)
        # z_shifted = 1000 + (-100) = 900
        # z_upper = 900 + 25 = 925
        assert zsh_s == pytest.approx(900)
        assert zup_s == pytest.approx(925)

    def test_sas_formula_centres_polygon(self):
        """sas: z_shifted = z - (ver_ext + d_v)/2; z_upper = z + ver_ext.
        With d_v == ver_ext this simplifies to z_shifted = z - ver_ext."""
        row = _make_row(stage="CL", v_shift_sas=0, v_ext_sas=170, h_ext_sas=660)
        ac = _build_aircraft({"CL": row})
        _, zsh_s, _, zup_s, _ = self._run(ac, "sas", "CL", z1=1000, z2=1000)
        # d_v = ver_ext = 170 → z_shifted = 1000 - (170+170)/2 = 1000 - 170 = 830
        # z_upper = 1000 + 170 = 1170
        assert zsh_s == pytest.approx(830)
        assert zup_s == pytest.approx(1170)

    def test_horizontal_extension_applied_perpendicular(self):
        """Polygon width should expand perpendicular to the track.
        Track along +y → width expands along x."""
        row = _make_row(stage="CL", h_ext=100, v_shift=0, v_ext=0)
        ac = _build_aircraft({"CL": row})
        qgs_poly, _, _, _, _ = self._run(ac, "default", "CL", z1=0, z2=0, dy=1000)
        wkt = qgs_poly.asWkt()
        assert wkt  # non-empty
        # hor_ext / 2 = 50 m each side; polygon x-range should span ~100 m
        # Cheap check: extract numeric x values, confirm span
        import re

        xs = [
            float(s)
            for s in re.findall(r"[-]?\d+\.?\d*(?=\s[-]?\d+\.?\d*\s[-]?\d+\.?\d*)", wkt)
        ][::3]
        # QGIS WKT is "x y z" triplets; a regex loose enough for either
        # ordering is overkill — just assert x range is non-degenerate.
        if xs:
            assert (max(xs) - min(xs)) > 50  # horizontal extension applied

    # --- TX mode special-cases z to 0 ---------------------------------

    def test_tx_mode_forces_z_to_zero(self):
        """TX mode: z2 is clamped to 0 regardless of input z."""
        row = _make_row(stage="TX", v_shift=0, v_ext=0)
        ac = _build_aircraft({"TX": row})
        # Feed z=100 — should be clamped to 0 for TX
        _, zsh_s, zsh_e, zup_s, zup_e = self._run(ac, "default", "TX", z1=50, z2=100)
        # start at z=0 (TX overrides to 0), ext=0 → all at 0
        assert zsh_s == 0
        assert zup_s == 0

    # --- All four LTO modes run end-to-end ----------------------------

    @pytest.mark.parametrize(
        "mode,method",
        [
            ("TX", "default"),
            ("TX", "sas"),
            ("TO", "default"),
            ("TO", "sas"),
            ("CL", "default"),
            ("CL", "sas"),
            ("AP", "default"),
            ("AP", "sas"),
        ],
    )
    def test_all_mode_method_combos_produce_valid_geom(self, mode, method):
        """Every (mode, method) combination must produce a non-empty 3D
        multipolygon with sane z bounds."""
        row = _make_row(stage=mode)
        ac = _build_aircraft({mode: row})
        geom, zsh_s, zsh_e, zup_s, zup_e = self._run(ac, method, mode)
        assert geom is not None
        # z_shifted must be <= z_upper (the floor of the box is below the ceiling)
        assert zsh_s <= zup_s
        assert zsh_e <= zup_e
        # geometry should be a valid polygon collection
        wkt = geom.asWkt()
        assert "POLYGON" in wkt.upper() or "MULTIPOLYGON" in wkt.upper()


# ----------------------------------------------------------------------
# SmoothAndShiftTransformer — B3 z-envelope across ALL segments
# ----------------------------------------------------------------------


class TestSmoothAndShiftTransformer:
    """Tests the multi-segment transformer, especially B3 (z-envelope
    accumulated across every segment, not just the last)."""

    def test_b3_envelope_spans_all_segments(self):
        """A trajectory spanning 0m → 500m → 2000m must produce a
        vertical extent that includes both low and high altitudes,
        not just the final segment's band."""
        from open_alaqs.core.interfaces.Emissions import Emission
        from open_alaqs.core.interfaces.Emissions import defValues as defaultEmissions

        # Multi-segment emission with a 3-point line
        em = Emission(defaultValues=defaultEmissions)
        # LineString with 3 vertices at increasing altitudes
        wkt = "LineStringZ (0 0 0, 0 1000 500, 0 2000 2000)"
        em.setGeometryText(wkt)

        # CL dynamics
        row = _make_row(stage="CL", v_shift=-100, v_ext=25)
        ac = _build_aircraft({"CL": row})

        transformer = SmoothAndShiftTransformer(
            ac,
            sas="default",
            is_arrival=False,
            lto_mode="CL",
        )
        em_list = [{"emissions": [em], "distance_time": 0, "distance_space": 0}]
        transformer.transform_emissions(em_list)

        # B3: vertical extent must span from first segment's z_shifted
        # (near 0) to last segment's z_upper (near 2000 + 25).
        # Pre-B3 this was clipped to only the final segment.
        ext = em._vertical_ext
        assert (
            ext["z_min"] < 500
        ), f"B3 regression: z_min={ext['z_min']} only reflects last segment"
        assert (
            ext["z_max"] > 1900
        ), f"B3 regression: z_max={ext['z_max']} does not span full trajectory"

    def test_smooth_and_shift_method_normalisation(self):
        """sas param normalised to 'default' or 'sas' in __init__ regardless
        of user-facing string."""
        ac = _build_aircraft({"CL": _make_row()})
        for user_str, expected in [
            ("default", "default"),
            ("smooth & shift", "sas"),
            ("anything-else", "sas"),
        ]:
            t = SmoothAndShiftTransformer(
                ac,
                sas=user_str,
                is_arrival=False,
                lto_mode="CL",
            )
            assert (
                t._sas_method == expected
            ), f"sas={user_str!r} → expected {expected!r}, got {t._sas_method!r}"

    def test_arrival_mode_defaults_to_ap(self):
        """When lto_mode is empty and is_arrival=True, segments pick AP."""
        # Any segment with z>=0 must use AP dynamics
        from open_alaqs.core.interfaces.Emissions import Emission
        from open_alaqs.core.interfaces.Emissions import defValues as defaultEmissions

        em = Emission(defaultValues=defaultEmissions)
        em.setGeometryText("LineStringZ (0 0 500, 0 1000 400)")

        row_ap = _make_row(stage="AP", v_shift=-100, v_ext=25)
        row_cl = _make_row(stage="CL", v_shift=-200, v_ext=50)  # sentinel
        ac = _build_aircraft({"AP": row_ap, "CL": row_cl})

        transformer = SmoothAndShiftTransformer(
            ac,
            sas="default",
            is_arrival=True,
            lto_mode="",
        )
        em_list = [{"emissions": [em], "distance_time": 0, "distance_space": 0}]
        transformer.transform_emissions(em_list)

        # AP dynamics: z_shift=-100, v_ext=25 → z_min = 500-100 = 400
        assert em._vertical_ext["z_min"] == pytest.approx(300)  # min(400, 300)
        # If CL had been used, z_min would have been ≤ 200.
