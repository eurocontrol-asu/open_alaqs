"""
MEEM V1 (ICAO CAEP/13-MDG) regression tests.

Reference values are derived from running the MEEM V1 algorithm as specified
in ICAO Doc 9889 Appendix 1 against the public ICAO Aircraft Engine Emissions
Databank (EEDB) entry for engine 10GE129. The EEDB nvPM anchors used are
publicly available from https://www.easa.europa.eu/en/domains/environment/icao-aircraft-engine-emissions-databank.

Segment conditions for the reference case:
  - segment altitude 253 ft (LTO — below 914 m cutoff)
  - phase CLIMB OUT
  - Mach 0.228
  - OPR 25.6
  - ISA ambient at segment altitude

Expected MEEM V1 outputs (independently computed from the spec):
  - Ei nvPM mass at GR, fossil = 43.7984 mg/kgFuel
  - Ei nvPM num  at GR, fossil = 2.76104e14 #/kgFuel
  - Enrichment factor φ = 1.0 for LTO (non-LTO uses DLR-fit φ)

EEDB anchor points for 10GE129 (public ICAO EEDB):
  % thrust  mass_mgkg         num_nkg
  0.07       4.78086296545785  2.41108044904334e14
  0.30       2.82581295191441  1.42511140985230e14
  0.85      43.7983713451728   2.76104433481114e14
  1.00      66.3695054537971   4.18392605499520e14

At climb-out (0.85 thrust anchor) the LTO interpolation must return the
anchor value — V1 uses % thrust as the interpolation variable, so hitting an
anchor returns the anchor EI exactly. This validates:
  (a) anchor array is in the right order / format,
  (b) LTO path applies no altitude correction (GR-equivalent thrust = actual),
  (c) non-LTO path activates the altitude chain and produces different output.

Behavioural sanity checks cover off-anchor power settings, non-LTO, and the
sub-anchor edge case.
"""

import pytest

from open_alaqs.core.tools.meem_v1 import calculate_nvpm_ei

# Public EEDB anchors for engine 10GE129
_EEDB_THRUSTS = [0.07, 0.30, 0.85, 1.00]
_EEDB_MASS = [4.78086296545785, 2.82581295191441, 43.7983713451728, 66.3695054537971]
_EEDB_NUM = [
    2.41108044904334e14,
    1.42511140985230e14,
    2.76104433481114e14,
    4.18392605499520e14,
]
_EEDB_OPR = 25.6


class TestMEEMV1Anchors:
    """At anchor points the V1 interpolation must return the anchor EI exactly."""

    @pytest.mark.parametrize(
        "thrust_anchor, mass_ref, num_ref",
        list(zip(_EEDB_THRUSTS, _EEDB_MASS, _EEDB_NUM)),
    )
    def test_anchor_reproduction_lto(self, thrust_anchor, mass_ref, num_ref):
        """LTO interpolation at an anchor returns the anchor EI exactly."""
        r = calculate_nvpm_ei(
            power_setting=thrust_anchor,
            thrust_settings=_EEDB_THRUSTS,
            ei_mass_mgkg=_EEDB_MASS,
            ei_number_nkg=_EEDB_NUM,
            altitude_m=77.1144,  # 253 ft = LTO
            mach=0.22834519,
            opr=_EEDB_OPR,
            phase="CLIMB OUT",
            apply_altitude_correction=False,
        )
        assert r.nvpm_mass_ei_mgkg == pytest.approx(mass_ref, rel=1e-9)
        assert r.nvpm_number_ei_nkg == pytest.approx(num_ref, rel=1e-9)


class TestMEEMV1SpecReference:
    """Full MEEM V1 reference case for engine 10GE129 (public EEDB) at climb-out 253 ft."""

    def test_climbout_lto_matches_spec(self):
        """Ei nvPM mass GR,Fossil = 43.7984 mg/kgFuel at
        climbout (0.85 thrust anchor), Mach 0.228, OPR 25.6, LTO segment.
        At an anchor the LTO path returns the anchor EI unchanged."""
        r = calculate_nvpm_ei(
            power_setting=0.85,
            thrust_settings=_EEDB_THRUSTS,
            ei_mass_mgkg=_EEDB_MASS,
            ei_number_nkg=_EEDB_NUM,
            altitude_m=77.1144,
            mach=0.22834519,
            opr=_EEDB_OPR,
            phase="CLIMB OUT",
            apply_altitude_correction=False,
        )
        # Reference: 43.7983713451728 mg/kg — tolerate 1e-6 relative
        assert r.nvpm_mass_ei_mgkg == pytest.approx(43.7983713451728, rel=1e-6)
        assert r.nvpm_number_ei_nkg == pytest.approx(2.76104433481114e14, rel=1e-6)


