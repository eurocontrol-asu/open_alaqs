"""
This class provides the module to calculate emissions of movements.
"""

from datetime import datetime
from typing import Tuple, TypedDict

import pandas as pd

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.GeoTransformation import (
    SmoothAndShiftTransformer,
    VerticalExtentTransformer,
)
from open_alaqs.core.interfaces.AmbientCondition import AmbientCondition
from open_alaqs.core.interfaces.Emissions import Emission
from open_alaqs.core.interfaces.Movement import MovementStore, defaultEmissions
from open_alaqs.core.interfaces.Source import Source
from open_alaqs.core.interfaces.SourceModule import SourceModule
from open_alaqs.core.MovementEmissionCalculator import (
    FlightEmissionCalculator,
    GateEmissionCalculator,
    TaxiingEmissionCalculator,
)

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
            show_progress = values_dict.get("show_progress", True)
            movement_store = MovementStore(
                self.getDatabasePath(), show_progress=show_progress
            )
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
        self._grid_bounds = values_dict.get("grid_bounds", None)

    def getMethod(self):
        return self._method

    def setMethod(self, var):
        self._method = var

    def getGridBounds(self):
        return self._grid_bounds

    def setGridBounds(self, var):
        self._grid_bounds = var

    def getApplyNOxCorrection(self):
        return self._nox_correction

    def setApplyNOxCorrection(self, var):
        self._nox_correction = var

    def getApplySmoothAndShift(self) -> str:
        return self._smooth_and_shift

    def setApplySmoothAndShift(self, var):
        self._smooth_and_shift = var

    def smoothAndShiftEnabled(self) -> bool:
        sas = self.getApplySmoothAndShift()
        return sas == "default" or sas == "smooth & shift"

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
        default_emission = Emission(defaultValues=defaultEmissions)

        # Create a function that returns a list of default emissions
        def _default_emissions(*args):
            return {
                "emissions": [default_emission],
                "distance_time": 0.0,
                "distance_space": 0.0,
            }

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
        # Then update with _profile_id where available
        for i, mov in enumerate(df["Sources"]):
            if hasattr(mov, "_profile_id") and mov._profile_id:
                df.at[i, "profile_id"] = mov._profile_id

        # try:
        #     default_profiles = df["Sources"].apply(self.getDefaultProfileName)
        #     profile_ids = [getattr(mov, '_profile_id', None) for mov in df["Sources"]]
        #     # Use _profile_id where it exists, otherwise keep default
        #     df.loc[:, "profile_id"] = [pid if pid is not None else default
        #                       for pid, default in zip(profile_ids, default_profiles)]
        #     df.loc[:, "profile_id"] = [mov._profile_id for mov in df["Sources"]]
        # except Exception as e:
        #     # Fallback to just default profiles if anything goes wrong
        #     df.loc[:, "profile_id"] = df["Sources"].apply(self.getDefaultProfileName)
        #     logger.error(f"Error processing profile IDs: {e}")

        # Add default gate and flight emissions
        empty_series = pd.Series(index=df.index, dtype=object)
        df.loc[:, "GateEmissions"] = empty_series.apply(
            _default_emissions
        )  # TODO: apply may have performance issues
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
    ) -> list[Tuple[datetime, Source, Emission]]:
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
        limit_["grid_bounds"] = self.getGridBounds()

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

            movement = group["Sources"].iloc[0]
            if runway_names and movement.getRunway().getName() not in runway_names:
                continue

            gate = movement.getGate()
            if gate is None:
                logger.warning(
                    "Did not find a gate for movement '%s'" % (movement.getName())
                )
                continue  # The corresponding df column already has a default emission dict

            gate_emission_calculator = GateEmissionCalculator(
                gate, movement.getAircraft(), movement.getDepartureArrivalFlag()
            )
            gate_emissions = gate_emission_calculator.calculate_emissions()

            MovementSourceModule.drop_zero_value_emissions(
                gate_emissions,
                f"Gate: {_name[0]}, AC Group: {_name[1]} and arr/dep: {_name[2]}",
            )

            # Apply GeoTransformation, changes are applied in-place
            if self.smoothAndShiftEnabled():
                VerticalExtentTransformer().transform_emissions(gate_emissions)

            # Update the gate emissions
            for ix in group.index:
                df.at[ix, "GateEmissions"] = gate_emissions

        """
        Calculate Flight Emissions
        """

        # Configure the flight emissions calculation
        mode_ = ""
        at_runway_ = True

        # flight_columns=["aircraft","engine","profile_id", "departure_arrival"]
        # flight_columns = ["engine","profile_id"]
        flight_columns = [
            "engine",
            "profile_id",
            # The profile and engine will calculate the pollutant emissions correctly, but the Emissions geometry will be incorrect.
            # This is because the Profile shows the path of the airplane ignoring the azimuth of the Runway,
            # and it's geometry is stored precalculated with the Runway in the resulting FlightEmissions object.
            # However, the geometry needs to be rotated to match the respective Runway of each Movement.
            lambda idx: df.loc[idx]["Sources"].getRunway().getName(),
        ]
        for grouped_values, group in df[relevant_movements].groupby(flight_columns):

            # Determine the flight emissions
            movement = group["Sources"].iloc[0]

            trajectory = (
                movement.getTrajectoryAtRunway()
                if at_runway_
                else movement.getTrajectory()
            )
            if trajectory is None:
                logger.warning(
                    "Did not find a trajectory for movement '%s'" % (movement.getName())
                )
                continue  # The corresponding df column already has a default emission dict

            flight_emission_calculator = FlightEmissionCalculator(
                trajectory,
                movement.getAircraft(),
                movement.getAircraftEngine(),
                movement.getTakeoffWeightRatio(),
                movement.getDepartureArrivalFlag(),
                movement.getName(),
                at_runway=at_runway_,
                method=calc_method,
                mode=mode_,
                limit=limit_,
            )
            flight_emissions = flight_emission_calculator.calculate_emissions()

            MovementSourceModule.drop_zero_value_emissions(
                flight_emissions,
                f"Engine: {grouped_values[0]}, profile id: {grouped_values[1]}",
            )

            # Apply GeoTransformation, changes are applied in-place
            if self.smoothAndShiftEnabled():
                SmoothAndShiftTransformer(
                    movement.getAircraft(),
                    self.getApplySmoothAndShift(),
                    lto_mode=mode_,
                ).transform_emissions(flight_emissions)
            else:
                VerticalExtentTransformer(0, 0).transform_emissions(flight_emissions)

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

            # Add Taxiing Emissions
            if movement.getTaxiRoute() is None:
                te = []
                logger.error(
                    "Did not find a taxi route for movement '%s'. Cannot calculate taxiing emissions.",
                    movement.getName(),
                )
            else:
                taxiing_emission_calculator = TaxiingEmissionCalculator(movement)
                te = taxiing_emission_calculator.calculate_emissions()

                MovementSourceModule.drop_zero_value_emissions(te, "Taxiing")

                # Apply GeoTransformation, changes are applied in-place
                if self.smoothAndShiftEnabled():
                    SmoothAndShiftTransformer(
                        movement.getAircraft(),
                        self.getApplySmoothAndShift(),
                        lto_mode="TX",
                    ).transform_emissions(te)

            # add Gate Emissions
            ge = df[df["Sources"] == movement]["GateEmissions"].iloc[0]

            # add Flight Emissions
            fe = df[df["Sources"] == movement]["FlightEmissions"].iloc[0]

            emissions_extended = te + ge + fe

            if emissions_extended:
                emissions_ = []
                for em_ in emissions_extended:
                    if "emissions" in em_ and em_["emissions"] is not None:
                        emissions_.extend(
                            [e.transposeToKilograms() for e in em_["emissions"]]
                        )

                emissions_extended = emissions_
            else:
                logger.warning("No Emissions for %s:" % (movement_name))
                # emissions_extended = [Emission(defaultValues=defaultEmissions)]
                emissions_extended = None

            result_.append((start_dt, movement, emissions_extended))

        return result_

    def endJob(self):
        SourceModule.endJob(self)

    @staticmethod
    def drop_zero_value_emissions(emissions, source):
        to_remove = []
        for index, em_ in enumerate(emissions):
            # em_["emissions"] is a list of Emissions objects
            if all(e.isZero() for e in em_["emissions"]):
                logger.warning(
                    f"Skip zero value emissions for {source} - index {index}"
                )
                to_remove.append(index)
        if to_remove:
            logger.warning(
                f"Removed: {len(to_remove)} over {len(emissions)} emissions because zero value"
            )
        for index in reversed(to_remove):
            emissions.pop(index)
