"""
Regression test for the source profile name mismatch bug.

Bug: in `core/interfaces/Source.py`, the constructor previously read
profile names using keys "hourly_profile" / "monthly_profile", but the
database schema (e.g. `shapes_roadways`) uses "hour_profile" /
"month_profile". Two of three keys mismatched. Hour and month profiles
silently fell through to the literal "default", which resolves to the
all-1.0 default profile in user_hour_profile / user_month_profile.

Effect: any roadway / point / parking / area / GSE source with non-default
hour or month profiles produced a flat hourly time series. Annual totals
were correct (the daily profile happened to match), but within-day and
within-year distributions were wiped out.

Fix: accept either name in Source.__init__ (schema name preferred).

These tests pin both schema names and (for backward-compat) the older
"hourly"/"monthly" names so a future refactor can't silently regress.
"""


class TestSourceProfileNameMismatchRegression:
    """Pin profile-name handling against the original bug."""

    def test_source_reads_schema_column_names(self):
        """Source must accept hour_profile / month_profile (database schema)."""
        from open_alaqs.core.interfaces.Source import Source

        s = Source(
            {
                "hour_profile": "rush_hour_pattern",
                "daily_profile": "weekday_pattern",
                "month_profile": "summer_pattern",
            }
        )
        assert s._hour_profile == "rush_hour_pattern"
        assert s._daily_profile == "weekday_pattern"
        assert s._month_profile == "summer_pattern"

    def test_source_reads_alias_names(self):
        """Backward compatibility: callers using older
        hourly_profile / monthly_profile keys must still work."""
        from open_alaqs.core.interfaces.Source import Source

        s = Source(
            {
                "hourly_profile": "rush_hour_pattern",
                "daily_profile": "weekday_pattern",
                "monthly_profile": "summer_pattern",
            }
        )
        assert s._hour_profile == "rush_hour_pattern"
        assert s._daily_profile == "weekday_pattern"
        assert s._month_profile == "summer_pattern"

    def test_schema_names_take_precedence_when_both_present(self):
        """If a row dict somehow has both names, the schema name wins.
        This matches what SQLSerializable produces (only schema names)."""
        from open_alaqs.core.interfaces.Source import Source

        s = Source(
            {
                "hour_profile": "schema_name",
                "hourly_profile": "alias_name",
                "month_profile": "schema_name",
                "monthly_profile": "alias_name",
            }
        )
        assert s._hour_profile == "schema_name"
        assert s._month_profile == "schema_name"

    def test_missing_keys_fall_back_to_default(self):
        """When neither name is provided, fall back to "default" string
        (which resolves to the all-1.0 profile in user_hour_profile)."""
        from open_alaqs.core.interfaces.Source import Source

        s = Source({})
        assert s._hour_profile == "default"
        assert s._daily_profile == "default"
        assert s._month_profile == "default"

    def test_subclass_inherits_correct_profile_handling(self):
        """Subclasses of Source must inherit the fix transparently.
        Uses a synthetic subclass instead of RoadwaySources to keep this
        test independent of the qgis runtime (which the standalone test
        runner does not have)."""
        from open_alaqs.core.interfaces.Source import Source

        class _SyntheticRoadwaySource(Source):
            def __init__(self, val=None, *args, **kwargs):
                super().__init__(val, *args, **kwargs)

        # This is the exact dict shape that SQLSerializable produces
        # when reading a row from `shapes_roadways`.
        r = _SyntheticRoadwaySource(
            {
                "roadway_id": "TEST_SEGMENT",
                "hour_profile": "inw_test_hour",
                "daily_profile": "inw_test_day",
                "month_profile": "rtha_test_month",
                "height": 0,
            }
        )
        assert r.getHourProfile() == "inw_test_hour"
        assert r.getDailyProfile() == "inw_test_day"
        assert r.getMonthProfile() == "rtha_test_month"
