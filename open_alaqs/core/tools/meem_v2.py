"""
meem_v2.py — MEEM V2 nvPM emission index calculator
=====================================================
Implements the Main Engine Emission Model version 2 (MEEM V2) as specified
in ICAO CAEP/13-WG3 and validated against CAEP14 FBE Calculation Sheet v12
tab "MEEM_V2" for engine 10GE129.

MEEM V2 differs from MEEM V1 in the interpolation variable:

  V1 (ICAO CAEP/13-MDG):
    Interpolate on % max thrust (F/F00).  Anchor points are at 0.07, 0.30,
    0.85, 1.00.  At climb-out thrust (0.85 anchor) the method returns the
    anchor EI exactly regardless of ambient conditions.

  V2 (ICAO CAEP/13-WG3, the CAEP14 v12 preferred method):
    Interpolate on BFFM2-adjusted fuel flow (FFadj in kg/s).  Anchor
    FFadj values are engine-specific, derived from the EEDB reference
    fuel flows at each mode via BFFM2's θ/δ/Mach correction evaluated at
    ISA+Mach=0:
        FFadj = FF_ref × δ × exp(0.2·M²) / θ^3.8
    At ISA+Mach=0 this factor is unity, so FFadj_ISA0 = FF_ref.
    At real segment ambient conditions the target FFadj differs from the
    mode anchor FFadj, so V2 produces a different EI than V1 even at LTO.

Numerical difference between V1 and V2 at the CAEP14 reference case for
engine 10GE129 at climb-out 253 ft, Mach 0.228, OPR 25.6, LTO:
  V1:  43.80 mg/kg   (exact anchor)
  V2:  36.63 mg/kg   (linear interp between FFadj anchors 0.22542 and 0.65845)
  ratio V2/V1 = 0.836 — about 16% lower

Interpolation math per CAEP14 sheet:
  * Mass EI: linear-linear interpolation between adjacent FFadj anchors:
      EI(FFadj) = EI[i] + (FFadj - FF[i]) / (FF[i+1] - FF[i]) × (EI[i+1] - EI[i])
    Values below FF[0] are clamped to EI[0]; above FF[-1] clamped to EI[-1].

  * Number EI: same linear-linear interpolation on FFadj.

The altitude correction chain at sections 1-4 is IDENTICAL to V1 — both use
the same GR-equivalent thrust computation, just applied AFTER the EI has
been obtained via the FFadj-based interpolation.  The DLR enrichment factor
φ at section 7 is also identical between V1 and V2.

Usage:

    from open_alaqs.core.tools.meem_v2 import calculate_nvpm_ei_v2

    # V2 requires BFFM2-adjusted FF values for each EEDB mode. These are
    # typically constructed by calling calculate_ffadj_at_mode() for each
    # mode at ISA+Mach=0 (trivial: FFadj = FF_ref in that case).
    ffadj_anchors  = [0.0924, 0.22542, 0.65845, 0.79689]  # for 10GE129
    mass_mgkg      = [4.78, 2.83, 43.80, 66.37]
    number_nkg     = [241e12, 143e12, 276e12, 418e12]

    result = calculate_nvpm_ei_v2(
        ffadj_target_kgs=0.582649,   # BFFM2-adjusted FF at segment
        ffadj_anchors=ffadj_anchors,
        ei_mass_mgkg=mass_mgkg,
        ei_number_nkg=number_nkg,
        altitude_m=77.1144,
        mach=0.228,
        opr=25.6,
        phase="CLIMB OUT",
        apply_altitude_correction=False,
    )

References:
  ICAO CAEP/13-WG3, MEEM V2 specification.
  CAEP14 FBE Engines Emissions Calculation Sheet v12, "MEEM_V2" tab.
"""

import logging
import math
from dataclasses import dataclass
from typing import Optional

# Reuse ISA constants, phase η_comp, altitude correction, and the atmosphere
# helpers from V1 — they are spec-identical between versions.
from open_alaqs.core.tools.meem_v1 import (
    _N_MASS,
    _N_NUMBER,
    ISA,
    PHASE_ETA_COMP,
    _altitude_correction_factor,
    combustor_inlet_conditions,
    isa_conditions,
    total_conditions,
)

logger = logging.getLogger(__name__)

_EPSILON: float = 1e-9


# ── BFFM2 adjustment factor ──────────────────────────────────────────────────


