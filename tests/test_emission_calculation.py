import datetime

import pytest
from qgis.core import QgsMapLayer, QgsVectorLayer
from qgis.testing import QgisTestCase, start_app
from qgis.testing.mocked import get_iface

from open_alaqs.core.alaqsdblite import ProjectDatabase
from open_alaqs.core.modules.ModuleManager import OutputAnalysisModuleRegistry
from open_alaqs.core.modules.TableViewWidgetOutputModule import ViewType
from open_alaqs.openalaqsdialog import OpenAlaqsResultsAnalysis
from tests.utils import (
    compare_text_files,
    get_data_path,
    get_tmp_path,
    get_vector_layer_path,
)

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

        ##################################
        # Test dataset using EHRD_out.alaqs
        ##################################
        {
            "title": "EHRD (Rotterdam, NL) Emission calculation test (CO), vector layer",
            "db_path": str(get_data_path("EHRD") / "EHRD.alaqs"),
            "inventory_path": str(get_data_path("EHRD") / "EHRD_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "CO",
            "study_start_date": "2025-12-01 06:00:00",
            "study_end_date": "2025-12-01 07:00:00",
            "expected_file_path": str(
                get_vector_layer_path("EHRD/vector_layer_co.gpkg", "output")
            ),
        },
        {
            "title": "EHRD (Rotterdam, NL) Emission calculation test (PM10), vector layer",
            "db_path": str(get_data_path("EHRD") / "EHRD.alaqs"),
            "inventory_path": str(get_data_path("EHRD") / "EHRD_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "PM10",
            "study_start_date": "2025-12-01 06:00:00",
            "study_end_date": "2025-12-01 07:00:00",
            "expected_file_path": str(
                get_vector_layer_path("EHRD/vector_layer_pm10.gpkg", "output")
            ),
        },
        {
            "title": "EHRD (Rotterdam, NL) Emission calculation test (CO), Emissions Table by Aggregation (CSV)",
            "db_path": str(get_data_path("EHRD") / "EHRD.alaqs"),
            "inventory_path": str(get_data_path("EHRD") / "EHRD_out.alaqs"),
            "module_name": "TableViewWidgetOutputModule",
            "pollutant": "CO",
            "study_start_date": "2025-12-01 06:00:00",
            "study_end_date": "2025-12-01 07:00:00",
            "expected_file_path": str(
                get_data_path("EHRD/EHRD_emissions_table_by_aggregation_co.csv")
            ),
        },
        {
            "title": "EHRD (Rotterdam, NL) Emission calculation test (PM10), Emissions Table by Grid Cell (CSV)",
            "db_path": str(get_data_path("EHRD") / "EHRD.alaqs"),
            "inventory_path": str(get_data_path("EHRD") / "EHRD_out.alaqs"),
            "module_name": "TableViewWidgetOutputModule",
            "pollutant": "PM10",
            "table_view_type": ViewType.BY_GRID_CELL,
            "study_start_date": "2025-12-01 06:00:00",
            "study_end_date": "2025-12-01 07:00:00",
            "expected_file_path": str(
                get_data_path("EHRD/EHRD_emissions_table_by_grid_cell_pm10.csv")
            ),
        },
        {
            "title": "EHRD (Rotterdam, NL) Emission calculation test for Movement Source (CO), vector layer",
            "db_path": str(get_data_path("EHRD") / "EHRD.alaqs"),
            "inventory_path": str(get_data_path("EHRD") / "EHRD_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "source_type": "MovementSource",
            "pollutant": "CO",
            "study_start_date": "2025-12-01 06:00:00",
            "study_end_date": "2025-12-01 07:00:00",
            "expected_file_path": str(
                get_vector_layer_path(
                    "EHRD/vector_layer_co_movement_source_centroids.gpkg", "output"
                )
            ),
        },

        ##################################
        # Test dataset using ANP_out.alaqs
        ##################################


        # Pollutants
        {
            "title": "ANP - CO emissions, vector layer",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "CO",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": str(
                get_vector_layer_path("ANP/ANP_vector_layer_co.gpkg", "output")
            ),
        },
        {
            "title": "ANP - PM10 emissions, vector layer",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "PM10",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": str(
                get_vector_layer_path("ANP/ANP_vector_layer_pm10.gpkg", "output")
            ),
        },
        {
            "title": "ANP - NOx emissions, vector layer",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "NOx",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": str(
                get_vector_layer_path("ANP/ANP_vector_layer_nox.gpkg", "output")
            ),
        },
        {
            "title": "ANP - HC emissions, vector layer",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "HC",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": str(
                get_vector_layer_path("ANP/ANP_vector_layer_hc.gpkg", "output")
            ),
        },
        {
            "title": "ANP - SOx emissions, vector layer",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "SOx",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": str(
                get_vector_layer_path("ANP/ANP_vector_layer_sox.gpkg", "output")
            ),
        },
        {
            "title": "ANP - CO2 emissions, vector layer",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "pollutant": "CO2",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": str(
                get_vector_layer_path("ANP/ANP_vector_layer_co2.gpkg", "output")
            ),
        },

        # TODO: Fix this test becuase it doesnt work
        # TableViewWidgetOutputModule
        # {
        #     "title": "ANP - CO emissions, Emissions Table by Aggregation (CSV)",
        #     "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
        #     "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
        #     "module_name": "TableViewWidgetOutputModule",
        #     "source_type": "all",
        #     "pollutant": "CO",
        #     "study_start_date": "2023-03-01 06:00:00",
        #     "study_end_date": "2023-03-01 22:00:00",
        #     "expected_file_path": str(
        #         get_data_path("ANP/ANP_emissions_table_by_aggregation_co.csv")
        #     ),
        # },

        # Source types
        {
            "title": "ANP - MovementSource, CO emissions",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "source_type": "MovementSource",
            "pollutant": "CO",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": str(
                get_vector_layer_path("ANP/ANP_vector_layer_co_movement_source.gpkg", "output")
            ),
        },
        {
            "title": "ANP - AreaSource, CO emissions",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "source_type": "AreaSourceWithTimeProfileModule",
            "pollutant": "CO",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": str(
                get_vector_layer_path("ANP/ANP_vector_layer_co_area_source.gpkg", "output")
            ),
        },
        {
            "title": "ANP - ParkingSource, CO emissions",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "source_type": "ParkingSourceWithTimeProfileModule",
            "pollutant": "CO",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": str(
                get_vector_layer_path("ANP/ANP_vector_layer_co_parking_source.gpkg", "output")
            ),
        },
        {
            "title": "ANP - PointSource, CO emissions",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "source_type": "PointSourceWithTimeProfileModule",
            "pollutant": "CO",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": str(
                get_vector_layer_path("ANP/ANP_vector_layer_co_point_source.gpkg", "output")
            ),
        },
        {
            "title": "ANP - RoadwaySource, CO emissions",
            "db_path": str(get_data_path("ANP") / "ANP.alaqs"),
            "inventory_path": str(get_data_path("ANP") / "ANP_out.alaqs"),
            "module_name": "EmissionsQGISVectorLayerOutputModule",
            "source_type": "RoadwaySourceWithTimeProfileModule",
            "pollutant": "CO",
            "study_start_date": "2023-03-01 06:00:00",
            "study_end_date": "2023-03-01 22:00:00",
            "expected_file_path": str(
                get_vector_layer_path("ANP/ANP_vector_layer_co_roadway_source.gpkg", "output")
            ),
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
            expected_parameters = [
                "title",
                "db_path",
                "inventory_path",
                "module_name",
                "pollutant",
                "study_start_date",
                "study_end_date",
                "expected_file_path",
            ]
            assert set(expected_parameters) - set(dataset.keys()) == set()
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

            if "source_type" in dataset:
                idx = dlg.ui.source_types.findText(dataset["source_type"])
                if idx != -1:
                    dlg.ui.source_types.setCurrentIndex(idx)
                    print(
                        f"[INFO] Emissions source type set to {dataset["source_type"]}"
                    )

            dlg.ui.pollutants_names.setCurrentIndex(
                dlg.ui.pollutants_names.findText(dataset["pollutant"])  # Set pollutant
            )
            if (
                module_name == "TableViewWidgetOutputModule"
                and "table_view_type" in dataset
            ):
                # Set view type
                # (Ugly! But no alternative until a proper core implementation is done)
                tab_bar = dlg.ui.output_modules_tab_widget.tabBar()
                for i in range(dlg.ui.output_modules_tab_widget.count()):
                    if tab_bar.tabText(i) == "Emissions table":
                        module_config_widget = dlg.ui.output_modules_tab_widget.widget(
                            i
                        ).widget()
                        combobox = module_config_widget.get_widget("view_type")
                        idx = combobox.findText(dataset["table_view_type"].value)
                        combobox.setCurrentIndex(idx)
                        print(
                            f"[INFO] Emissions table view type set to {combobox.currentText()}"
                        )
                        break

            output_module, res = dlg.runOutputModule(OutputModule)

            result_tested = False
            # Checks depend on the module type
            if module_name == "EmissionsQGISVectorLayerOutputModule":
                assert str(output_module.getPollutant()) == dataset["pollutant"].lower()
                assert output_module.getTimeStart() == datetime.datetime.fromisoformat(
                    dataset["study_start_date"]
                )
                assert output_module.getTimeEnd() == datetime.datetime.fromisoformat(
                    dataset["study_end_date"]
                )

                assert isinstance(res, QgsMapLayer)
                assert isinstance(res, QgsVectorLayer)

                layer = QgsVectorLayer(dataset["expected_file_path"], "output", "ogr")
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

            elif module_name == "TableViewWidgetOutputModule":
                csv_path = get_tmp_path("emission_calculation_output.csv")
                assert not csv_path.exists()

                output_module.export_to_csv(csv_path)

                assert csv_path.exists()
                compare_text_files(dataset["expected_file_path"], str(csv_path))

                result_tested = True

            assert result_tested
