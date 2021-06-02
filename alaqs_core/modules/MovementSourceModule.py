"""
This class provides the module to calculate emissions of movements.
"""

import pandas as pd

from open_alaqs.alaqs_core import alaqslogging
from open_alaqs.alaqs_core.interfaces.AmbientCondition import AmbientCondition
from open_alaqs.alaqs_core.interfaces.Emissions import Emission
from open_alaqs.alaqs_core.interfaces.Movement import MovementStore
from open_alaqs.alaqs_core.interfaces.SourceModule import SourceModule
from open_alaqs.alaqs_core.tools import conversion

logger = alaqslogging.logging.getLogger(__name__)
logger.setLevel('DEBUG')
file_handler = alaqslogging.logging.FileHandler(alaqslogging.LOG_FILE_PATH)
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
formatter = alaqslogging.logging.Formatter(log_format)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


class MovementSourceModule(SourceModule):
    """
    Calculate emissions due to movements
    """

    @staticmethod
    def getModuleName():
        return "MovementSource"

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        SourceModule.__init__(self, values_dict)

        if not self.getDatabasePath() is None:
            self.setStore(MovementStore(self.getDatabasePath()))

        self._calculation_limit = {
            "max_height": 914.4,
            "height_unit_in_feet":False
        }
        #self.limit = {}

        self._installation_corrections = {
                        "Takeoff":1.010,    # 100%
                        "Climbout":1.012,   # 85%
                        "Approach":1.020,   # 30%
                        "Idle":1.100        # 7%
        }
        # self._installation_corrections = {}

        self._ambient_conditions = AmbientCondition()

        # self._method = {"name": "BFFM2"} #method="linear_scaling", "matching", "bymode", "BFFM2"
        if not ("Method" in values_dict):
            values_dict["Method"] = {}
        self._method = {"name": values_dict["Method"]["selected"] if ("selected" in values_dict["Method"] and "Method" in values_dict) else ""}

        self._nox_correction = values_dict["Apply NOx corrections"] if ("Apply NOx corrections" in values_dict) else False
        self._smooth_and_shift = values_dict["Source Dynamics"]["selected"] if "Source Dynamics" in values_dict and "selected" in values_dict["Source Dynamics"] else 'None'
        self._reference_altitude = values_dict["reference_altitude"] if ("reference_altitude" in values_dict) else 0.0


    def getMethod(self):
        return self._method
    def setMethod(self, var):
        self._method = var

    def getApplyNOxCorrection(self):
        return self._nox_correction
    def setApplyNOxCorrection(self, var):
        self._nox_correction = var

    def getApplySmoothAndShift(self):
        return self._smooth_and_shift
    def setApplySmoothAndShift(self, var):
        self._smooth_and_shift = var

    def getAirportAltitude(self):
        return self._reference_altitude
    def setAirportAltitude(self, var):
        self._reference_altitude = var

    def getCalculationLimit(self):
        return self._calculation_limit
    def setCalculationLimit(self, var):
        self._calculation_limit = var

    def getAmbientConditions(self):
        return self._ambient_conditions
    def setAmbientConditions(self, var):
        self._ambient_conditions = var

    def getInstallationCorrections(self):
        return self._installation_corrections
    def setInstallationCorrections(self, var):
        self._installation_corrections = var

    # def getMovements(self):
    #     return pd.DataFrame.from_dict(self.getStore().getMovementDatabase().getEntries(), orient='index')

    def FetchGateEmissions(self, group, method, source_names, runway_names):

        movement = group["Sources"].iloc[0]
        # movement_name = movement.getName()

        # process only movements of the runway under study
        if runway_names and not (movement.getRunway().getName() in runway_names):
            return pd.Int64Index([], dtype='int64'), None
            # continue
        if source_names and not ("all" in source_names) and not (movement.getName() in source_names):
            return pd.Int64Index([], dtype='int64'), None
            # continue

        gate_emissions = movement.calculateGateEmissions(sas=method["config"]["apply_smooth_and_shift"])
        return gate_emissions

    def FetchFlightEmissions(self, group, method, mode, limit, source_names, runway_names, atRunway=True):

        movement = group["Sources"].iloc[0]

        if source_names and not ("all" in source_names) and not (movement.getName() in source_names):
            return pd.Int64Index([], dtype='int64'), None
            # continue
        flight_emissions = movement.calculateFlightEmissions(atRunway, method, mode, limit)
        return flight_emissions

    def beginJob(self):
        SourceModule.beginJob(self)#super(MovementSourceModule, self).beginJob()

    def process(self, startTimeSeries, endTimeSeries, source_names=[], runway_names=[], ambient_conditions=None, **kwargs):

        result_ = []

        defaultEmissions={
                "fuel_kg" : 0.,
                "co_g" : 0.,
                "co2_g" : 0.,
                "hc_g" : 0.,
                "nox_g" : 0.,
                "sox_g" : 0.,
                "pm10_g" : 0.,
                "p1_g" : 0.,
                "p2_g": 0.,
                "pm10_prefoa3_g" : 0.,
                "pm10_nonvol_g" : 0.,
                "pm10_sul_g" : 0.,
                "pm10_organic_g" : 0.
            }

        try:
            self.getCalculationLimit()['max_height'] = ambient_conditions.getMixingHeight()
        except:
            # limit set by default to 3000 ft
            self.getCalculationLimit()['max_height'] = conversion.convertFeetToMeters(3000.)
            logger.info("Taking default mixing height (3000ft) on %s"%startTimeSeries.getTimeAsDateTime())

        limit_ = self.getCalculationLimit()
        limit_["height_unit_in_feet"]=False

        calc_method = {
            "name": self.getMethod()["name"],
            "config": {
                "apply_smooth_and_shift": self.getApplySmoothAndShift(),
                "apply_nox_corrections": self.getApplyNOxCorrection(),
                "airport_altitude": self.getAirportAltitude(),
                "installation_corrections": self.getInstallationCorrections(),
                "ambient_conditions": ambient_conditions  # ac
            }
        }

        # Load movements from DataFrame
        df = self.LoadMovementsDataFrame()

        df.loc[:, "RunwayTime"] = [mov.getRunwayTime() for mov in df["Sources"]]
        if df[(df["RunwayTime"] >= startTimeSeries.getTime()) &
                (df["RunwayTime"] < endTimeSeries.getTime())].empty:
            return result_

        else:
            df.loc[:, "gate"] = [mov.getGate().getName() for mov in df["Sources"]]

            df.loc[:, "ac_group"] = [mov.getAircraft().getGroup() for mov in df["Sources"]]

            df.loc[:, "aircraft"] = [mov.getAircraft().getName() for mov in df["Sources"]]

            df.loc[:, "engine"] = [mov.getAircraftEngine().getName() for mov in df["Sources"]]

            df.loc[:, "departure_arrival"] = [mov.getDepartureArrivalFlag() for mov in df["Sources"]]

            df.loc[:, "profile_id"] = [mov.getAircraft().getDefaultDepartureProfileName() if mov.isDeparture() else
                                       mov.getAircraft().getDefaultArrivalProfileName() for mov in df["Sources"]]


            # df.loc[:, "GateEmissions"] = [Emission(defaultValues=defaultEmissions)]
            df.loc[:, "GateEmissions"] = pd.Series([Emission(defaultValues=defaultEmissions)])
            # df.loc[:, "FlightEmissions"] = [Emission(defaultValues=defaultEmissions)]
            df.loc[:, "FlightEmissions"] = pd.Series([Emission(defaultValues=defaultEmissions)])

            df = df.astype('object')



            # time_interval_df = df[(df["RunwayTime"] >= startTimeSeries.getTime()) &
        #         (df["RunwayTime"] < endTimeSeries.getTime())]
        # if not time_interval_df.empty:

        # if not df[(df["RunwayTime"] >= startTimeSeries.getTime()) &
        #         (df["RunwayTime"] < endTimeSeries.getTime())].empty:

            """
            Calculate Gate Emissions
            """
            # Fetch movements that use this runway for this time period
            grouped_by_gate_ac = df[(df["RunwayTime"] >= startTimeSeries.getTime()) &
                (df["RunwayTime"] < endTimeSeries.getTime())].groupby(["gate", "ac_group", "departure_arrival"])

            for name, group in grouped_by_gate_ac:
                gemissions = self.FetchGateEmissions(group, calc_method, source_names, runway_names)

                if not grouped_by_gate_ac.groups[name].empty:
                    for ix in grouped_by_gate_ac.groups[name]:
                        df.loc[ix, "GateEmissions"] = gemissions


            """
            Calculate Flight Emissions
            """
            mode_ = ""
            # atRunway = True
            # Fetch movements that use this runway for this time period
            # grouped_by_ac_type = time_interval_df.groupby(["aircraft","engine","profile_id", "departure_arrival"])
            grouped_by_ac_type = df[(df["RunwayTime"] >= startTimeSeries.getTime()) &
                (df["RunwayTime"] < endTimeSeries.getTime())].groupby(["engine","profile_id"])

            for name, group in grouped_by_ac_type:
                flight_emissions = self.FetchFlightEmissions(group, calc_method, mode_, limit_, source_names, runway_names)
                if not grouped_by_ac_type.groups[name].empty:
                    for ix in grouped_by_ac_type.groups[name]:
                        df.loc[ix, "FlightEmissions"] = flight_emissions

            """
            Calculate Taxiing Emissions
            """
            # emissions_extended = []
            for movement_name, movement in self.getSources().items():

                #process only movements of the runway under study
                if runway_names and not (movement.getRunway().getName() in runway_names):
                    continue
                if source_names and ("all" not in source_names) and (movement.getName() not in source_names):
                    continue
                # Fetch movements that use this runway for this time period
                if not (movement.getRunwayTime()>=startTimeSeries.getTime() and movement.getRunwayTime()<endTimeSeries.getTime()):
                    continue

                # add Taxiing Emissions
                TE = movement.calculateTaxiingEmissions(sas=calc_method["config"]["apply_smooth_and_shift"])

                # add Gate Emissions
                GE = df[df["Sources"] == movement]["GateEmissions"].iloc[0]

                # add Flight Emissions
                FE = df[df["Sources"] == movement]["FlightEmissions"].iloc[0]

                emissions_extended = TE+GE+FE

                # import geopandas as gpd
                # import matplotlib.pyplot as plt
                # import mplleaflet
                # import datetime
                # gdf = gpd.GeoDataFrame(index=range(0, len(emissions_extended)), columns=["NOx", "geometry"])
                # cnt = 0
                if emissions_extended:
                    emissions_ = []
                    for em_ in emissions_extended:
                        if "emissions" in em_ and not em_["emissions"] is None:
                            if not em_["emissions"].isZero():
                                emissions_.append(em_["emissions"].transposeToKilograms())

                                # gdf.loc[cnt, "NOx"] = em_["emissions"].transposeToKilograms().getValue("NOx", unit="kg")[0]
                                # gdf.loc[cnt, "geometry"] = em_["emissions"].getGeometry()
                                # cnt += +1

                    emissions_extended = emissions_
                else:
                    logger.warning("No Emissions for %s:" % (movement_name))
                    # emissions_extended = [Emission(defaultValues=defaultEmissions)]
                    emissions_extended = None

                result_.append((startTimeSeries.getTimeAsDateTime(), movement, emissions_extended))

        return result_

    def endJob(self):
        SourceModule.endJob(self)
