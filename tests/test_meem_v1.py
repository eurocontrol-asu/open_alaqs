"""
MEEM V1 regression tests against the ICAO CAEP14 FBE Engines Emissions
Calculation Sheet v14 (tabs MEEM_V1, USER INPUTS, Constants).

Reference values:
  - Stored example of the sheet (USER INPUTS as delivered): engine 01P20CM127,
    22500 ft, CLIMB TO CRUISE, TAS 428.49 kt, RH 60 %, delta T 0, cruise
    altitude 38000 ft, OPR 30: MEEM_V1!B119 = 0.944536653843135 mg/kg and
    B120 = 2.58597485320693e13 #/kg (cached values of the workbook).
  - Other cases: the sheet recalculated in LibreOffice 24.2 with the USER
    INPUTS below. LibreOffice 24.2 has no SORT/FILTER, so the sorted point
    tables MEEM_V1!C88:D91 and C96:D99 were replaced by the fixed 4-point
    order (7 %, 30 %, 85 %, 100 %) for the recalculation; all the other cells
    are the sheet's formulas. The recalculation reproduces the stored example
    to 1e-15. Four cases have a temperature deviation (USER INPUTS!B5); the
    -5.1825 K one is the delta T of the training example (283 K at -5 m).

At or below 3000 ft (LTO) the sheet returns the certification value of the
mode (no interpolation, no correction): the anchor tests.
"""

import pytest

from open_alaqs.core.tools.meem_v1 import (
    calculate_nvpm_ei,
    delta_t_from_ground,
    interpolate_ei,
    isa_ambient,
    pressure_coefficient,
    section_of_flight,
)

_TS = [1.0, 0.85, 0.30, 0.07]  # TO, CL, AP, TX

# Engines_Database of the sheet: PRESS_RATIO, NVPM_M_*_MG/KG, NVPM_N_*_N/KG
_ENGINES = {
    "01P20CM127": (
        30.0,
        [1.35458150221701, 1.03598718120316, 1.85003357629324, 0.788067430941943],
        [107147000375.795, 92348579066.5577, 276096126031350, 13005424535946.3],
    ),
    "01P20CM128": (
        33.3,
        [1.6270256714414, 1.23517541065843, 2.98855587397408, 0.683860589780375],
        [119654243894.608, 100052658632.405, 456827575055365, 10901015768971.4],
    ),
    "11GE144": (
        27.2,
        [73.7415341769357, 53.301741608788, 2.79689622305639, 5.3325761855363],
        [464865790499195, 336013571246026, 141052815153605, 268931995685205],
    ),
}

# (engine, altitude ft, phase, TAS kt, delta T K, cruise altitude ft)
#   -> (B83 thrust, B119 mass mg/kg, B120 number #/kg)
_SHEET_CASES = [
    (
        ("01P20CM127", 22500, "CLIMB TO CRUISE", 428.49, 0.0, 38000),
        (0.7887145601010004, 0.944536653843135, 2.58597485320693e13),
    ),
    (
        ("01P20CM127", 8000, "CLIMB TO CRUISE", 280, 0.0, 38000),
        (0.8348976022035491, 1.169462798467009, 8476555606056.236),
    ),
    (
        ("01P20CM127", 12000, "DESCENT TO APPROACH", 300, 0.0, 38000),
        (0.10274033269749813, 0.9340576233694476, 50177927487796.09),
    ),
    (
        ("11GE144", 4500, "CLIMB TO CRUISE", 220, 0.0, 38000),
        (0.836680133114006, 61.22075397785308, 389448647438752.9),
    ),
    (
        ("11GE144", 5000, "DESCENT TO APPROACH", 210, 0.0, 38000),
        (0.11379018347519793, 5.588363301978656, 281831828205551.56),
    ),
    (
        ("01P20CM128", 3500, "CLIMB TO CRUISE", 200, 0.0, 38000),
        (0.837316143704763, 1.5260688609694564, 12720599785837.182),
    ),
    (
        ("01P20CM128", 39000, "CRUISE", 450, 10.0, 38000),
        (0.6075261182483186, 0.8493868216612246, 85207826176777.17),
    ),
    (
        ("11GE144", 30000, "CLIMB TO CRUISE", 420, -5.0, 35000),
        (0.6446938481236183, 27.083099737453495, 206951650850677.44),
    ),
    (
        ("11GE144", 4500, "CLIMB TO CRUISE", 220, -5.1825, 38000),
        (0.7849739365883964, 60.52925750077077, 400236880720932.9),
    ),
    (
        ("11GE144", 5000, "DESCENT TO APPROACH", 210, 12.0, 38000),
        (0.13248463510116748, 4.55684516335939, 229810399546587.56),
    ),
]


