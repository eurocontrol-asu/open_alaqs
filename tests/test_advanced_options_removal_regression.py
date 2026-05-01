"""
Regression test for the Advanced Options UI removal.

Earlier the inventory dialog exposed an "Advanced Options" group box with
two configurable widgets:
  - towing_speed (km/h)
  - vert_limit_m / vert_limit_ft (the LTO ceiling)

Both were removed because:
  - towing_speed had no downstream consumer (the value was written to a
    dict that no calculation step ever read).
  - vert_limit was a footgun: the user could set it to anything and the
    plugin would happily compute LTO emissions to e.g. 30000 ft, which
    is not what CAEP14 prescribes. The CAEP14 LTO ceiling is fixed at
    3000 ft = 914.4 m.

This file verifies the runtime contract: the LTO ceiling baked into the
calculation pipeline is 914.4 m at every consumer.

  a. `EmissionCalculatorService.vertical_limit_m` field default.
  b. `MovementSourceModule.process` `vertical_limit_m` arg default.
"""

import inspect


def test_emission_calculator_service_lto_ceiling_default_is_caep():
    """EmissionCalculatorService.vertical_limit_m default == 914.4 m (CAEP)."""
    from open_alaqs.core.EmissionCalculatorService import EmissionCalculationConfig

    fields = {
        f.name: f for f in EmissionCalculationConfig.__dataclass_fields__.values()
    }
    assert "vertical_limit_m" in fields, (
        "EmissionCalculationConfig must declare vertical_limit_m so the LTO "
        "ceiling is explicit at the API surface."
    )
    assert fields["vertical_limit_m"].default == 914.4, (
        f"vertical_limit_m default drifted from CAEP 914.4 m to "
        f"{fields['vertical_limit_m'].default}. Update both this test AND "
        f"the README before changing the constant."
    )


def test_movement_source_module_process_vertical_limit_default_is_caep():
    """MovementSourceModule.process keyword arg vertical_limit_m default is 914.4."""
    from open_alaqs.core.modules.MovementSourceModule import MovementSourceModule

    sig = inspect.signature(MovementSourceModule.process)
    p = sig.parameters.get("vertical_limit_m")
    assert p is not None, (
        "MovementSourceModule.process must accept vertical_limit_m as a keyword "
        "argument so the calculator can pass the CAEP default."
    )
    assert (
        p.default == 914.4
    ), f"vertical_limit_m default drifted from CAEP 914.4 m to {p.default}."
