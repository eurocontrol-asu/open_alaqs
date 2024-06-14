from typing import TypeVar, cast

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.DispersionModule import DispersionModule
from open_alaqs.core.interfaces.OutputModule import OutputModule
from open_alaqs.core.interfaces.SourceModule import SourceModule
from open_alaqs.core.modules.AreaSourceModule import AreaSourceWithTimeProfileModule
from open_alaqs.core.modules.AUSTAL2000OutputModule import AUSTAL2000DispersionModule
from open_alaqs.core.modules.ConcentrationsQGISVectorLayerOutputModule import (
    QGISVectorLayerDispersionModule,
)
from open_alaqs.core.modules.EmissionsQGISVectorLayerOutputModule import (
    EmissionsQGISVectorLayerOutputModule,
)
from open_alaqs.core.modules.MovementSourceModule import MovementSourceModule
from open_alaqs.core.modules.ParkingSourceModule import (
    ParkingSourceWithTimeProfileModule,
)
from open_alaqs.core.modules.PointSourceModule import PointSourceWithTimeProfileModule
from open_alaqs.core.modules.RoadwaySourceModule import (
    RoadwaySourceWithTimeProfileModule,
)
from open_alaqs.core.modules.TableViewDispersionOutputModule import (
    TableViewDispersionModule,
)
from open_alaqs.core.modules.TableViewWidgetOutputModule import (
    TableViewWidgetOutputModule,
)
from open_alaqs.core.modules.TimeSeriesDispersionOutputModule import (
    TimeSeriesDispersionModule,
)
from open_alaqs.core.modules.TimeSeriesWidgetOutputModule import (
    TimeSeriesWidgetOutputModule,
)
from open_alaqs.core.tools.Singleton import Singleton

logger = get_logger(__name__)


class ModuleRegistry(metaclass=Singleton):
    ModuleType = TypeVar("ModuleType")
    module_class = object

    def __init__(self) -> None:
        self._registry: dict[str, ModuleRegistry.ModuleType] = {}

    def register(self, module: ModuleType) -> None:
        if not issubclass(module, self.module_class):
            raise Exception(
                f"The provided `{module=}` must be a subclass of `{self.module_class.__name__}`!"
            )

        module_name = module.getModuleName()

        self._registry[module_name] = module

    def get_module_names(self) -> list[str]:
        return list(self._registry.keys())

    def get_module(self, name: str) -> ModuleType:
        return self._registry.get(name, None)


class SourceModuleRegistry(ModuleRegistry):
    module_type = SourceModule

    def get_module(self, name: str) -> type[SourceModule]:
        return cast(type[SourceModule], super().get_module(name))


class OutputModuleRegistry(ModuleRegistry):
    module_type = OutputModule

    def get_module(self, name: str) -> type[OutputModule]:
        return cast(type[OutputModule], super().get_module(name))


class OutputAnalysisModuleRegistry(ModuleRegistry):
    pass


class OutputDispersionModuleRegistry(ModuleRegistry):
    pass


class DispersionModuleRegistry(ModuleRegistry):
    module_type = OutputModule

    def get_module(self, name: str) -> type[DispersionModule]:
        return cast(type[DispersionModule], super().get_module(name))


source_module_registry = SourceModuleRegistry()
source_module_registry.register(AreaSourceWithTimeProfileModule)
source_module_registry.register(MovementSourceModule)
source_module_registry.register(ParkingSourceWithTimeProfileModule)
source_module_registry.register(PointSourceWithTimeProfileModule)
source_module_registry.register(RoadwaySourceWithTimeProfileModule)


output_analysis_module_registry = OutputAnalysisModuleRegistry()
output_analysis_module_registry.register(TableViewWidgetOutputModule)
output_analysis_module_registry.register(TimeSeriesWidgetOutputModule)
output_analysis_module_registry.register(EmissionsQGISVectorLayerOutputModule)

output_dispersion_module_registry = OutputDispersionModuleRegistry()
output_dispersion_module_registry.register(QGISVectorLayerDispersionModule)
output_dispersion_module_registry.register(TableViewDispersionModule)
output_dispersion_module_registry.register(TimeSeriesDispersionModule)

dispersion_module_registry = DispersionModuleRegistry()
dispersion_module_registry.register(AUSTAL2000DispersionModule)
