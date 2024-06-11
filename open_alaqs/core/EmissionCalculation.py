from datetime import datetime, timedelta
from typing import Any, List, TypedDict

from qgis.PyQt import QtCore, QtWidgets

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.AmbientCondition import (
    AmbientCondition,
    AmbientConditionStore,
)
from open_alaqs.core.interfaces.Emissions import Emission
from open_alaqs.core.interfaces.InventoryTimeSeries import InventoryTimeSeriesStore
from open_alaqs.core.interfaces.Source import Source
from open_alaqs.core.modules.ModuleManager import (
    DispersionModuleRegistry,
    SourceModuleRegistry,
)
from open_alaqs.core.tools.Grid3D import Grid3D
from open_alaqs.core.tools.iterator import pairwise

logger = get_logger(__name__)


class GridConfig(TypedDict):
    x_cells: int
    y_cells: int
    z_cells: int
    x_resolution: int
    y_resolution: int
    z_resolution: int
    reference_latitude: float
    reference_longitude: float
    reference_altitude: float


class EmissionCalculation:
    def __init__(
        self,
        db_path: str,
        grid_config: GridConfig,
        start_dt: datetime,
        end_dt: datetime,
        time_interval: timedelta,
    ) -> None:
        assert db_path

        self._database_path = db_path
        self._grid = Grid3D(self._database_path, grid_config)

        # Get the time series for this inventory
        self._start_dt = start_dt
        self._end_dt = end_dt
        self._time_interval = time_interval
        self._inventoryTimeSeriesStore = InventoryTimeSeriesStore(self._database_path)
        self._emissions = {}
        self._source_modules = {}
        self._dispersion_modules = {}
        self._ambient_conditions_store = AmbientConditionStore(self._database_path)

    @staticmethod
    def ProgressBarWidget(dispersion_enabled=False):
        if dispersion_enabled:
            progressbar = QtWidgets.QProgressDialog(
                "Calculating emissions & writing input files for"
                " dispersion model ...",
                "Cancel",
                0,
                99,
            )
        else:
            progressbar = QtWidgets.QProgressDialog(
                "Calculating emissions ...", "Cancel", 0, 99
            )
        progressbar.setWindowTitle("Emissions Calculation")
        # self._progressbar.setValue(1)
        progressbar.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)
        progressbar.setWindowModality(QtCore.Qt.WindowModal)
        progressbar.setAutoReset(True)
        progressbar.setAutoClose(True)
        progressbar.resize(350, 100)
        progressbar.show()
        return progressbar

    def getAmbientCondition(self, t_):
        # Get the ambient conditions
        ac_ = self._ambient_conditions_store.getAmbientConditions(scenario="")

        # Return the ambient condition closest to the provided date
        return min(ac_, key=lambda x: abs(t_ - x.getDate()))

    def add_source_module(
        self, module_name: str, module_config: dict[str, Any]
    ) -> None:
        EmissionSourceModule = SourceModuleRegistry().get_module(module_name)

        self._source_modules[module_name] = EmissionSourceModule(
            values_dict={
                "database_path": self._database_path,
                **module_config,
            }
        )

    def add_dispersion_modules(
        self, module_name: list[str], module_config: dict[str, Any]
    ):
        DispersionSourceModule = DispersionModuleRegistry().get_module(module_name)

        self._dispersion_modules[module_name] = DispersionSourceModule(
            values_dict={
                "database_path": self._database_path,
                **module_config,
            }
        )

    def run(self, source_names: List, vertical_limit_m: float):
        if source_names is None:
            source_names = []

        default_emissions = {
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

        # check if a dispersion module is enabled
        dispersion_enabled = len(self.getDispersionModules()) > 0

        # list the selected modules
        logger.debug("Selected source modules: %s", ", ".join(self.getModules().keys()))
        logger.debug(
            "Selected dispersion modules: %s",
            (
                ", ".join(self.getDispersionModules().keys())
                if dispersion_enabled
                else None
            ),
        )

        # execute beginJob(..) of SourceModules
        logger.debug("Execute beginJob(..) of source modules")
        for mod_name, mod_obj in self.getModules().items():
            mod_obj.beginJob()

        # execute beginJob(..) of dispersion modules
        logger.debug("Execute beginJob(..) of dispersion modules")
        for (
            dispersion_mod_name,
            dispersion_mod_obj,
        ) in self.getDispersionModules().items():
            dispersion_mod_obj.beginJob()

        # execute process(..)
        logger.debug("Execute process(..)")
        try:
            # configure the progress bar
            progressbar = self.ProgressBarWidget(dispersion_enabled=dispersion_enabled)
            count_ = 0
            total_count_ = len(list(self.getTimeSeries())) - 1

            # loop on complete period
            for start_dt, end_dt in pairwise(self.getTimeSeries()):
                logger.debug(f"start {start_dt}, end {end_dt}")

                # update the progress bar
                progressbar.setValue(int(100 * count_ / total_count_))
                count_ += +1
                QtCore.QCoreApplication.instance().processEvents()
                if progressbar.wasCanceled():
                    raise StopIteration("Operation canceled by user")

                # get the ambient condition
                # ToDo: only run on (start_, end_) with emission sources?
                try:
                    ambient_condition = self.getAmbientCondition(start_dt.timestamp())
                except Exception as error:
                    logger.warning(
                        "Couldn't load the ambient condition, so "
                        "default conditions are used:\n%s",
                        error,
                    )
                    ambient_condition = AmbientCondition()

                period_emissions = []

                # calculate emissions per source
                for mod_name, mod_obj in self.getModules().items():
                    logger.debug(mod_name)

                    # process() returns a list of tuples for each specific
                    # time interval (start_, end_)
                    for timestamp_, source_, emission_ in mod_obj.process(
                        start_dt,
                        end_dt,
                        source_names=source_names,
                        ambient_conditions=ambient_condition,
                        vertical_limit_m=vertical_limit_m,
                    ):

                        logger.debug(f"{mod_name}: {timestamp_}")

                        if emission_ is not None:
                            period_emissions.append((source_, emission_))
                        else:
                            period_emissions.append(
                                (
                                    source_,
                                    [Emission(default_emissions, default_emissions)],
                                )
                            )

                # calculate dispersion per model
                for (
                    dispersion_mod_name,
                    dispersion_mod_obj,
                ) in self.getDispersionModules().items():
                    logger.debug(f"{dispersion_mod_name}: {start_dt}")
                    dispersion_mod_obj.process(
                        start_dt, end_dt, period_emissions, ambient_condition
                    )

                # add a generic (zero) emission if the list is empty
                if len(period_emissions) == 0:
                    period_emissions.append(
                        (Source(), [Emission(default_emissions, default_emissions)])
                    )

                # add the emissions to the dict
                self._emissions[start_dt] = period_emissions

        except StopIteration as e:
            logger.info("Iteration stopped. %s", e)

        # execute endJob(..)
        logger.debug("Execute endJob(..)")
        for mod_name, mod_obj in self.getModules().items():
            mod_obj.endJob()

        # execute endJob(..) of dispersion modules
        logger.debug("Execute endJob(..) of dispersion modules")
        for (
            dispersion_mod_name,
            dispersion_mod_obj,
        ) in self.getDispersionModules().items():
            dispersion_mod_obj.endJob()

    def getModules(self):
        return self._source_modules

    def getDispersionModules(self):
        return self._dispersion_modules

    def getEmissions(self):
        return self._emissions

    def sortEmissionsByTime(self):
        # sort emissions by index (which is a timestamp)
        self._emissions = dict(
            sorted(iter(self.getEmissions().items()), key=lambda x: x[0])
        )

    def getDatabasePath(self):
        return self._database_path

    def getTimeSeries(self):
        dt = self._start_dt
        while dt >= self._start_dt and dt <= self._end_dt:
            yield dt

            dt += self._time_interval

    def get3DGrid(self):
        return self._grid
