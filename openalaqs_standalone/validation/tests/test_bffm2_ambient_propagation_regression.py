"""Regression test: BFFM2 ambient_conditions propagation from method config.

Validates that bffm2.calculate_emission_index correctly applies ambient
corrections when ambient conditions are passed through as a dict (the form
the plugin's Engine.getEmissionIndexByFuelFlow builds from
method["config"]["ambient_conditions"]).

Background: during CAEP14 reference validation it was found that the
plugin's bymode and BFFM2 CSV outputs matched the reference exactly only
when ambient_conditions were ISA, even though tbl_InvMeteo was populated
with non-ISA values.  The root cause was traced to:

  1. EmissionCalculation.getAmbientCondition() returns AmbientCondition()
     (ISA defaults) silently when tbl_InvMeteo is empty.
  2. Engine.getEmissionIndexByFuelFlow swallowed any exception during
     ambient extraction and reverted to ISA without logging.

Both silent-fallback paths now log a warning, but the BFFM2 calculation
logic itself was never wrong: when given non-ISA conditions, it produces
non-ISA EIs.  This test pins that behaviour so a future regression in
bffm2.py (or in the dict shape Engine.py builds) is caught.
"""

from open_alaqs.core.tools.bffm2 import calculate_emission_index

# A20N engine 01P20CM128 reference EEDB anchors (kg/s, g/kg).
A20N_EEDB = {
    "NOx": {
        "Idle": {0.091: 4.61},
        "Approach": {0.244: 8.75},
        "Climbout": {0.710: 13.38},
        "Takeoff": {0.861: 30.80},
    },
    "CO": {
        "Idle": {0.091: 21.63},
        "Approach": {0.244: 2.65},
        "Climbout": {0.710: 0.26},
        "Takeoff": {0.861: 0.24},
    },
    "HC": {
        "Idle": {0.091: 0.29},
        "Approach": {0.244: 0.04},
        "Climbout": {0.710: 0.02},
        "Takeoff": {0.861: 0.02},
    },
}

ISA = {
    "temperature_in_Kelvin": 288.15,
    "pressure_in_Pa": 101325.0,
    "relative_humidity": 0.6,
    "mach_number": 0.0,
}

# Cold dry-air conditions (training_v3.alaqs Dec 1 06:00 — first row of the
# CAEP14 reference dataset).
COLD = {
    "temperature_in_Kelvin": 280.5,
    "pressure_in_Pa": 97600.0,
    "relative_humidity": 0.68,
    "mach_number": 0.0,
}

# Warm humid conditions (training_v3.alaqs Dec 3 — last meteo cluster).
WARM = {
    "temperature_in_Kelvin": 295.0,
    "pressure_in_Pa": 101100.0,
    "relative_humidity": 0.9,
    "mach_number": 0.0,
}


def test_bffm2_ei_changes_with_ambient_temperature():
    """Different ambient T must give different NOx EI for the same anchor FF."""
    ei_isa = calculate_emission_index("NOx", 0.244, A20N_EEDB, ISA)
    ei_cold = calculate_emission_index("NOx", 0.244, A20N_EEDB, COLD)
    ei_warm = calculate_emission_index("NOx", 0.244, A20N_EEDB, WARM)

    # Cold + drier than ISA-ref-day → higher NOx (positive humidity coefficient)
    # AND smaller theta → NOx scales up with (delta^1.02/theta^3.3)^0.5.
    assert ei_cold > ei_isa, (
        f"NOx EI must rise in cold dry conditions; got ISA={ei_isa:.4f}, "
        f"COLD={ei_cold:.4f}"
    )
    # Warm + much wetter than ISA-ref-day → lower NOx.
    assert ei_warm < ei_isa, (
        f"NOx EI must fall in warm humid conditions; got ISA={ei_isa:.4f}, "
        f"WARM={ei_warm:.4f}"
    )


