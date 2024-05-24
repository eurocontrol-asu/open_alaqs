from typing import Type, TypeVar, cast

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.DispersionModule import DispersionModule
from open_alaqs.core.interfaces.OutputModule import OutputModule
from open_alaqs.core.interfaces.SourceModule import SourceModule
from open_alaqs.core.modules.AreaSourceModule import AreaSourceWithTimeProfileModule
from open_alaqs.core.modules.AUSTAL2000OutputModule import AUSTAL2000DispersionModule
from open_alaqs.core.modules.ConcentrationsQGISVectorLayerOutputModule import (
    QGISVectorLayerDispersionModule,
)
from open_alaqs.core.modules.CSVOutputModule import CSVOutputModule
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
from open_alaqs.core.modules.SQLiteOutputModule import SQLiteOutputModule
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

    def __init__(self) -> None:
        self._registry: dict[str, ModuleRegistry.ModuleType] = {}

    def register(self, source_module: Type[ModuleType]) -> None:
        module_name = source_module.getModuleName()

        self._registry[module_name] = source_module

    def get_module_names(self) -> list[str]:
        return list(self._registry.keys())

    def get_module(self, name: str) -> Type[ModuleType]:
        return self._registry.get(name, None)


class EmissionSourceModuleRegistry(ModuleRegistry):
    def register(self, module: SourceModule) -> None:
        if not issubclass(cast(type[SourceModule], module), SourceModule):
            raise Exception(
                f"The provided `{module=}` must be a subclass of `SourceModule`!"
            )

        super().register(module)

    def get_module(self, name: str) -> type[SourceModule]:
        return cast(type[SourceModule], super().get_module(name))


class OutputModuleRegistry(ModuleRegistry):
    def register(self, module: ModuleRegistry.ModuleType) -> None:
        if not issubclass(cast(type[OutputModule], module), OutputModule):
            raise Exception(
                f"The provided `{module=}` must be a subclass of `OutputModule`!"
            )

        super().register(module)

    def get_module(self, name: str) -> type[OutputModule]:
        return cast(type[OutputModule], super().get_module(name))


class DispersionModuleRegistry(ModuleRegistry):
    def register(self, module: ModuleRegistry.ModuleType) -> None:
        if not issubclass(cast(type[DispersionModule], module), DispersionModule):
            raise Exception(
                f"The provided `{module=}` must be a subclass of `DispersionModule`!"
            )

        super().register(module)

    def get_module(self, name: str) -> type[DispersionModule]:
        return cast(type[DispersionModule], super().get_module(name))


emission_source_module_registry = EmissionSourceModuleRegistry()
emission_source_module_registry.register(AreaSourceWithTimeProfileModule)
emission_source_module_registry.register(MovementSourceModule)
emission_source_module_registry.register(ParkingSourceWithTimeProfileModule)
emission_source_module_registry.register(PointSourceWithTimeProfileModule)
emission_source_module_registry.register(RoadwaySourceWithTimeProfileModule)


output_module_registry = OutputModuleRegistry()
output_module_registry.register(CSVOutputModule)
output_module_registry.register(EmissionsQGISVectorLayerOutputModule)
output_module_registry.register(QGISVectorLayerDispersionModule)
output_module_registry.register(SQLiteOutputModule)
output_module_registry.register(TableViewDispersionModule)
output_module_registry.register(TableViewWidgetOutputModule)
output_module_registry.register(TimeSeriesDispersionModule)
output_module_registry.register(TimeSeriesWidgetOutputModule)

dispersion_module_registry = DispersionModuleRegistry()
dispersion_module_registry.register(AUSTAL2000DispersionModule)
