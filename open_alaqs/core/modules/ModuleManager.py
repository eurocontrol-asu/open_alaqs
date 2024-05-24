import importlib.machinery
import importlib.util
import inspect
from collections import OrderedDict
from pathlib import Path
from typing import Type, TypeVar, cast

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.DispersionModule import DispersionModule
from open_alaqs.core.interfaces.OutputModule import OutputModule
from open_alaqs.core.interfaces.SourceModule import SourceModule
from open_alaqs.core.modules.AreaSourceModule import AreaSourceWithTimeProfileModule
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


class ModuleManager(metaclass=Singleton):
    def __init__(self, moduletype):
        self._modules = OrderedDict()
        self._module_type = moduletype

        self.loadModules()

    def getModuleType(self):
        return self._module_type

    # load all modules in current directory
    def loadModules(self):
        for filename in Path(__file__).resolve().parent.glob("*.py"):
            loader = importlib.machinery.SourceFileLoader(
                filename.stem.lower(), str(filename)
            )
            spec = importlib.util.spec_from_loader(loader.name, loader)
            module = importlib.util.module_from_spec(spec)
            loader.exec_module(module)

            for _name, obj in inspect.getmembers(module):

                # include only classes
                if not inspect.isclass(obj):
                    continue

                # exclude classes that are not defined in the inspected module,
                # i.e. without imported classes
                if not module.__name__ == obj.__module__:
                    continue

                # exclude the plugin manager
                if module.__name__ == self.__class__.__name__:
                    continue

                # exclude classes that are subclasses of a particular class
                # (e.g. 'SourceModule')
                if not issubclass(obj, self.getModuleType()):
                    continue

                # add modules to the list of existing modules
                if _name not in self._modules:
                    self.addModule(obj.getModuleName(), obj)

    def addModule(self, name, classinfo):
        if name in self._modules:
            logger.warning(
                "Already found a module with name '%s' and class "
                "'%s'. Overwriting existing with name '%s' and "
                "class '%s'." % (name, self._modules[name], name, str(classinfo))
            )
        self._modules[name] = classinfo

    def getModulesByType(self, typename):
        return [
            x for x in iter(self._modules.items()) if x[1].__name__ == typename.__name__
        ]

    def getModulesByName(self, name):
        return [x for x in iter(self._modules.items()) if x[1].getModuleName() == name]

    def getModuleByName(self, name):
        matched_ = [
            x for x in iter(self._modules.items()) if x[1].getModuleName() == name
        ]
        if len(matched_):
            return matched_[0][1]
        return None

    def hasModule(self, name):
        for x in iter(self._modules.items()):
            if x[1].getModuleName() == name:
                return True
        return False

    def getModules(self):
        return self._modules

    def getModuleNames(self):
        return [module_name_ for module_name_ in self.getModules()]

    def getModuleInstances(self):
        instances_ = OrderedDict()
        for module_name_, obj_ in self.getModules().items():
            instances_[module_name_] = obj_()
        return instances_


class DispersionModuleManager(ModuleManager, metaclass=Singleton):
    def __init__(self):
        ModuleManager.__init__(self, DispersionModule)


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
    pass


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
