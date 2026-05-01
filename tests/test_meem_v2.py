"""
MEEM V2 (ICAO CAEP/13-WG3) regression tests.

Reference values are independently derived numerical outputs for engine
10GE129. The EEDB anchors used (reference fuel flow, nvPM mass, nvPM number)
are publicly available from the ICAO Aircraft Engine Emissions Databank.

V2 specifies linear-linear interpolation on BFFM2-adjusted fuel flow
(FFadj in kg/s).  At the CAEP14 reference segment (climb-out 253 ft,
Mach 0.228, OPR 25.6), the segment's reference FF is 0.58265 kg/s (between
the approach anchor FF=0.22542 and climb-out anchor FF=0.65845).  Linear
interpolation gives:

    EI(0.58265) = EI(0.22542) + (0.58265 - 0.22542) / (0.65845 - 0.22542) *
                  (EI(0.65845) - EI(0.22542))
                = 2.82581 + 0.82494 * (43.79837 - 2.82581)
                = 36.62624 mg/kg

That 36.626 mg/kg is the expected V2 mass EI; V1 gives 43.798 mg/kg at the
same conditions (exact climb-out thrust anchor).  The ~16% gap between V1
and V2 at LTO is the core reason V2 exists as a separate mode.
"""

import pytest

from open_alaqs.core.tools.meem_v2 import (
    bffm2_adjustment_factor,
    calculate_nvpm_ei_v2,
    compute_ffadj_for_segment,
    ffadj_anchors_at_isa,
    interpolate_on_ffadj_linear,
)

# EEDB anchors for engine 10GE129 — publicly available ICAO EEDB values
_FF_REF_KGS = [0.0924, 0.22542, 0.65845, 0.79689]  # kg/s
_EI_MASS_MGKG = [4.78086296545785, 2.82581295191441, 43.7983713451728, 66.3695054537971]
_EI_NUMBER_NKG = [
    2.41108044904334e14,
    1.42511140985230e14,
    2.76104433481114e14,
    4.18392605499520e14,
]
_OPR = 25.6


class TestMEEMV2Interpolation:
    """FFadj-based linear interpolation primitives."""

    def test_ffadj_anchors_at_isa_identity(self):
        """At ISA+Mach=0 the FFadj factor is unity, so FFadj anchors equal
        the reference FF values."""
        anchors = ffadj_anchors_at_isa(_FF_REF_KGS)
        assert anchors == _FF_REF_KGS

    def test_bffm2_factor_unity_at_isa_mach_zero(self):
        """θ=δ=1, M=0 → factor = 1.0."""
        assert bffm2_adjustment_factor(theta=1.0, delta=1.0, mach=0.0) == pytest.approx(
            1.0
        )

    def test_bffm2_factor_increases_with_colder_air(self):
        """Colder air (θ<1) → larger adjustment factor (FFadj > FF_amb)
        at constant δ, M."""
        f_cold = bffm2_adjustment_factor(theta=0.95, delta=1.0, mach=0.2)
        f_isa = bffm2_adjustment_factor(theta=1.00, delta=1.0, mach=0.2)
        assert f_cold > f_isa

    def test_interpolate_clamps_below_min(self):
        """Target below lowest anchor → first EI (no extrapolation)."""
        v = interpolate_on_ffadj_linear(0.01, _FF_REF_KGS, _EI_MASS_MGKG)
        assert v == pytest.approx(_EI_MASS_MGKG[0])

    def test_interpolate_clamps_above_max(self):
        """Target above highest anchor → last EI."""
        v = interpolate_on_ffadj_linear(10.0, _FF_REF_KGS, _EI_MASS_MGKG)
        assert v == pytest.approx(_EI_MASS_MGKG[-1])

    def test_interpolate_at_anchor_returns_anchor(self):
        """Target at an anchor returns that anchor's EI exactly."""
        for ff, ei in zip(_FF_REF_KGS, _EI_MASS_MGKG):
            v = interpolate_on_ffadj_linear(ff, _FF_REF_KGS, _EI_MASS_MGKG)
            assert v == pytest.approx(ei, rel=1e-12)


