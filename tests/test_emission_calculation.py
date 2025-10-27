import datetime

import pytest
from qgis.core import QgsMapLayer, QgsVectorLayer
from qgis.testing import QgisTestCase, start_app
from qgis.testing.mocked import get_iface

from open_alaqs.core.alaqsdblite import ProjectDatabase
from open_alaqs.core.modules.ModuleManager import OutputAnalysisModuleRegistry
from open_alaqs.openalaqsdialog import OpenAlaqsResultsAnalysis
from tests.utils import get_copy_path, get_data_path

start_app()


@pytest.fixture(scope="class")
def plugin_instance(request):
    print("\nINFO: Get plugin instance")
    from open_alaqs.openalaqs import OpenALAQS

    request.cls.plugin = OpenALAQS(get_iface())
    yield request.cls.plugin

    print(" [INFO] Tearing down plugin instance")
    request.cls.plugin.unload()


@pytest.fixture(scope="class")
def datasets_to_test(request) -> list:
    print("\nINFO: Get datasets to test...")
    request.cls.datasets = [
        {
            "title": "EHRD (Rotterdam, NL) Emission calculation test (CO)",
            "db_path": str(get_data_path("EHRD") / "EHRD.alaqs"),
            "inventory_path": str(get_data_path("EHRD") / "EHRD_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "CO",
            "study_start_date": datetime.datetime(2025, 12, 1, 6, 0),
            "study_end_date": datetime.datetime(2025, 12, 1, 7, 0),
            "vector_layer_path": str(
                get_copy_path(get_data_path("EHRD") / "vector_layer_co.gpkg")
            )
            + "|layername=output",
        },
        {
            "title": "EHRD (Rotterdam, NL) Emission calculation test (PM10)",
            "db_path": str(get_data_path("EHRD") / "EHRD.alaqs"),
            "inventory_path": str(get_data_path("EHRD") / "EHRD_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "PM10",
            "study_start_date": datetime.datetime(2025, 12, 1, 6, 0),
            "study_end_date": datetime.datetime(2025, 12, 1, 7, 0),
            "vector_layer_path": str(
                get_copy_path(get_data_path("EHRD") / "vector_layer_pm10.gpkg")
            )
            + "|layername=output",
        },
    ]


@pytest.mark.usefixtures("plugin_instance", "datasets_to_test")
class EmissionCalculationTestCase(QgisTestCase):
    """
    Subclass QgisTestCase to use checkLayersEqual()
    """

    def test_emission_calculation(self):
        print(" [INFO] Validating Emission Calculation...")
        for dataset in self.datasets:
            # Check parameter completeness
            assert list(dataset.keys()) == [
                "title",
                "db_path",
                "inventory_path",
                "module_name",
                "pollutant",
                "study_start_date",
                "study_end_date",
                "vector_layer_path",
            ]
            print(f" [INFO] Testing {dataset["title"]}...")

            # Store the database in-memory for future use
            project_database = ProjectDatabase()
            project_database.path = dataset["db_path"]

            inventory_path = dataset["inventory_path"]
            module_name = dataset["module_name"]

            OutputModule = OutputAnalysisModuleRegistry().get_module(module_name)
            assert OutputModule is not None

            # For now, we test from the dialog itself, but it
            # should be changed to a core implementation when it's ready
            dlg = OpenAlaqsResultsAnalysis(self.plugin.iface)
            dlg.result_file_path_changed(inventory_path)
            dlg.ui.result_file_path.setFilePath(inventory_path)
            dlg.ui.pollutants_names.setCurrentIndex(
                dlg.ui.pollutants_names.findText(dataset["pollutant"])
            )
            output_module, res = dlg.runOutputModule(OutputModule)

            assert str(output_module.getPollutant()) == dataset["pollutant"].lower()
            assert output_module.getTimeStart() == dataset["study_start_date"]
            assert output_module.getTimeEnd() == dataset["study_end_date"]

            result_tested = False
            # Checks depend on the module type
            if module_name == "EmissionsQGISVectorLayerOutputModule":
                assert isinstance(res, QgsMapLayer)
                assert isinstance(res, QgsVectorLayer)
                assert [field.name().lower() for field in res.fields()] == [
                    dataset["pollutant"].lower()
                ]

                layer = QgsVectorLayer(dataset["vector_layer_path"], "output", "ogr")
                assert layer.isValid()

                assert self.checkLayersEqual(
                    layer,
                    res,
                    use_asserts=True,  # Better for debugging in case of errors
                    compare={
                        "ignore_crs_check": True,  # Wrongly returns 4326 for the res layer, we'll check CRS later
                        "fields": {
                            "fid": "skip"
                        },  # Expected layer has a fid field that we can ignore
                        "unordered": True,  # Since no id, check that all values match, regardless of the ordering
                    },
                )
                assert layer.crs() == res.crs()

                result_tested = True

            assert result_tested
