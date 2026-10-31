# ANP 2.2 profile build

For maintainers: how the default aircraft profiles are rebuilt from the ANP
v2.2 tables. `build_anp22_profiles.py` rebuilds `open_alaqs/database/data/default_aircraft_profiles.csv`
and the default profile columns of `open_alaqs/database/data/default_aircraft.csv`
from the 5.3.5 tables (git revision `c8a55cd`) and the ANP v2.2 tables.
The reasoning and the checks are in [AIRCRAFT_PROFILES_PROVENANCE.md](../../documents/developer/AIRCRAFT_PROFILES_PROVENANCE.md).

```bash
python3 tools/anp22_profiles/build_anp22_profiles.py --anp-dir /path/to/anp_v2_2
```

`--anp-dir` must hold `Aircraft.csv`, `Default_weights.csv`,
`Default_fixed_point_profiles.csv` and
`ANP v2.2 Aircraft substitutions - jets & heavy props (22022018).xlsx`
(needs `openpyxl`). The ANP tables are not in the repository.

Outputs in `output/`:

* `profile_build_log.csv`: one row per profile (origin, power treatment,
  capped points, weight source).
* `default_aircraft_mapping.csv`: one row per aircraft type (old and new
  defaults, rule a/b/c, ANP proxy, basis).

After a rebuild, update the fixtures with
`tools/test_fixtures/regenerate_default_aircraft_profiles.py` and
`tools/test_fixtures/regenerate_default_aircraft.py`.

See also:

- [AIRCRAFT_PROFILES_PROVENANCE.md](../../documents/developer/AIRCRAFT_PROFILES_PROVENANCE.md): provenance of the profiles
- [tools/test_fixtures](../test_fixtures/README.md): updating the fixtures after a rebuild
- [Flight profiles (ANP)](../../documents/methods/AIRCRAFT_EMISSIONS.md#flight-profiles-anp): how the plugin uses the profiles