class TestMEEMV1SheetReference:
    """Non-LTO branch: the sheet's values to floating-point noise."""

    @pytest.mark.parametrize("inputs, expected", _SHEET_CASES)
    def test_matches_sheet(self, inputs, expected):
        engine, alt_ft, phase, tas_kt, delta_t, cruise_ft = inputs
        opr, mass, number = _ENGINES[engine]
        r = calculate_nvpm_ei(
            phase=phase,
            altitude_ft=alt_ft,
            thrust_settings=_TS,
            ei_mass_mgkg=mass,
            ei_number_nkg=number,
            opr=opr,
            tas_kt=tas_kt,
            delta_t=delta_t,
            cruise_altitude_ft=cruise_ft,
        )
        thrust, mass_ref, number_ref = expected
        assert r.flight_section == "Non LTO"
        assert r.gr_thrust == pytest.approx(thrust, rel=1e-12)
        assert r.nvpm_mass_ei_mgkg == pytest.approx(mass_ref, rel=1e-12)
        assert r.nvpm_number_ei_nkg == pytest.approx(number_ref, rel=1e-12)

    def test_stored_example_intermediate_cells(self):
        """MEEM_V1 intermediate cells of the stored example."""
        opr, mass, number = _ENGINES["01P20CM127"]
        r = calculate_nvpm_ei(
            "CLIMB TO CRUISE", 22500, _TS, mass, number, opr=opr, tas_kt=428.49
        )
        assert r.mach == pytest.approx(0.7045643104991359, rel=1e-12)  # B17
        assert r.T_amb == pytest.approx(243.57299857353598, rel=1e-12)  # B47
        assert r.P_amb == pytest.approx(41888.29383521342, rel=1e-12)  # B48
        assert r.T3_alt == pytest.approx(771.3359775104177, rel=1e-12)  # B65
        assert r.P3_alt == pytest.approx(1779237.7074678312, rel=1e-12)  # B66
        assert r.P3_gr == pytest.approx(2418903.581264782, rel=1e-12)  # B77
        assert r.nvpm_mass_ei_gr_mgkg == pytest.approx(
            1.1266948019691427, rel=1e-12
        )  # B101
        assert r.nvpm_number_ei_gr_nkg == pytest.approx(
            30846917515337.062, rel=1e-12
        )  # B102

    def test_pressure_coefficient(self):
        """MEEM_V1!B26 of the stored example and the constant phases."""
        assert pressure_coefficient("CLIMB TO CRUISE", 22500) == pytest.approx(
            1.0171428571428571, rel=1e-14
        )
        assert pressure_coefficient("CLIMB TO CRUISE", 3000) == 0.85
        assert pressure_coefficient("DESCENT TO APPROACH", 8000) == 0.12
        assert pressure_coefficient("CRUISE", 38000) == 0.95

    def test_isa_above_tropopause(self):
        """USER INPUTS!B44/B45 above 11 km: isothermal layer."""
        t, p = isa_ambient(39000)
        assert t == pytest.approx(216.65, abs=1e-9)
        assert p < isa_ambient(36000)[1]


class TestMEEMV1Anchors:
    """LTO branch: the certification value of the mode, exactly."""

    @pytest.mark.parametrize(
        "phase, index",
        [("TAKE OFF", 0), ("CLIMB OUT", 1), ("APPROACH", 2), ("TAXI", 3)],
    )
    def test_lto_phase_returns_mode_value(self, phase, index):
        opr, mass, number = _ENGINES["11GE144"]
        r = calculate_nvpm_ei(phase, 2000, _TS, mass, number, opr=opr, tas_kt=150)
        assert r.flight_section == "LTO"
        assert r.nvpm_mass_ei_mgkg == mass[index]
        assert r.nvpm_number_ei_nkg == number[index]

    def test_lto_ceiling(self):
        """USER INPUTS!B36: LTO up to and including 3000 ft."""
        assert section_of_flight(0) == "LTO"
        assert section_of_flight(3000) == "LTO"
        assert section_of_flight(3000.001) == "NON_LTO"


