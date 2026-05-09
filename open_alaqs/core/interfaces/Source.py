class Source:
    # ------------------------------------------------------------------
    # Loop-ordering discriminator.
    #
    # `True`  -> the geometric footprint is fixed for the whole study
    #            year. The vectorised emission path can compute spatial
    #            cell weights once per source and produce an entire
    #            8760/8784-element hourly emission vector in a single
    #            pass, then hand it to the output modules.
    # `False` -> the source's footprint or activity binding to geometry
    #            varies over time (gates/taxiways/aircraft movements).
    #            Stays on the legacy time-major hot loop in
    #            EmissionCalculation.run().
    #
    # only declares the flag; it is read in when
    # EmissionCalculation partitions modules between the two paths. The
    # base class default is False so the legacy code path is preserved
    # for any class that has not been audited yet.
    # ------------------------------------------------------------------
    time_invariant_geometry: bool = False

    def __init__(self, val=None, *args, **kwargs):
        if val is None:
            val = {}

        # Locale-tolerant float parsing for DB-sourced values (GitHub #159).
        from open_alaqs.core.tools.conversion import convertToFloat

        self._height = convertToFloat(val.get("height", 0), default=0.0)
        # Database schema uses "hour_profile" / "month_profile" (see
        # RoadwaySources.RoadwaySourcesDatabase, PointSources, etc.) but
        # historical callers also pass "hourly_profile" / "monthly_profile".
        # Accept either; prefer the schema names. Without this, sources
        # silently fall back to the all-1.0 "default" profile and produce
        # a flat hourly time series. See PR comment for full reproduction.
        self._hour_profile = str(
            val.get("hour_profile", val.get("hourly_profile", "default"))
        )
        self._daily_profile = str(val.get("daily_profile", "default"))
        self._month_profile = str(
            val.get("month_profile", val.get("monthly_profile", "default"))
        )
        self._geometry_text = str(val.get("geometry", ""))
        self._unit_year = None
        self._emissionIndex = None
        self._id = None

        # Capture the `instudy` flag from the source row. Rows with
        # `instudy='0'` are excluded from emission output by the
        # *SourceModule.process() filter. Default to True so legacy
        # callers that build sources from non-DB inputs (programmatic
        # construction, tests) are unaffected. See `isInStudy()`.
        self._in_study = str(val.get("instudy", "1")).strip() == "1"

    def isInStudy(self) -> bool:
        """Return True if this source should be included in the
        emission calculation. Sources with `instudy='0'` in the
        spatialite layer are excluded; this is the read-side of that
        contract.
        """
        return self._in_study

    def getName(self):
        return self._id

    def getEmissionIndex(self):
        return self._emissionIndex

    def setEmissionIndex(self, val):
        self._emissionIndex = val

    def getUnitsPerYear(self):
        return self._unit_year

    def getHeight(self):
        return self._height

    def setHeight(self, var):
        self._height = var

    def getHourProfile(self):
        return self._hour_profile

    def getDailyProfile(self):
        return self._daily_profile

    def getMonthProfile(self):
        return self._month_profile

    def getGeometryText(self):
        return self._geometry_text

    def setGeometryText(self, val):
        self._geometry_text = val

    # ------------------------------------------------------------------
    # Vectorised activity expansion.
    #
    # Returns a length 8760/8784 ndarray of per-hour activity 'units'
    # for the source. Summing the array yields the annual total
    # (`getUnitsPerYear()` on most subclasses; `PointSources` overrides
    # to use `getOpsYear()` since its annual scalar comes from a
    # different column).
    #
    # This method is the source-level analogue of the per-hour scalar
    # path:
    #     SourceModule.getRelativeActivityPerHour(...)
    # The two paths produce element-wise equal results within float
    # precision; see profiles_vec.hourly_multipliers for the
    # normalisation invariant proof.
    #
    # only adds this method; downstream callers (the
    # *SourceModule.process methods) keep their per-hour scalar path
    # until wires up the source-major loop.
    # ------------------------------------------------------------------
    def getHourlyActivityVector(self, profiles, year: int):
        """Return an ndarray of length `hours_in_year(year)` whose sum
        equals `getUnitsPerYear()` to float precision.

        Parameters
        ----------
        profiles
            A `core.tools.profiles_vec.ProfileSet` built from the
            already-populated User{Hour,Day,Month}ProfileStore
            singletons.
        year
            Calendar year of the inventory (used for leap-year length
            and weekday/month calendar walk).

        Returns
        -------
        numpy.ndarray of shape (8760,) or (8784,), dtype float.
        """
        # Local import to keep Source.py free of numpy/pandas imports
        # at module-load time; ProfileSet is the only external type
        # involved and it is pure data.
        from open_alaqs.core.tools.profiles_vec import (hourly_multipliers,
                                                        spread_annual)

        mults = hourly_multipliers(
            profiles,
            self.getHourProfile(),
            self.getDailyProfile(),
            self.getMonthProfile(),
            year,
        )
        return spread_annual(float(self.getUnitsPerYear() or 0.0), mults)
