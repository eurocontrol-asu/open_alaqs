import pytest
from qgis.testing import start_app
from qgis.testing.mocked import get_iface

from open_alaqs.core.alaqsdblite import ProjectDatabase
from open_alaqs.openalaqsdialog import OpenAlaqsResultsAnalysis
from tests.utils import get_data_path

start_app()


# Class-scoped fixture that initializes and provides the plugin instance to get the functionality
@pytest.fixture(scope="class")
def plugin_instance(request):

    print("\n[INFO] Get plugin instance")
    from open_alaqs.openalaqs import OpenALAQS

    # Create and attach plugin instance to test class
    request.cls.plugin = OpenALAQS(get_iface())
    yield request.cls.plugin

    # Clean up after tests
    print(" [INFO] Tearing down plugin instance")
    request.cls.plugin.unload()


# During refactoring, the service layer should produce identical configuration structures and default values
@pytest.mark.usefixtures("plugin_instance")
class TestGuiConfigurationValues:

    # Capture all values from _emission_calculation_configuration_widget.get_values()
    def test_capture_emission_calculation_config(self, plugin_instance):

        dlg = OpenAlaqsResultsAnalysis(plugin_instance.iface)
        inventory_path = str(
            get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs"
        )  # out file path

        # Initialize database and trigger dialog setup
        project_database = ProjectDatabase()
        project_database.path = str(get_data_path("AIRPORT_A") / "AIRPORT_A.alaqs")
        dlg.result_file_path_changed(inventory_path)  # Trigger UI update
        dlg.ui.result_file_path.setFilePath(inventory_path)  # Set file path in UI

        # Extract emission calculation config from widget
        em_config = dlg._emission_calculation_configuration_widget.get_values()

        # Print the returned results
        print(f"[INFO] Loaded emission calculation config: {em_config}")

        expected_keys = {
            "start_dt_inclusive",
            "end_dt_inclusive",
            "method",
            "should_apply_nox_corrections",
            "source_dynamics",
            "bffm2_ff_source",
            "time_interval",
            "vertical_limit_m",
            "receptor_points",
        }

        # Validate all keys present
        assert set(em_config.keys()) == expected_keys

        # Verify default values
        assert em_config["vertical_limit_m"] == 914.4
        assert not em_config[
            "should_apply_nox_corrections"
        ]  # default is set to False/off
        assert em_config["time_interval"] == "3600"  # TODO: check why this is a string

    # Check output modules configuration structure
    def test_capture_output_modules_config(self, plugin_instance):

        # Initialize dialog with test inventory
        dlg = OpenAlaqsResultsAnalysis(plugin_instance.iface)
        inventory_path = str(get_data_path("AIRPORT_A") / "AIRPORT_A_out.alaqs")
        dlg.result_file_path_changed(inventory_path)

        # Get output modules config
        gui_modules_config = dlg.getOutputModulesConfiguration()

        # Validate output modules config is not empty
        assert gui_modules_config is not None
        assert len(gui_modules_config) > 0

        # Validate each module has required structure
        for module_name, config in gui_modules_config.items():
            assert isinstance(module_name, str)
            assert isinstance(config, dict)
            assert len(config) > 0

        # Verify expected modules are present
        expected_modules = [
            "Emissions table",
            "Vector Layer",
            "Time Series",
        ]

        present_modules = set(gui_modules_config.keys())
        print(f" [INFO] Output modules: {present_modules}")

        for expected_module in expected_modules:
            assert (
                expected_module in present_modules
            ), f"Expected module '{expected_module}' not found in {present_modules}"

    # Check the pollutants list
    def test_capture_pollutants_list(self, plugin_instance):

        # Initialize dialog
        dlg = OpenAlaqsResultsAnalysis(plugin_instance.iface)

        # Expected pollutants list
        expected_pollutants = ["CO2", "CO", "HC", "NOx", "SOx", "PM10"]
        assert dlg._pollutants_list == expected_pollutants

    # Check the available source options
    def test_capture_source_module_names(self, plugin_instance):
        from open_alaqs.core.modules.ModuleManager import SourceModuleRegistry

        # Get registered source modules
        module_names = SourceModuleRegistry().get_module_names()
        print(f" [INFO] Source modules: {module_names}")

        # Expected source module types
        expected_modules = [
            "AreaSource",
            "MovementSource",
            "ParkingSource",
            "PointSource",
            "RoadwaySource",
        ]

        # Verify all modules registered
        assert set(module_names) == set(expected_modules)