class TestMEEMV1Interpolation:
    """MEEM_V1!B101/B102 non-LTO interpolation: linear between the two
    bracketing points, the 100 % value above 1, the 7 % value below 0.07."""

    _mass = _ENGINES["11GE144"][1]

    def test_linear_between_points(self):
        v = interpolate_ei(0.5, _TS, self._mass)
        x0, x1, y0, y1 = 0.30, 0.85, self._mass[2], self._mass[1]
        assert v == pytest.approx(y0 + (0.5 - x0) * (y1 - y0) / (x1 - x0), rel=1e-14)

    def test_caps(self):
        assert interpolate_ei(1.2, _TS, self._mass) == self._mass[0]
        assert interpolate_ei(0.01, _TS, self._mass) == self._mass[3]

    def test_at_points(self):
        for t, v in zip(_TS, self._mass):
            assert interpolate_ei(t, _TS, self._mass) == pytest.approx(v, rel=1e-14)


class TestMEEMV1EngineWiring:
    """Engine.getEmissionIndexByModeWithMEEM: LTO returns the mode EI
    unchanged; above 3000 ft the MEEM mass EI replaces pm10_nonvol and
    pm10, p1, p2 move by the same amount."""

    def _build_engine(self):
        from open_alaqs.core.interfaces.Engine import EngineEmissionIndex

        opr, mass, number = _ENGINES["11GE144"]
        eei = EngineEmissionIndex()
        for i, m in enumerate(("TO", "CL", "AP", "TX")):
            eei.setObject(
                m,
                {
                    "mode": m,
                    "thrust": _TS[i],
                    "fuel_kg_sec": 0.5,
                    "co_ei": 0.0,
                    "hc_ei": 0.0,
                    "nox_ei": 0.0,
                    "sox_ei": 0.0,
                    "pm10_nonvol": mass[i] / 1000.0,
                    "nvpm_number_ei": number[i],
                    "pm10_sul": 0.02,
                    "pm10_organic": 0.03,
                    "pm10_ei": mass[i] / 1000.0 + 0.05,
                    "p1_ei": mass[i] / 1000.0 + 0.05,
                    "p2_ei": mass[i] / 1000.0 + 0.05,
                },
            )
        eei._press_ratio = opr
        return eei

    def test_lto_returns_mode_ei(self):
        eei = self._build_engine()
        base = eei.getEmissionIndexByMode("CL")
        for alt in (None, 0.0, 914.4):
            ei = eei.getEmissionIndexByModeWithMEEM(
                "CL", 101325.0, 0.3, altitude_m=alt, tas_m_s=100.0, climbing=True
            )
            assert ei is base

    def test_non_lto_matches_sheet_and_moves_pm10(self):
        """11GE144 at 4500 ft, CLIMB TO CRUISE, TAS 220 kt: MEEM_V1!B119 of
        the recalculated sheet."""
        eei = self._build_engine()
        base = eei.getEmissionIndexByMode("CL")
        ft2m = 0.3048000097536
        ei = eei.getEmissionIndexByModeWithMEEM(
            "CL",
            101325.0,
            0.0,
            altitude_m=4500 * ft2m,
            tas_m_s=220 / 1.94384,
            climbing=True,
        )
        nonvol = ei.getObject("pm10_nonvol_g_kg")
        assert nonvol == pytest.approx(61.22075397785308 / 1000.0, rel=1e-12)
        assert ei.getObject("nvpm_g_kg") == nonvol
        assert ei.getObject("nvpm_number_kg") == pytest.approx(
            389448647438752.9, rel=1e-12
        )
        delta = nonvol - base.getObject("pm10_nonvol_g_kg")
        for key in ("pm10_g_kg", "p1_g_kg", "p2_g_kg"):
            assert ei.getObject(key) == pytest.approx(
                base.getObject(key) + delta, rel=1e-14
            )
        assert ei.getObject("pm10_g_kg") == pytest.approx(
            nonvol + ei.getObject("pm10_sul_g_kg") + ei.getObject("pm10_organic_g_kg"),
            rel=1e-12,
        )
        for key in ("fuel_kg_sec", "nox_g_kg", "co_g_kg", "hc_g_kg", "sox_g_kg"):
            assert ei.getObject(key) == base.getObject(key)

    def test_descent_phase_for_arrivals(self):
        """11GE144 at 5000 ft, DESCENT TO APPROACH, TAS 210 kt."""
        eei = self._build_engine()
        ei = eei.getEmissionIndexByModeWithMEEM(
            "AP",
            101325.0,
            0.0,
            altitude_m=5000 * 0.3048000097536,
            tas_m_s=210 / 1.94384,
            climbing=False,
        )
        assert ei.getObject("pm10_nonvol_g_kg") == pytest.approx(
            5.588363301978656 / 1000.0, rel=1e-12
        )

    def test_missing_pressure_ratio_uses_default(self):
        """No press_ratio in the table: OPR 30 (the sheet has no value)."""
        eei = self._build_engine()
        eei._press_ratio = None
        ei = eei.getEmissionIndexByModeWithMEEM(
            "CL", 101325.0, 0.0, altitude_m=2000.0, tas_m_s=120.0, climbing=True
        )
        opr, mass, number = _ENGINES["11GE144"]
        r = calculate_nvpm_ei(
            "CLIMB TO CRUISE",
            2000.0 / 0.3048000097536,
            _TS,
            mass,
            number,
            opr=30.0,
            tas_kt=120.0 * 1.94384,
        )
        assert ei.getObject("pm10_nonvol_g_kg") == pytest.approx(
            r.nvpm_mass_ei_mgkg / 1000.0, rel=1e-14
        )