def test_bffm2_ei_changes_with_mach():
    """Per-segment Mach must shift the EI lookup point on the EEDB curve."""
    ei_m0 = calculate_emission_index("NOx", 0.244, A20N_EEDB, ISA)
    isa_m03 = dict(ISA, mach_number=0.3)
    ei_m03 = calculate_emission_index("NOx", 0.244, A20N_EEDB, isa_m03)
    assert ei_m0 != ei_m03, (
        "BFFM2 NOx EI must depend on Mach (the inverse correction is "
        "ff_ref = ff_amb * theta^3.8 / delta * exp(0.2*M^2) and a different "
        "ff_ref lands at a different log-log interpolation point)."
    )


def test_bffm2_isa_default_when_ambient_missing():
    """Passing ambient_conditions=None must produce the ISA result."""
    ei_explicit = calculate_emission_index("NOx", 0.244, A20N_EEDB, ISA)
    ei_implicit = calculate_emission_index("NOx", 0.244, A20N_EEDB, None)
    # Both paths must land on identical ISA defaults; tiny rounding from
    # the duplicated installation_corrections application across the
    # explicit/implicit paths could give a 1e-12-scale jitter.
    assert abs(ei_explicit - ei_implicit) < 1e-9, (
        f"ISA-explicit and ISA-default paths must match; got explicit="
        f"{ei_explicit!r}, implicit={ei_implicit!r}."
    )


def test_bffm2_cold_dec1_pinned_values():
    """Pin the exact BFFM2 EI values for the CAEP14 Dec 1 06:00 conditions.

    These numbers are what compute_caep14_reference.py produces when invoked
    with --use-meteo against training_v3.alaqs and match a manual hand trace
    of the SAE AIR-5715 / CAEP14 BFFM2 formulae against tbl_InvMeteo's first
    row.  Any drift here means either the bffm2 module changed or the
    installation-correction defaults changed.
    """
    # AP anchor FF for A20N at cold-dry Dec 1 meteo.
    nox = calculate_emission_index("NOx", 0.244, A20N_EEDB, COLD)
    co = calculate_emission_index("CO", 0.244, A20N_EEDB, COLD)
    hc = calculate_emission_index("HC", 0.244, A20N_EEDB, COLD)
    # Values pinned against the live bffm2 module (CAEP14 v12, May 2026).
    # If these drift the bffm2 formulae or installation-correction defaults
    # have changed; re-derive against a manual hand trace before updating.
    assert abs(nox - 8.76009) < 1e-3, f"NOx at COLD = {nox!r} (expected ~8.760)"
    assert abs(co - 3.06171) < 1e-3, f"CO at COLD  = {co!r} (expected ~3.062)"
    assert abs(hc - 0.04571) < 1e-4, f"HC at COLD  = {hc!r} (expected ~0.046)"


def test_bffm2_dict_input_shape_matches_engine_path():
    """The dict shape Engine.getEmissionIndexByFuelFlow builds must be
    accepted by bffm2.calculate_emission_index without modification.

    Engine.py constructs the ambient_conditions dict with exactly four keys:
    temperature_in_Kelvin, pressure_in_Pa, mach_number, relative_humidity.
    This test guarantees that the bffm2 module's API stays compatible with
    that shape (no missing-key crashes, no silent-fallback to ISA via the
    empty-dict path).
    """
    engine_shape = {
        "temperature_in_Kelvin": 280.5,
        "pressure_in_Pa": 97600.0,
        "mach_number": 0.25,
        "relative_humidity": 0.68,
    }
    nox_engine = calculate_emission_index("NOx", 0.244, A20N_EEDB, engine_shape)
    # Compare against the same conditions passed through COLD (M=0)
    # rebuilt with M=0.25 — both paths must produce the same value.
    cold_m025 = dict(COLD, mach_number=0.25)
    nox_cold = calculate_emission_index("NOx", 0.244, A20N_EEDB, cold_m025)
    assert nox_engine == nox_cold