class TestMEEMV2Reference:
    """Reference case for engine 10GE129 at climb-out 253 ft."""

    def test_climbout_lto_matches_reference(self):
        """MEEM V2 reference output at FFadj=0.58265 kg/s:
        linear interpolation between (0.22542, 2.826) and (0.65845, 43.798)
        gives 36.626 mg/kg."""
        result = calculate_nvpm_ei_v2(
            ffadj_target_kgs=0.582649335838304,
            ffadj_anchors=_FF_REF_KGS,
            ei_mass_mgkg=_EI_MASS_MGKG,
            ei_number_nkg=_EI_NUMBER_NKG,
            altitude_m=77.1144,
            mach=0.22834519,
            opr=_OPR,
            phase="CLIMB OUT",
            apply_altitude_correction=False,
        )
        assert result.nvpm_mass_ei_mgkg == pytest.approx(36.62624207326819, rel=1e-6)

    def test_v2_differs_from_v1_at_reference(self):
        """V2 vs V1 at the CAEP14 reference case: V1 returns 43.80 (anchor
        exact), V2 returns 36.63. Their ratio is ~0.836, a 16% gap.
        If this test ever flips (V1=V2 numerically), the V1 and V2 code
        paths have been incorrectly merged."""
        from open_alaqs.core.tools.meem_v1 import calculate_nvpm_ei

        v1 = calculate_nvpm_ei(
            power_setting=0.85,
            thrust_settings=[0.07, 0.30, 0.85, 1.00],
            ei_mass_mgkg=_EI_MASS_MGKG,
            ei_number_nkg=_EI_NUMBER_NKG,
            altitude_m=77.1144,
            mach=0.22834519,
            opr=_OPR,
            phase="CLIMB OUT",
            apply_altitude_correction=False,
        )
        v2 = calculate_nvpm_ei_v2(
            ffadj_target_kgs=0.582649335838304,
            ffadj_anchors=_FF_REF_KGS,
            ei_mass_mgkg=_EI_MASS_MGKG,
            ei_number_nkg=_EI_NUMBER_NKG,
            altitude_m=77.1144,
            mach=0.22834519,
            opr=_OPR,
            phase="CLIMB OUT",
            apply_altitude_correction=False,
        )
        assert v1.nvpm_mass_ei_mgkg == pytest.approx(43.7983713451728, rel=1e-6)
        assert v2.nvpm_mass_ei_mgkg == pytest.approx(36.62624207326819, rel=1e-6)
        # Distinctness check — must differ by >10%
        assert (
            abs(v1.nvpm_mass_ei_mgkg - v2.nvpm_mass_ei_mgkg) / v1.nvpm_mass_ei_mgkg
            > 0.10
        )


class TestMEEMV2SegmentHelper:
    """compute_ffadj_for_segment builds the interpolation target from a
    mode's reference FF and ambient conditions."""

    def test_isa_mach_zero_returns_ff_ref(self):
        """At ISA + Mach=0, FFadj = FF_ref."""
        v = compute_ffadj_for_segment(
            ff_ref_kgs=0.65845,
            altitude_m=0.0,
            mach=0.0,
        )
        assert v == pytest.approx(0.65845, rel=1e-6)

    def test_mach_nonzero_shifts_ffadj_up(self):
        """At M > 0 and same static conditions, exp(0.2·M²) > 1 → FFadj
        shifts up from FF_ref."""
        v = compute_ffadj_for_segment(
            ff_ref_kgs=0.65845,
            altitude_m=0.0,
            mach=0.4,
            T_ambient_K=288.15,
            P_ambient_Pa=101325.0,
        )
        assert v > 0.65845
        # The exact shift is exp(0.2 * 0.16) = exp(0.032) = 1.0325
        assert v == pytest.approx(0.65845 * 1.03252, rel=1e-4)


