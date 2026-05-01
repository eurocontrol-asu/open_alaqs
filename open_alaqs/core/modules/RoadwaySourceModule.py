"""
This class provides all of the calculation methods required to perform emissions
 calculations for roadways.
"""

from datetime import datetime

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Emissions import Emission
from open_alaqs.core.interfaces.RoadwaySources import RoadwaySourcesStore
from open_alaqs.core.interfaces.SourceModule import SourceWithTimeProfileModule
from open_alaqs.core.tools import spatial

_ZERO_EMISSION_VALUES = {
    "fuel_kg": 0.0,
    "co2_kg": 0.0,
    "co_kg": 0.0,
    "hc_kg": 0.0,
    "nox_kg": 0.0,
    "sox_kg": 0.0,
    "pm10_kg": 0.0,
    "p1_kg": 0.0,
    "p2_kg": 0.0,
    "pm10_nonvol_kg": 0.0,
    "pm10_sul_kg": 0.0,
    "pm10_organic_kg": 0.0,
}

logger = get_logger(__name__)


class RoadwaySourceWithTimeProfileModule(SourceWithTimeProfileModule):
    """
    Calculate roadway emissions for a specific roadway based on the roadway name
     and time period

    The emission for any source for each time period is equal to the length of
     the roadway in km multiplied by the
    average emission per vehicle per km multiplied by the number of vehicles for
     the time period

    multiplied by the activity factor for the specific hour. For example:
    \f$E_{co} = Length_{km} \times EF_{co_km} \times  N_{vehicles}\f$

    :param database_path: path to the alaqs output file being displayed/examined
    :param source_name: the name of the roadway to be reviewed
    :return emission_profile: a dict containing the total emissions for each
     pollutant
    :rtype: dict
    """

    @staticmethod
    def getModuleName():
        return "RoadwaySource"

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        SourceWithTimeProfileModule.__init__(self, values_dict)

        if self.getDatabasePath() is not None:
            self.setStore(RoadwaySourcesStore(self.getDatabasePath()))

        self._grid_bounds = values_dict.get("grid_bounds", None)

    def beginJob(self) -> None:
        SourceWithTimeProfileModule.beginJob(self)

    def process(
        self, start_dt: datetime, _end_dt: datetime, source_names=None, **kwargs
    ):
        if source_names is None:
            source_names = []
        result_ = []

        # Use grid_bounds stored at init (passed via EmissionCalculatorService config)
        grid_bounds = self._grid_bounds

        for source_id, source in self.getSources().items():
            if ("all" not in source_names) and (source_id not in source_names):
                continue

            # Get the relative activity (percentage of total emissions) for this hour
            activity_multiplier = self.getRelativeActivityPerHour(
                start_dt,
                source.getUnitsPerYear(),
                source.getHourProfile(),
                source.getDailyProfile(),
                source.getMonthProfile(),
            )

            # Calculate the emissions for this time interval
            emissions = Emission(
                initValues=dict(_ZERO_EMISSION_VALUES), defaultValues={}
            )

            # Get roadway geometry and calculate length_fraction if available
            roadway_geometry = source.getGeometryText()
            length_fraction = 1.0
            clipped_geometry = roadway_geometry

            # Apply grid clipping if grid_bounds is provided
            if grid_bounds is not None and roadway_geometry:
                clipped_geometry, length_fraction = spatial.clip_linestring_to_grid(
                    roadway_geometry, grid_bounds
                )

                if clipped_geometry is None:
                    # Roadway is completely outside grid, skip it
                    logger.debug(
                        f"Roadway {source_id} is completely outside grid bounds, skipping"
                    )
                    continue

            # Add emissions (and convert g to kg)
            # Multiply by effective_length_fraction to account for grid clipping
            emissions.addGeneric(
                source.getEmissionIndex(),
                source.getLength(unitInKM=True)
                * activity_multiplier
                * length_fraction
                / 1000.0,
                unit="gm_km",
                new_unit="kg",
            )

            # Add emission geometry (use clipped geometry if available)
            emissions.setGeometryText(clipped_geometry)

            # Add to list of all emissions
            result_.append((start_dt, source, [emissions]))

        # Return list of all emissions
        return result_

    def endJob(self):
        SourceWithTimeProfileModule.endJob(self)
