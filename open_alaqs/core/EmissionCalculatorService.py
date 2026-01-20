import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from open_alaqs.core.EmissionCalculation import EmissionCalculation
from open_alaqs.core.modules.ModuleManager import SourceModuleRegistry

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
            logger.warning("Grid is None, grid_bounds will not be set for segment clipping")

        # Add each module for the configuration
        for module_name in module_names:
            self._emission_calculation.add_source_module(
                module_name,
                {
                    "method": config.method,
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
                    "pollutants_list": self.supported_pollutants,
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
