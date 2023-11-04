import inspect
import os
import pkgutil
from collections import OrderedDict

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.interfaces.DispersionModule import DispersionModule
from open_alaqs.alaqs_core.interfaces.OutputModule import OutputModule
from open_alaqs.alaqs_core.tools.Singleton import Singleton
from open_alaqs.alaqs_core.interfaces.SourceModule import SourceModule

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
                [os.path.abspath(os.path.dirname(__file__))]):
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
            logger.warning("Already found a module with name '%s' and class "
                           "'%s'. Overwriting existing with name '%s' and "
                           "class '%s'."
                           % (name, self._modules[name], name, str(classinfo)))
        self._modules[name] = classinfo

    def getModulesByType(self, typename):
        return [x for x in iter(self._modules.items()) if
                x[1].__name__ == typename.__name__]

    def getModulesByName(self, name):
        return [x for x in iter(self._modules.items()) if
                x[1].getModuleName() == name]

    def getModuleByName(self, name):
        matched_ = [x for x in iter(self._modules.items()) if
                    x[1].getModuleName() == name]
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


# if __name__ == "__main__":
#     # logging.getLogger().setLevel(logging.INFO)
#     # # create console handler and set level to debug
#     # ch = logging.StreamHandler()
#     # if loaded_color_logger:
#     #     ch= RainbowLoggingHandler(sys.stderr, color_funcName=('black', 'yellow', True))
#     #
#     # ch.setLevel(logging.DEBUG)
#     # # create formatter
#     # formatter = logging.Formatter('%(asctime)s:%(levelname)s - %(message)s')
#     # # add formatter to ch
#     # ch.setFormatter(formatter)
#     # # add ch to logger
#     # logger.addHandler(ch)
#
#     from interfaces.Movement import MovementStore, MovementDatabase #SS
#
#     mm = SourceModuleManager()
#     module_name = "MovementSource"
#
#     path_to_database = os.path.join("..","..","example/CAEPport_training/", "caepport_out.alaqs")
#     ms2 = MovementStore(path_to_database, debug=False)
#     MovementDatabase().__init__
#     mdb2 = MovementDatabase(path_to_database)
#
#     # for module_name_, module_obj_ in mm.getModulesByName(module_name):
#     #     mod_ = None
#     #     #instantiate module to get access to the sources
#     #     em_config = {"database_path" : path_to_database}
#     #
#     #     # if module_name == "MovementSource":
#     #         # store_ = MovementStore(inventory_path, debug=False)#MovementStore
#     #         # module_obj_.setStore(module_obj_.store_)#MovementStoreModule
#     #         # em_config.update(self._emission_calculation_configuration_widget.getValues())
#     #     mod_ = module_obj_(em_config)
#     #     MS = mod_.loadSources()
#     #     S1 = mod_.getStore()
#     #     print "Which module_obj DatabasePath ? %s"%mod_.getDatabasePath()
#     #     print "Which STORE ? %s"%mod_.getStore()._db_path
#     #     mod_.setDatabasePath('..\\..\\example/DHC6_DEP.alaqs')
#     #     print "Which module_obj DatabasePath ? %s"%mod_.getDatabasePath()
#     #     mod_.setStore(MovementStore(mod_.getDatabasePath(), debug=False))#MovementStore)
#     #     print "Which STORE ? %s"%mod_.getStore()._db_path
#     #
#     #     S2 = mod_.getStore()
#
#
#     #
#     # if os.path.exists(path_to_database):
#     #
#     #
#     #
#     #     for module_name_, obj_ in mm.getModuleInstances().iteritems():
#     #         if module_name_ == "MovementSource":
#     #             break
#     #     print "Module name: %s, Instance: %s" % (module_name_, obj_)
#     #     # logger.info("Module name: %s, Instance: %s" % (module_name_, obj_))
#     #     obj_.setDatabasePath(path_to_database)
#     #
#     #     print "Which module_obj DatabasePath ? %s"%obj_.getDatabasePath()
#     #     obj_.setStore(MovementStore(obj_.getDatabasePath(), debug=False))
#     #
#     #
#     #     print "\t Which STORE ? %s"%obj_.getStore()._db_path
#     #     print "\t Which STORE DB ? %s"%obj_.getStore()._movement_db._db_path
#     #     obj_.loadSources()
#     #     print "\t Source Names: %s"%obj_.getSourceNames()
#     #
#     #     print "** Reseting Store **"
#     #     obj_.resetStore()
#     #     print "\t Which STORE ? %s"%obj_.getStore()
#     #     obj_.loadSources()
#     #     print "\t Source Names: %s"%obj_.getSourceNames()
#     #
#     #     # # NEW path_to_database
#     #     print "** Updating Store **"
#     #     mm = SourceModuleManager()
#     #     obj_ = None
#     #     # for source_name, source in obj_.getStore().getObjects().items():
#     #     #         obj_.getStore().removeObject(source_name)
#     #
#     #     for module_name_, obj_ in mm.getModuleInstances().iteritems():
#     #         if module_name_ == "MovementSource":
#     #             break
#     #     path_to_database = os.path.join("..",'..',"example/", "DHC6_DEP.alaqs")
#     #     if os.path.exists(path_to_database):
#     #         store = MovementStore(path_to_database, debug=False)
#     #         obj_.setDatabasePath(path_to_database)
#     #         print "Which module_obj DatabasePath ? %s"%obj_.getDatabasePath()
#     #
#     #         obj_.setStore(MovementStore(obj_.getDatabasePath()))
#     #         print "\t Which STORE ? %s"%obj_.getStore()._db_path
#     #         print "\t Which STORE DB ? %s"%obj_.getStore()._movement_db._db_path
#     #
#     #         gS = obj_.getStore()
#     #         obj_.loadSources()
#     #
#     #         print "\t Source Names: %s"%obj_.getSourceNames()
#     #     else:
#     #         print "Database '%s' does not exist."%path_to_database
#     #
#     # else:
#     #     print "Database '%s' does not exist."%path_to_database
