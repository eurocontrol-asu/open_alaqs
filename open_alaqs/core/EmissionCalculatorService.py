import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from open_alaqs.core.EmissionCalculation import EmissionCalculation
from open_alaqs.core.modules.ModuleManager import SourceModuleRegistry
from open_alaqs.core.tools import surface_layer_atmosphere as _sla

logger = logging.getLogger(__name__)


@dataclass
class EmissionCalculationConfig:
    """Data class for the emission calculator config"""

    # Required paths
    db_path: str

    # Required time parameters
    start_dt_inclusive: datetime
    end_dt_inclusive: datetime
    time_interval: timedelta  # in seconds (60, 300, 600, 900, 1200, 1800, 3600)

    # Required calculation parameters
    pollutant: str  # CO2, CO, HC, NOx, SOx, PM10
    method: str = "bymode"  # bymode, BFFM2
    # Fuel-flow interpolation method used inside BFFM2.
    #   "twin_quadratic"  — ALAQS parabolic fit (default, backward-compatible)
    #   "linear"   — ICAO/CAEP14 piecewise-linear between EEDB breakpoints

    # MEEM version for the nvPM EI. Only "v1" (ICAO CAEP/13-MDG, CAEP14 v14
    # MEEM_V1 tab) is used: MEEM V2 (CAEP14 v12+, meem_v2.py) is implemented
    # but not used, its adoption is to be decided; MovementSourceModule logs a
    # warning and runs V1 for any other value.
    meem_version: str = "v1"

    # BFFM2 fuel-flow source — what FF to use when the segment has no explicit
    # fuel_flow_kgm (built-in ANP-derived profiles).
    #   "trajectory" (default): derive FF from the segment's power_setting via
    #       twin_quadratic_fit_method. Uses the ANP sub-mode thrust variation
    #       (ratio of THR_SET in lb to Max Sea Level Static Thrust in lb per
    #       Aircraft.csv). BFFM2 EIs are then log-log interpolated on the EEDB
    #       curve at that FF. Matches the CAEP14 v14 BFFM2 workflow.
    #   "mode_anchor":        use the EEDB anchor FF for the segment's mode
    #       (TX→0.091, AP→0.244, CL→0.71, TO→0.861 kg/s/eng for LEAP-1A).
    #       Disables sub-mode resolution but still applies BFFM2 atmospheric
    #       and humidity corrections. Matches the CAEP14 v14 LTO-mode workflow
    #       with ambient corrections applied.
    # Only affects BFFM2; has no effect when method == "bymode" or when an
    # explicit fuel_flow_kgm is supplied by the trajectory.
    bffm2_ff_source: str = "trajectory"
    # Ambient conditions aloft (core/tools/surface_layer_atmosphere.py): "standard_lapse"
    # (default, ISA lapse rate from the hourly row's 2 m temperature and station pressure),
    # "surface_layer" (AUSTAL's boundary-layer temperature profile) or "ground_held" (the
    # hourly row at every height, the 5.4.0 ambient conditions). The site
    # parameters default to those of the configured AUSTAL module, else to the AUSTAL
    # defaults of surface_layer_atmosphere.site_parameters (z0 0.1 m, the TA Luft value for
    # airports; d0 6 z0; ha 10 m + d0). None, "" or 0 derive from z0.
    atmosphere_model: str = "standard_lapse"
    atmosphere_z0_m: Optional[float] = None
    atmosphere_d0_m: Optional[float] = None
    atmosphere_ha_m: Optional[float] = None

    # Optional source filtering
    source_type: str = "all"
    source_names: List[str] = field(default_factory=list)

    # Optional calculation parameters
    vertical_limit_m: float = 914.4  # meters
    should_apply_nox_corrections: bool = False
    source_dynamics: str = "none"  # "none", "default", "smooth & shift"

    # Optional grid configuration
    grid_config: Optional[Dict[str, Any]] = None

    # Optional receptor points
    receptor_points: Optional[Any] = None

    # Optional module configurations
    dispersion_modules_config: Optional[Dict[str, Any]] = None
    output_modules_config: Optional[Dict[str, Any]] = None