def bffm2_adjustment_factor(
    theta: float,
    delta: float,
    mach: float,
) -> float:
    """
    BFFM2 fuel-flow adjustment factor used to convert between ambient FF
    and reference FF:
        FFadj = FF_amb × δ × exp(0.2·M²) / θ^3.8   [SAE AIR-5715 / CAEP14]

    Returns the multiplicative factor f such that FFadj = FF_amb × f.

    At ISA sea-level static conditions (θ=δ=1, M=0) this is exactly 1.0.
    """
    if theta <= 0 or delta <= 0:
        return 1.0
    return delta * math.exp(0.2 * mach * mach) / (theta**3.8)


def ffadj_anchors_at_isa(
    ff_ref_kgs: list[float],
) -> list[float]:
    """
    At ISA sea-level Mach=0, the BFFM2 adjustment factor is unity, so the
    FFadj anchor values equal the reference FF values.  Wrap this trivial
    identity in a named helper to make V2 call sites self-documenting.
    """
    return [float(ff) for ff in ff_ref_kgs]


# ── FFadj-based interpolation ─────────────────────────────────────────────────


def _sort_points(xs: list[float], ys: list[float]) -> tuple[list[float], list[float]]:
    pairs = sorted(zip(xs, ys), key=lambda p: p[0])
    return [p[0] for p in pairs], [p[1] for p in pairs]


def interpolate_on_ffadj_linear(
    ffadj_target: float,
    ffadj_anchors: list[float],
    ei_values: list[float],
) -> float:
    """
    Linear-linear piecewise interpolation on FFadj, matching the CAEP14 v12
    MEEM_V2 sheet behaviour.

    Clamping rules: values below the first anchor return the first EI;
    values above the last anchor return the last EI. No extrapolation.

    :param ffadj_target:   BFFM2-adjusted fuel flow at the segment (kg/s).
    :param ffadj_anchors:  List of FFadj anchor values (kg/s) at each EEDB
                           mode, typically 4 or 5 points.
    :param ei_values:      EI values (mg/kg or #/kg) at each anchor.
    :return:               Interpolated EI at ffadj_target.
    """
    xs, ys = _sort_points(ffadj_anchors, ei_values)
    if not any(y for y in ys):
        return 0.0
    if ffadj_target <= xs[0]:
        return float(ys[0])
    if ffadj_target >= xs[-1]:
        return float(ys[-1])
    for i in range(len(xs) - 1):
        if xs[i] <= ffadj_target <= xs[i + 1]:
            if xs[i + 1] == xs[i]:
                return float(ys[i])
            frac = (ffadj_target - xs[i]) / (xs[i + 1] - xs[i])
            return float(ys[i] + frac * (ys[i + 1] - ys[i]))
    return float(ys[-1])


# ── Result ────────────────────────────────────────────────────────────────────


@dataclass
class MEEMv2Result:
    """nvPM emission indices returned by MEEM V2."""

    nvpm_mass_ei_mgkg: float  # mg/kg fuel
    nvpm_number_ei_nkg: float  # #/kg fuel
    ffadj_target_kgs: float  # BFFM2-adjusted FF used for interpolation
    T3_alt: float  # combustor inlet T at altitude (K) — NaN for LTO
    T3_gr: float  # combustor inlet T at GR (K)
    phi: float  # enrichment factor applied (1.0 for LTO)


# ── Main entry point ──────────────────────────────────────────────────────────


