"""
This class provides the module to calculate emissions of movements.
"""

from datetime import datetime
from typing import List, Tuple, TypedDict

import pandas as pd

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.AmbientCondition import AmbientCondition
from open_alaqs.core.interfaces.Emissions import Emission
from open_alaqs.core.interfaces.Movement import EmissionsDict, MovementStore
from open_alaqs.core.interfaces.Source import Source
from open_alaqs.core.interfaces.SourceModule import SourceModule

logger = get_logger(__name__)


class CalcMethodConfigDict(TypedDict):
    apply_smooth_and_shift: str
    apply_nox_corrections: bool
    airport_altitude: float
    installation_corrections: dict[str, float]
    ambient_conditions: AmbientCondition


class CalcMethodDict(TypedDict):

    name: str
    config: CalcMethodConfigDict


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

        if self.getDatabasePath() is not None:
            movement_store = MovementStore(self.getDatabasePath())
            self.setStore(movement_store)

        self._calculation_limit = {"max_height": 914.4, "height_unit_in_feet": False}

        self._installation_corrections = {
            "Takeoff": 1.010,  # 100%
            "Climbout": 1.012,  # 85%
            "Approach": 1.020,  # 30%
            "Idle": 1.100,  # 7%
        }

        self._ambient_conditions = AmbientCondition()

        self._method = {"name": values_dict.get("method", "")}
        self._nox_correction = values_dict.get("should_apply_nox_corrections", False)
        self._smooth_and_shift = values_dict.get("source_dynamics", "none")
        self._reference_altitude = values_dict.get("reference_altitude", 0.0)

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

    def FetchGateEmissions(
        self,
        group: pd.DataFrame,
        method: CalcMethodDict,
        source_names: list[str],
        runway_names: list[str],
    ) -> list[EmissionsDict]:

        movement = group["Sources"].iloc[0]
        # movement_name = movement.getName()

        # process only movements of the runway under study
        if runway_names and not (movement.getRunway().getName() in runway_names):
            return []

        if (
            source_names
            and not ("all" in source_names)
            # to be sure not getting a movement beloging to another source_name
            and not (movement.getName() in source_names)
        ):
            return []

        gate_emissions = movement.calculateGateEmissions(
            sas=method["config"]["apply_smooth_and_shift"]
        )
        return gate_emissions

    def FetchFlightEmissions(
        self,
        group: pd.DataFrame,
        method: CalcMethodDict,
        mode: str,
        limit: dict,
        source_names: list[str],
        runway_names: list[str],
        atRunway: bool = True,
    ) -> list[EmissionsDict]:

        movement = group["Sources"].iloc[0]

        if (
            source_names
            and not ("all" in source_names)
            # to be sure not getting a movement beloging to another source_name
            and not (movement.getName() in source_names)
        ):
            return []
            # continue
        flight_emissions = movement.calculateFlightEmissions(
            atRunway, method, mode, limit
        )
        return flight_emissions

    @staticmethod
    def getDefaultProfileName(movement):
        if movement.isDeparture():
            return movement.getAircraft().getDefaultDepartureProfileName()
        return movement.getAircraft().getDefaultArrivalProfileName()

    def addAdditionalColumnsToDataFrame(self):
        """
        Add additional movement information to the dataframe

        """

        # Set default emissions
        default_emission = Emission(
            defaultValues={
                "fuel_kg": 0.0,
                "co_g": 0.0,
                "co2_g": 0.0,
                "hc_g": 0.0,
                "nox_g": 0.0,
                "sox_g": 0.0,
                "pm10_g": 0.0,
                "p1_g": 0.0,
                "p2_g": 0.0,
                "pm10_prefoa3_g": 0.0,
                "pm10_nonvol_g": 0.0,
                "pm10_sul_g": 0.0,
                "pm10_organic_g": 0.0,
                "nvpm_g": 0.0,
                "nvpm_number": 0.0,
            }
        )

        # Create a function that returns a list of default emissions
        def _default_emissions(*args):
            return [default_emission]

        # Load movements from DataFrame
        df = self.getDataframe()

        # Add the runway times
        df.loc[:, "RunwayTime"] = [mov.getRunwayTime() for mov in df["Sources"]]

        # Add the gate
        df.loc[:, "gate"] = [mov.getGate().getName() for mov in df["Sources"]]

        # Add the aircraft and aircraft group
        df.loc[:, "aircraft"] = [mov.getAircraft().getName() for mov in df["Sources"]]
        df.loc[:, "ac_group"] = [mov.getAircraft().getGroup() for mov in df["Sources"]]

        # Add the engine
        df.loc[:, "engine"] = [
            mov.getAircraftEngine().getName() for mov in df["Sources"]
        ]

        # Add the departure/arrival
        df.loc[:, "departure_arrival"] = [
            mov.getDepartureArrivalFlag() for mov in df["Sources"]
        ]

        # Add the profile id
        df.loc[:, "profile_id"] = df["Sources"].apply(self.getDefaultProfileName)

        # Add default gate and flight emissions
        empty_series = pd.Series(index=df.index, dtype=object)
        # TODO OPENGIS.ch: the type of the `GateEmissions` column would be an `Emission` instance, but later we set it to
        # `{distance_time:float, distance_space:float, emissions: list[Emissions]}`
        df.loc[:, "GateEmissions"] = empty_series.apply(_default_emissions)
        df.loc[:, "FlightEmissions"] = empty_series.apply(_default_emissions)

        # Update the DataFrame
        self._dataframe = df.astype("object")

    def _getMovementsIndicesBySourceNames(
        self, df: pd.DataFrame, source_names: list[str]
    ) -> pd.Series:
        cache_key = tuple(sorted(source_names))

        if cache_key not in self._cachedMovementIndexBySourceNames:
            self._cachedMovementIndexBySourceNames[cache_key] = df.apply(
                lambda r: r["Sources"].getName() in source_names,
                axis=1,
            )

        return self._cachedMovementIndexBySourceNames[cache_key]

    def beginJob(self):
        self.loadSources()
        self.convertSourcesToDataFrame()
        self.addAdditionalColumnsToDataFrame()

        # reset the movement index cache
        self._cachedMovementIndexBySourceNames: dict[tuple[str, ...], pd.Series] = {}

    def process(
        self,
        start_dt: datetime,
        end_dt: datetime,
        source_names=None,
        runway_names=None,
        ambient_conditions=None,
        vertical_limit_m: float = 914.4,
        **kwargs,
    ) -> List[Tuple[datetime, Source, Emission]]:
        if runway_names is None:
            runway_names = []
        if source_names is None:
            source_names = []
        result_ = []

        try:
            self.getCalculationLimit()[
                "max_height"
            ] = ambient_conditions.getMixingHeight()
        except AttributeError:
            self.getCalculationLimit()["max_height"] = vertical_limit_m
            logger.info(
                "Taking default mixing height (3000ft) on %s",
                start_dt,
            )

        limit_ = self.getCalculationLimit()
        limit_["height_unit_in_feet"] = False

        calc_method: CalcMethodDict = {
            "name": self.getMethod()["name"],
            "config": {
                "apply_smooth_and_shift": self.getApplySmoothAndShift(),
                "apply_nox_corrections": self.getApplyNOxCorrection(),
                "airport_altitude": self.getAirportAltitude(),
                "installation_corrections": self.getInstallationCorrections(),
                "ambient_conditions": ambient_conditions,
            },
        }

        # Load movements from DataFrame
        df = self.getDataframe()

        # Get the movements that match the source names
        if source_names and "all" not in source_names:
            df = df[self._getMovementsIndicesBySourceNames(df, source_names)]

        # Get the movements between start and end time of this period
        relevant_movements = (df["RunwayTime"] >= start_dt.timestamp()) & (
            df["RunwayTime"] < end_dt.timestamp()
        )

        # Return an empty list if there are no movements in this period
        if df[relevant_movements].empty:
            return []

        """
        Calculate Gate Emissions
        """

        # Perform the gate calculation once for each group
        gate_columns = ["gate", "ac_group", "departure_arrival"]
        for _name, group in df[relevant_movements].groupby(gate_columns):

            # Calculate the gate emissions
            gate_emissions = self.FetchGateEmissions(
                group, calc_method, source_names, runway_names
            )

            to_remove = []
            for index, em_ in enumerate(gate_emissions):
                if em_["emissions"].isZero():
                    logger.warning(
                        f"Skip zero value emissions for Gate: {_name[0]}, AC Group: {_name[1]} and arr/dep: {_name[2]} - index {index}"
                    )
                    to_remove.append(index)
            if to_remove:
                logger.warning(
                    f"Removed: {len(to_remove)} over {len(gate_emissions)} gate emissions because zero value"
                )
            for index in reversed(to_remove):
                gate_emissions.pop(index)

            # Update the gate emissions
            for ix in group.index:
                df.at[ix, "GateEmissions"] = gate_emissions

        """
        Calculate Flight Emissions
        """

        # Configure the flight emissions calculation
        mode_ = ""

        # flight_columns=["aircraft","engine","profile_id", "departure_arrival"]
        flight_columns = ["engine", "profile_id"]
        flight_columns = [
            "engine",
            "profile_id",
            # The profile and engine will calculate the pollutant emissions correctly, but the Emissions geometry will be incorrect.
            # This is because the Profile shows the path of the airplane ignoring the azimuth of the Runway
            # and it's geometry is stored precalculated with the Runway in the resulting FlightEmissions object.
            # However, the geometry needs to be rotated to match the respective Runway of each Movement.
            lambda idx: df.loc[idx]["Sources"].getRunway().getName(),
        ]
        for grouped_values, group in df[relevant_movements].groupby(flight_columns):

            # Determine the flight emissions
            flight_emissions = self.FetchFlightEmissions(
                group, calc_method, mode_, limit_, source_names, runway_names
            )

            to_remove = []
            for index, em_ in enumerate(flight_emissions):
                if em_["emissions"].isZero():
                    logger.debug(
                        f"Skip zero value emissions for Engine: {grouped_values[0]}, profile id: {grouped_values[1]}"
                    )
                    to_remove.append(index)
            if to_remove:
                logger.debug(
                    f"Removed: {len(to_remove)} over {len(flight_emissions)} flight emissions because zero value"
                )
            for index in reversed(to_remove):
                flight_emissions.pop(index)

            # Update the flight emissions
            for ix in group.index:
                df.at[ix, "FlightEmissions"] = flight_emissions

        """
        Calculate Taxiing Emissions
        """
        for movement_name, movement in self.getSources().items():

            # process only movements of the runway under study
            if runway_names and not (movement.getRunway().getName() in runway_names):
                continue
            if (
                source_names
                and ("all" not in source_names)
                and (movement.getName() not in source_names)
            ):
                continue
            # Fetch movements that use this runway for this time period
            if not (
                start_dt.timestamp() <= movement.getRunwayTime() < end_dt.timestamp()
            ):
                continue

            # add Taxiing Emissions
            te = movement.calculateTaxiingEmissions(
                sas=calc_method["config"]["apply_smooth_and_shift"]
            )

            to_remove = []
            for index, em_ in enumerate(te):
                if em_["emissions"].isZero():
                    logger.warning(
                        f"Skip zero value emissions for Taxiing with index {index}"
                    )
                    to_remove.append(index)
            if to_remove:
                logger.warning(
                    f"Removed: {len(to_remove)} over {len(te)} taxiing emissions because zero value"
                )
            for index in reversed(to_remove):
                te.pop(index)

            # add Gate Emissions
            ge = df[df["Sources"] == movement]["GateEmissions"].iloc[0]

            # add Flight Emissions
            fe = df[df["Sources"] == movement]["FlightEmissions"].iloc[0]

            emissions_extended = te + ge + fe

            # import geopandas as gpd
            # import matplotlib.pyplot as plt
            # import mplleaflet
            # import datetime
            # gdf = gpd.GeoDataFrame(index=range(0, len(emissions_extended)), columns=["NOx", "geometry"])
            # cnt = 0
            if emissions_extended:
                emissions_ = []
                for em_ in emissions_extended:
                    if "emissions" in em_ and em_["emissions"] is not None:
                        emissions_.append(em_["emissions"].transposeToKilograms())

                emissions_extended = emissions_
            else:
                logger.warning("No Emissions for %s:" % (movement_name))
                # emissions_extended = [Emission(defaultValues=defaultEmissions)]
                emissions_extended = None

            result_.append((start_dt, movement, emissions_extended))

        return result_

    def endJob(self):
        SourceModule.endJob(self)