@dataclass
class EmissionCalculationResult:
    """Result from the emissions calculator"""

    success: bool
    emissions_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Any] = None
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class EmissionCalculatorService:
    """Service class that handles all business logic for emission calculations"""

    def __init__(self):

        # Initialise the calculator and the warnings list
        self._emission_calculation: Optional[EmissionCalculation] = None
        self._warnings: List[str] = []

        # Supported pollutants for validation
        self.supported_pollutants = ["CO2", "CO", "HC", "NOx", "SOx", "PM10"]
        self.supported_methods = ["bymode", "BFFM2"]

    def validate_config(
        self, config: EmissionCalculationConfig
    ) -> tuple[bool, Optional[str]]:
        """
        Validate the emission calculation configuration.

        :param config: EmissionCalculationConfig instance
        :return: Tuple of (is_valid, error_message)
        """
        self._warnings = []

        try:
            # Check required fields
            if not config.db_path:
                return False, "Database path is required"

            if config.start_dt_inclusive >= config.end_dt_inclusive:
                return False, "Start datetime must be before end datetime"

            if config.time_interval.total_seconds() <= 0:
                return False, "Time interval must be positive"

            if config.pollutant not in self.supported_pollutants:
                return (
                    False,
                    f"Invalid pollutant: {config.pollutant}. Supported: {self.supported_pollutants}",
                )

            if config.method not in self.supported_methods:
                return (
                    False,
                    f"Invalid method: {config.method}. Supported: {self.supported_methods}",
                )

            if config.grid_config is None:
                return False, "Grid configuration is required"

            # Validation warnings (non-fatal)
            if config.should_apply_nox_corrections and config.method == "BFFM2":
                self._warnings.append(
                    "NOx corrections are not applicable with BFFM2 method"
                )

            return True, None

        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def calculate_emissions(
        self, config: EmissionCalculationConfig
    ) -> EmissionCalculationResult:
        """
        Main method to calculate emissions based on configuration.

        :param config: EmissionCalculationConfig instance
        :return: EmissionCalculationResult with results and status
        """
        # Validate configuration
        is_valid, error_msg = self.validate_config(config)
        if not is_valid:
            logger.error(f"Configuration validation failed: {error_msg}")
            return EmissionCalculationResult(success=False, error_message=error_msg)

        # Log configuration
        # self._log_configuration(config)

        try:
            # Initialize emission calculation
            self._emission_calculation = self._initialize_calculation(config)

            # Add source modules
            self._add_source_modules(config)

            # Add dispersion modules
            self._add_dispersion_modules(config)

            # Run calculation
            self._run_calculation(config)

            # Get emissions data
            emissions_data = self._emission_calculation.getEmissions()

            return EmissionCalculationResult(
                success=True,
                emissions_data=emissions_data,
                warnings=self._warnings.copy(),
                metadata=self._get_metadata(config),
            )

        except Exception as e:
            logger.error(f"Emission calculation failed: {str(e)}", exc_info=True)
            return EmissionCalculationResult(
                success=False, error_message=str(e), warnings=self._warnings.copy()
            )

    def _log_configuration(self, config: EmissionCalculationConfig) -> None:
        """Log the configuration for debugging and verification"""

        logger.info("EMISSION CALCULATION CONFIGURATION")
        logger.info(f"Database Path: {config.db_path}")
        logger.info(f"Start DateTime (inclusive): {config.start_dt_inclusive}")
        logger.info(f"End DateTime (inclusive): {config.end_dt_inclusive}")
        logger.info(f"Time Interval: {config.time_interval.total_seconds()} seconds")
        logger.info(f"Pollutant: {config.pollutant}")
        logger.info(f"Method: {config.method}")
        logger.info(f"Source Type: {config.source_type}")
        logger.info(f"Source Names: {config.source_names}")
        logger.info(f"Vertical Limit: {config.vertical_limit_m} m")
        logger.info(f"Apply NOx Corrections: {config.should_apply_nox_corrections}")
        logger.info(f"Source Dynamics: {config.source_dynamics}")
        logger.info(f"Grid Config: {config.grid_config}")
        has_receptors = (
            config.receptor_points is not None and len(config.receptor_points) > 0
        )
        logger.info(f"Has Receptor Points: {has_receptors}")

    def _initialize_calculation(
        self, config: EmissionCalculationConfig
    ) -> EmissionCalculation:
        """Initialize the emission calculation object."""
        return EmissionCalculation(
            db_path=config.db_path,
            grid_config=config.grid_config,
            start_dt=config.start_dt_inclusive,
            end_dt=config.end_dt_inclusive,
            time_interval=config.time_interval,
        )

    def _add_source_modules(self, config: EmissionCalculationConfig) -> None:
        """Add source modules based on configuration."""
        if self._emission_calculation is None:
            raise ValueError("Emission calculation not initialized")

        # Map user-friendly source type names to actual module names
        source_type_mapping = {
            "all": "all",
            "area": "AreaSource",
            "areasource": "AreaSource",
            "movement": "MovementSource",
            "movements": "MovementSource",
            "movementsource": "MovementSource",
            "parking": "ParkingSource",
            "parkingsource": "ParkingSource",
            "point": "PointSource",
            "pointsource": "PointSource",
            "roadway": "RoadwaySource",
            "roadwaysource": "RoadwaySource",
        }

        # Determine which modules to add
        source_type_lower = config.source_type.lower()
        if source_type_lower == "all":
            module_names = SourceModuleRegistry().get_module_names()
        else:
            # Look up in mapping, fallback to the original value
            module_name = source_type_mapping.get(source_type_lower, config.source_type)
            module_names = [module_name]

        # Get reference altitude from grid config
        reference_altitude = config.grid_config.get("reference_altitude", 0.0)

        # Get grid bounds from the 3D grid
        grid_bounds = None
        if self._emission_calculation._grid is not None:
            grid_bounds = self._emission_calculation._grid.getGridBounds()
            logger.info(f"Grid bounds calculated: {grid_bounds}")
        else:
            logger.warning(
                "Grid is None, grid_bounds will not be set for segment clipping"
            )

        # Site parameters of the boundary-layer formulas (atmosphere_model): explicit values,
        # else those of a configured dispersion module (AUSTAL), else the AUSTAL defaults.
        # A module setting of 0 (the spin boxes cannot be empty) means "derive from z0", as
        # in the AUSTAL module itself (site_parameters_from_settings).
        _site = {
            "atmosphere_z0_m": config.atmosphere_z0_m,
            "atmosphere_d0_m": config.atmosphere_d0_m,
            "atmosphere_ha_m": config.atmosphere_ha_m,
        }
        for _mod_cfg in (config.dispersion_modules_config or {}).values():
            if not isinstance(_mod_cfg, dict) or not any(
                _k in _mod_cfg
                for _k in (
                    "roughness_length_m",
                    "displacement_height_m",
                    "anemometer_height_m",
                )
            ):
                continue
            _mod_site = dict(
                zip(
                    ("atmosphere_z0_m", "atmosphere_d0_m", "atmosphere_ha_m"),
                    _sla.site_parameters_from_settings(
                        _mod_cfg.get("roughness_length_m"),
                        _mod_cfg.get("displacement_height_m"),
                        _mod_cfg.get("anemometer_height_m"),
                    ),
                )
            )
            for _key in _site:
                if _site[_key] is None:
                    _site[_key] = _mod_site[_key]

        # Add each module for the configuration
        for module_name in module_names:
            self._emission_calculation.add_source_module(
                module_name,
                {
                    "method": config.method,
                    "meem_version": config.meem_version,
                    "bffm2_ff_source": config.bffm2_ff_source,
                    "atmosphere_model": config.atmosphere_model,
                    **_site,
                    "should_apply_nox_corrections": config.should_apply_nox_corrections,
                    "source_dynamics": config.source_dynamics,
                    "reference_altitude": reference_altitude,
                    "show_progress": False,
                    "receptors": config.receptor_points,
                    "grid_bounds": grid_bounds,
                },
            )
            logger.info(f"Added source module: {module_name}")

    def _add_dispersion_modules(self, config: EmissionCalculationConfig) -> None:
        """Add dispersion modules based on configuration."""

        if self._emission_calculation is None:
            raise ValueError("Emission calculation not initialized")

        if config.dispersion_modules_config is None:
            return

        for module_name, module_config in config.dispersion_modules_config.items():
            if not module_config.get("is_enabled", False):
                continue

            # Create a copy to avoid mutating the original config
            dm_config = module_config.copy()
            dm_config.update(
                {
                    "pollutant": config.pollutant,
                    "pollutants_list": [config.pollutant],
                    "receptors": config.receptor_points,
                    "grid": self._emission_calculation.get3DGrid(),
                }
            )

            self._emission_calculation.add_dispersion_modules([module_name], dm_config)
            logger.info(f"Added dispersion module: {module_name}")

    def _run_calculation(self, config: EmissionCalculationConfig) -> None:
        """Run the emission calculation."""
        if self._emission_calculation is None:
            raise ValueError("Emission calculation not initialized")

        logger.info("Starting emission calculation...")

        # Use source_names if provided, otherwise default to ["all"]
        source_names = config.source_names if config.source_names else ["all"]

        # Run without GUI progress bar (headless mode)
        self._emission_calculation.run(
            source_names=source_names,
            vertical_limit_m=config.vertical_limit_m,
            show_progress=False,
        )

        self._emission_calculation.sortEmissionsByTime()

        logger.info("Emission calculation completed successfully")

    def _get_metadata(self, config: EmissionCalculationConfig) -> Dict[str, Any]:
        """Extract metadata from the calculation."""
        return {
            "pollutant": config.pollutant,
            "method": config.method,
            "source_type": config.source_type,
            "start_time": config.start_dt_inclusive.isoformat(),
            "end_time": config.end_dt_inclusive.isoformat(),
            "time_interval_seconds": config.time_interval.total_seconds(),
        }

    def get_calculation(self) -> Optional[EmissionCalculation]:
        """Get the current emission calculation object."""
        return self._emission_calculation

    def get_emissions(self) -> Optional[Dict[str, Any]]:
        """Get the calculated emissions data."""
        if self._emission_calculation is None:
            return None
        return self._emission_calculation.getEmissions()

    def get_3d_grid(self):
        """Get the 3D grid from the calculation."""
        if self._emission_calculation is None:
            return None
        return self._emission_calculation.get3DGrid()

    def get_database_path(self) -> Optional[str]:
        """Get the database path from the calculation."""
        if self._emission_calculation is None:
            return None
        return self._emission_calculation.getDatabasePath()
