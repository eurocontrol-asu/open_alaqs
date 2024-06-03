class Source:
    def __init__(self, val=None, *args, **kwargs):
        if val is None:
            val = {}

        self._height = float(val.get("height", 0))
        self._hour_profile = str(val.get("hourly_profile", "default"))
        self._daily_profile = str(val.get("daily_profile", "default"))
        self._month_profile = str(val.get("monthly_profile", "default"))
        self._geometry_text = str(val.get("geometry", ""))
        self._unit_year = None
        self._emissionIndex = None
        self._id = None

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