class TestMEEMV2EngineWiring:
    """End-to-end: Engine.getEmissionIndexByModeWithMEEM routes to V2
    when meem_version='v2'."""

    def _build_engine(self):
        from open_alaqs.core.interfaces.Engine import EngineEmissionIndex

        eei = EngineEmissionIndex()
        modes = [
            ("TO", 1.00, 0.79689),
            ("CL", 0.85, 0.65845),
            ("AP", 0.30, 0.22542),
            ("TX", 0.07, 0.0924),
        ]
        for i, (m, p, ff) in enumerate(modes):
            eei.setObject(
                m,
                {
                    "mode": m,
                    "thrust": p,
                    "fuel_kg_sec": ff,
                    "co_ei": 0.0,
                    "hc_ei": 0.0,
                    "nox_ei": 0.0,
                    "sox_ei": 0.0,
                    "pm10_nonvol": _EI_MASS_MGKG[3 - i] / 1000.0,
                    "nvpm_number_ei": _EI_NUMBER_NKG[3 - i],
                    "pm10_sul": 0.0,
                    "pm10_organic": 0.0,
                    "pm10_ei": _EI_MASS_MGKG[3 - i] / 1000.0,
                    "p1_ei": 0.0,
                    "p2_ei": 0.0,
                },
            )
        eei._press_ratio = _OPR
        return eei

    def test_engine_v2_differs_from_v1_at_lto(self):
        """Request CL mode at 0.85 power (anchor), Mach 0.228, ISA LTO:
        V1 returns the anchor EI (43.80); V2 returns the FFadj-interpolated
        value (around 37-40 depending on BFFM2 factor with M=0.228)."""
        eei = self._build_engine()
        v1 = eei.getEmissionIndexByModeWithMEEM(
            "CL",
            101325.0,
            0.22834519,
            power_setting=0.85,
            altitude_m=77.1144,
            meem_version="v1",
        )
        v2 = eei.getEmissionIndexByModeWithMEEM(
            "CL",
            101325.0,
            0.22834519,
            power_setting=0.85,
            altitude_m=77.1144,
            meem_version="v2",
        )
        v1_mass = v1.getObject("nvpm_g_kg") * 1000.0  # g/kg → mg/kg
        v2_mass = v2.getObject("nvpm_g_kg") * 1000.0
        # V1 returns the CL anchor
        assert v1_mass == pytest.approx(43.798, rel=1e-3)
        # V2 shifts due to BFFM2-adjusted FF at M=0.228 ≠ CL anchor FF.
        # The ratio shift: factor = exp(0.2 × 0.228²) × 1 / 1 ≈ 1.0104
        # → FFadj = 0.65845 × 1.0104 ≈ 0.66532 — past CL anchor
        # So V2 will interpolate between CL (43.80) and TO (66.37)
        # slightly beyond CL. Expect: V2 > V1 due to bffm2 factor pushing
        # past CL anchor at M=0.228 ISA conditions.
        assert v2_mass > v1_mass, (
            f"At M=0.228 ISA, FFadj > FF_ref → V2 should interpolate past "
            f"CL anchor. Got v1={v1_mass}, v2={v2_mass}"
        )

    def test_engine_default_is_v1(self):
        """Omitting meem_version must default to V1 behaviour."""
        eei = self._build_engine()
        default = eei.getEmissionIndexByModeWithMEEM(
            "CL",
            101325.0,
            0.22834519,
            power_setting=0.85,
            altitude_m=77.1144,
        )
        v1 = eei.getEmissionIndexByModeWithMEEM(
            "CL",
            101325.0,
            0.22834519,
            power_setting=0.85,
            altitude_m=77.1144,
            meem_version="v1",
        )
        assert default.getObject("nvpm_g_kg") == pytest.approx(
            v1.getObject("nvpm_g_kg"), rel=1e-12
        )