class TestMEEMV1BehaviouralSanity:
    """
    Non-reference sanity checks for off-anchor and non-LTO cases.  Strict
    numerical reference values depend on the CAEP13/MDG compressor-efficiency
    correlations which aren't published, so these tests only check the
    qualitative behaviour:
      - between anchors, the interpolated EI lies between the neighbour values
      - non-LTO altitude-corrected EI differs from LTO EI at the same power
      - invalid inputs fall through cleanly without raising
    """

    def test_offanchor_mass_between_neighbours(self):
        """Interpolation at 0.58 thrust: log-log on mass between 0.30 and 0.85
        anchors.  Result must lie in [mass(0.30), mass(0.85)] bracket."""
        r = calculate_nvpm_ei(
            power_setting=0.58,
            thrust_settings=_EEDB_THRUSTS,
            ei_mass_mgkg=_EEDB_MASS,
            ei_number_nkg=_EEDB_NUM,
            altitude_m=77.1144,
            mach=0.0,
            opr=_EEDB_OPR,
            phase="CLIMB OUT",
            apply_altitude_correction=False,
        )
        # Mass curve is NOT monotonic (2.83 at 0.30, 43.80 at 0.85) but values
        # at 0.58 must sit within the span of surrounding anchors.
        assert (
            min(2.82581295, 43.7983713)
            <= r.nvpm_mass_ei_mgkg
            <= max(2.82581295, 43.7983713)
        )

    def test_nonlto_differs_from_lto(self):
        """At the same power setting but non-LTO altitude, the altitude
        correction chain (φ enrichment etc.) must yield a different mass EI
        from the LTO case."""
        kw = dict(
            power_setting=0.85,
            thrust_settings=_EEDB_THRUSTS,
            ei_mass_mgkg=_EEDB_MASS,
            ei_number_nkg=_EEDB_NUM,
            mach=0.4,
            opr=_EEDB_OPR,
            phase="CLIMB OUT",
        )
        lto = calculate_nvpm_ei(
            altitude_m=77.1144, apply_altitude_correction=False, **kw
        )
        nonlto = calculate_nvpm_ei(
            altitude_m=3048.0, apply_altitude_correction=True, **kw
        )
        # Non-LTO output must differ from LTO anchor value.
        assert lto.nvpm_mass_ei_mgkg != pytest.approx(
            nonlto.nvpm_mass_ei_mgkg, rel=1e-6
        )

    def test_power_setting_zero_does_not_raise(self):
        """Idle-below-taxi edge case: power setting below the lowest anchor
        must not raise; interpolation should clamp or extrapolate safely."""
        try:
            calculate_nvpm_ei(
                power_setting=0.01,
                thrust_settings=_EEDB_THRUSTS,
                ei_mass_mgkg=_EEDB_MASS,
                ei_number_nkg=_EEDB_NUM,
                altitude_m=0.0,
                mach=0.0,
                opr=_EEDB_OPR,
                phase="IDLE",
                apply_altitude_correction=False,
            )
        except Exception as exc:
            pytest.fail(f"MEEM V1 raised on sub-anchor power setting: {exc!r}")


class TestMEEMV1Wiring:
    """End-to-end: Engine.getEmissionIndexByModeWithMEEM must honour the
    new power_setting / altitude_m / T_amb_K kwargs and return EI that
    DIFFERS from bymode when the segment conditions warrant it."""

    def _build_engine(self):
        """Construct a minimal EngineEmissionIndex with the public-EEDB 10GE129
        nvPM anchors at the 4 standard modes."""
        from open_alaqs.core.interfaces.Engine import EngineEmissionIndex

        eei = EngineEmissionIndex()
        modes = [("TO", 1.00), ("CL", 0.85), ("AP", 0.30), ("TX", 0.07)]
        for i, (m, p) in enumerate(modes):
            eei.setObject(
                m,
                {
                    "mode": m,
                    "thrust": p,
                    "fuel_kg_sec": 0.5,
                    "co_ei": 0.0,
                    "hc_ei": 0.0,
                    "nox_ei": 0.0,
                    "sox_ei": 0.0,
                    "pm10_nonvol": _EEDB_MASS[3 - i] / 1000.0,  # g/kg
                    "nvpm_number_ei": _EEDB_NUM[3 - i],
                    "pm10_sul": 0.0,
                    "pm10_organic": 0.0,
                    "pm10_ei": _EEDB_MASS[3 - i] / 1000.0,
                    "p1_ei": 0.0,
                    "p2_ei": 0.0,
                },
            )
        eei._press_ratio = _EEDB_OPR
        return eei

    def test_power_setting_kwarg_shifts_result(self):
        """Calling with power_setting != mode's anchor must shift the EI.
        Without power_setting the call returns the mode's anchor EI."""
        eei = self._build_engine()
        # Anchor-only call: returns CL anchor
        default = eei.getEmissionIndexByModeWithMEEM("CL", 101325.0, 0.0)
        # Off-anchor call: power_setting 0.674 (real profile value)
        off = eei.getEmissionIndexByModeWithMEEM(
            "CL",
            101325.0,
            0.0,
            power_setting=0.674,
            altitude_m=0.0,
        )
        # Mass EI must differ (default is at anchor 0.85; off-anchor is between 0.30 and 0.85).
        assert default.getObject("nvpm_g_kg") != pytest.approx(
            off.getObject("nvpm_g_kg"), rel=1e-9
        )

    def test_altitude_kwarg_shifts_result_at_non_lto(self):
        """Same power setting, LTO vs non-LTO altitude: altitude correction
        chain must shift the result."""
        eei = self._build_engine()
        lto = eei.getEmissionIndexByModeWithMEEM(
            "CL",
            101325.0,
            0.4,
            power_setting=0.85,
            altitude_m=100.0,
        )
        nonlto = eei.getEmissionIndexByModeWithMEEM(
            "CL",
            70000.0,
            0.4,
            power_setting=0.85,
            altitude_m=3048.0,
        )
        assert lto.getObject("nvpm_g_kg") != pytest.approx(
            nonlto.getObject("nvpm_g_kg"), rel=1e-6
        )
