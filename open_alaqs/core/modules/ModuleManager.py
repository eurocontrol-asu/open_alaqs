import inspect
import os
import pkgutil
from collections import OrderedDict

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.DispersionModule import DispersionModule
from open_alaqs.core.interfaces.OutputModule import OutputModule
from open_alaqs.core.interfaces.SourceModule import SourceModule
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
        for loader, name, _ in pkgutil.walk_packages(
            [os.path.abspath(os.path.dirname(__file__))]
        ):
            module = loader.find_module(name).load_module(name)
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


class SourceModuleManager(ModuleManager, metaclass=Singleton):
    def __init__(self):
        ModuleManager.__init__(self, SourceModule)


class OutputModuleManager(ModuleManager, metaclass=Singleton):
    def __init__(self):
        ModuleManager.__init__(self, OutputModule)


class DispersionModuleManager(ModuleManager, metaclass=Singleton):
    def __init__(self):
        ModuleManager.__init__(self, DispersionModule)