class TestMEEMV1DeltaT:
    """ISA + delta T above 3000 ft: delta T is the meteo temperature minus
    ISA at the airport elevation (USER INPUTS!B5, constant aloft)."""

    def test_delta_t_from_ground(self):
        assert delta_t_from_ground(None, 120.0) == 0.0
        assert delta_t_from_ground(288.15, 0.0) == 0.0
        assert delta_t_from_ground(288.15 - 0.0065 * 500.0, 500.0) == pytest.approx(
            0.0, abs=1e-12
        )
        # training example: 283 K at -5 m
        assert delta_t_from_ground(283.0, -5.0) == pytest.approx(-5.1825, abs=1e-12)
        assert delta_t_from_ground(300.0, None) == pytest.approx(11.85, abs=1e-12)

    def test_ambient_temperature_at_elevation_is_the_meteo_value(self):
        from open_alaqs.core.tools.meem_v1 import FT_TO_M, isa_ambient

        elev_m, t_ground = 450.0, 279.4
        t_amb, _ = isa_ambient(elev_m / FT_TO_M, delta_t_from_ground(t_ground, elev_m))
        assert t_amb == pytest.approx(t_ground, abs=1e-9)

    def _engine(self):
        return TestMEEMV1EngineWiring()._build_engine()

    def test_engine_delta_t_zero_is_isa(self):
        kw = dict(altitude_m=4500 * 0.3048000097536, tas_m_s=220 / 1.94384)
        a = self._engine().getEmissionIndexByModeWithMEEM(
            "CL", 101325.0, 0.0, climbing=True, **kw
        )
        b = self._engine().getEmissionIndexByModeWithMEEM(
            "CL", 101325.0, 0.0, climbing=True, delta_t=0.0, **kw
        )
        assert a.getObject("pm10_nonvol_g_kg") == b.getObject("pm10_nonvol_g_kg")
        assert a.getObject("nvpm_number_kg") == b.getObject("nvpm_number_kg")
        assert a.getObject("pm10_nonvol_g_kg") == pytest.approx(
            61.22075397785308 / 1000.0, rel=1e-12
        )

    @pytest.mark.parametrize(
        "mode, alt_ft, tas_kt, climbing, delta_t, mass, number",
        [
            ("CL", 4500, 220, True, -5.1825, 60.52925750077077, 400236880720932.9),
            ("AP", 5000, 210, False, 12.0, 4.55684516335939, 229810399546587.56),
        ],
    )
    def test_engine_delta_t_matches_sheet(
        self, mode, alt_ft, tas_kt, climbing, delta_t, mass, number
    ):
        """11GE144, the sheet recalculated in LibreOffice with USER INPUTS!B5
        = delta T (cruise altitude 38000 ft)."""
        ei = self._engine().getEmissionIndexByModeWithMEEM(
            mode,
            101325.0,
            0.0,
            altitude_m=alt_ft * 0.3048000097536,
            tas_m_s=tas_kt / 1.94384,
            climbing=climbing,
            delta_t=delta_t,
        )
        assert ei.getObject("pm10_nonvol_g_kg") == pytest.approx(
            mass / 1000.0, rel=1e-12
        )
        assert ei.getObject("nvpm_number_kg") == pytest.approx(number, rel=1e-12)

    def test_calculator_delta_t_from_meteo(self):
        """FlightEmissionCalculator._meem_delta_t: the period's temperature
        (the one BFFM2 uses) and the airport altitude of the method config."""
        from types import SimpleNamespace

        from open_alaqs.core.MovementEmissionCalculator import (
            FlightEmissionCalculator,
        )

        calc = SimpleNamespace(_method={"config": {"airport_altitude": -5.0}})
        f = FlightEmissionCalculator._meem_delta_t
        assert f(calc, 283.0) == pytest.approx(-5.1825, abs=1e-12)
        assert f(calc, None) == 0.0
        calc._method["config"]["airport_altitude"] = None
        assert f(calc, 290.0) == pytest.approx(1.85, abs=1e-12)