def calculate_nvpm_ei_v2(
    ffadj_target_kgs: float,
    ffadj_anchors: list[float],
    ei_mass_mgkg: list[float],
    ei_number_nkg: list[float],
    altitude_m: float = 0.0,
    mach: float = 0.0,
    opr: float = 30.0,
    phase: str = "CLIMB OUT",
    apply_altitude_correction: bool = False,
    T_ambient_K: Optional[float] = None,
    P_ambient_Pa: Optional[float] = None,
) -> MEEMv2Result:
    """
    MEEM V2 nvPM mass and number EI at the given segment conditions.

    V2 interpolates on BFFM2-adjusted fuel flow (ffadj_target_kgs) rather than
    % max thrust. For LTO segments (altitude ≤ 914 m) the altitude correction
    chain is skipped. For non-LTO segments with apply_altitude_correction=True,
    the same altitude chain as V1 is applied (reusing meem_v1's helpers).

    :param ffadj_target_kgs:          BFFM2-adjusted fuel flow at the segment (kg/s).
    :param ffadj_anchors:             List of FFadj anchor values at each EEDB
                                       mode. Typically derived via
                                       ffadj_anchors_at_isa(ff_ref_kgs).
    :param ei_mass_mgkg:              EEDB nvPM mass EI at each anchor (mg/kg).
    :param ei_number_nkg:             EEDB nvPM number EI at each anchor (#/kg).
    :param altitude_m:                Segment altitude (m). Gates LTO vs non-LTO.
    :param mach:                      Mach number (dimensionless, ≥ 0).
    :param opr:                       Engine OPR (π00), dimensionless.
    :param phase:                     CAEP14 phase name (see PHASE_ETA_COMP).
    :param apply_altitude_correction: If True and altitude > 914 m, apply the
                                       P3/T3 altitude chain after the FFadj
                                       interpolation.
    :param T_ambient_K:               Optional ambient T (K); overrides ISA.
    :param P_ambient_Pa:              Optional ambient P (Pa); overrides ISA.
    :return:                          MEEMv2Result.
    """
    # Step 1: interpolate mass and number EI on FFadj
    ei_mass_gr = interpolate_on_ffadj_linear(
        ffadj_target_kgs, ffadj_anchors, ei_mass_mgkg
    )
    ei_number_gr = interpolate_on_ffadj_linear(
        ffadj_target_kgs, ffadj_anchors, ei_number_nkg
    )

    # Step 2: for LTO, return as-is (no altitude correction required)
    is_lto = (altitude_m is None) or (float(altitude_m) <= 914.0)
    if is_lto or not apply_altitude_correction:
        return MEEMv2Result(
            nvpm_mass_ei_mgkg=ei_mass_gr,
            nvpm_number_ei_nkg=ei_number_gr,
            ffadj_target_kgs=float(ffadj_target_kgs),
            T3_alt=float("nan"),
            T3_gr=ISA.T0,
            phi=1.0,
        )

    # Step 3: non-LTO altitude correction (same chain as V1, reuses helpers)
    eta_comp = PHASE_ETA_COMP.get(phase, 0.88)

    if T_ambient_K is not None and P_ambient_Pa is not None:
        T_amb = float(T_ambient_K)
        P_amb = float(P_ambient_Pa)
    else:
        T_amb, P_amb = isa_conditions(float(altitude_m))

    TT_alt, PT_alt = total_conditions(T_amb, P_amb, float(mach))
    P3_alt, T3_alt = combustor_inlet_conditions(TT_alt, PT_alt, float(opr), eta_comp)

    # Ground reference: ISA MSL
    PT_gr, TT_gr = ISA.P0, ISA.T0
    _, T3_gr = combustor_inlet_conditions(TT_gr, PT_gr, float(opr), eta_comp)

    phi_mass = _altitude_correction_factor(T3_alt, T3_gr, exponent=_N_MASS)
    phi_num = _altitude_correction_factor(T3_alt, T3_gr, exponent=_N_NUMBER)

    return MEEMv2Result(
        nvpm_mass_ei_mgkg=ei_mass_gr * phi_mass,
        nvpm_number_ei_nkg=ei_number_gr * phi_num,
        ffadj_target_kgs=float(ffadj_target_kgs),
        T3_alt=T3_alt,
        T3_gr=T3_gr,
        phi=phi_mass,
    )


# ── Convenience: compute FFadj for a segment from ambient conditions ─────────


def compute_ffadj_for_segment(
    ff_ref_kgs: float,
    altitude_m: float = 0.0,
    mach: float = 0.0,
    T_ambient_K: Optional[float] = None,
    P_ambient_Pa: Optional[float] = None,
) -> float:
    """
    Helper: given the reference FF at a mode, compute the BFFM2-adjusted FF
    at the segment ambient conditions.  The formula is:
        FFadj = FF_ref × f(θ, δ, M)
    where the adjustment factor f is 1 at ISA+Mach=0.

    Used by callers that want to turn a mode's reference FF into the FFadj
    target that should be passed to calculate_nvpm_ei_v2.
    """
    if T_ambient_K is None or P_ambient_Pa is None:
        T, P = isa_conditions(float(altitude_m))
    else:
        T, P = float(T_ambient_K), float(P_ambient_Pa)
    theta = T / ISA.T0
    delta = P / ISA.P0
    factor = bffm2_adjustment_factor(theta, delta, float(mach))
    return float(ff_ref_kgs) * factor
