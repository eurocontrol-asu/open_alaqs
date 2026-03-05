import pytest
from qgis.testing import start_app
from qgis.testing.mocked import get_iface

from open_alaqs.core.alaqsdblite import ProjectDatabase
from open_alaqs.core.tools.ads_b import validate_adsb_file
from open_alaqs.core.tools.sql_interface import db_delete_records
from tests.utils import get_copy_path, get_data_path

start_app()


@pytest.fixture(scope="module")
def plugin_instance():
    print("\nINFO: Get plugin instance")
    from open_alaqs.openalaqs import OpenALAQS

    plugin = OpenALAQS(get_iface())
    yield plugin

    print(" [INFO] Tearing down plugin instance")
    plugin.unload()


def test_ads_b_validation(plugin_instance):
    print(" [INFO] Validating ADS-B data validation...")

    project_database = ProjectDatabase()

    db_path = str(get_copy_path(get_data_path("EHRD") / "EHRD_out.alaqs"))
    project_database.path = db_path

    # Invalid data 1 (Missing mandatory fields in header)
    ads_b_file_invalid = str(
        get_copy_path(get_data_path("EHRD/ADS-B") / "EHRD_ads_b_data_invalid_1.csv")
    )
    res, msg = validate_adsb_file(ads_b_file_invalid)
    assert not res

    # Invalid data 2 (NULL values in mandatory fields)
    ads_b_file_invalid = str(
        get_copy_path(get_data_path("EHRD/ADS-B") / "EHRD_ads_b_data_invalid_2.csv")
    )
    res, msg = validate_adsb_file(ads_b_file_invalid)
    assert not res

    # Invalid data 3 (thrust and fuel flow not given)
    ads_b_file_invalid = str(
        get_copy_path(get_data_path("EHRD/ADS-B") / "EHRD_ads_b_data_invalid_3.csv")
    )
    res, msg = validate_adsb_file(ads_b_file_invalid)
    assert not res

    # Valid data
    ads_b_file_valid = str(
        get_copy_path(get_data_path("EHRD/ADS-B") / "EHRD_ads_b_data_valid.csv")
    )
    res, msg = validate_adsb_file(ads_b_file_valid)
    assert res

    # Invalid data 0.1 (no runways)
    db_delete_records(db_path, "shapes_runways", {"oid": 1})  # Remove all runways
    ads_b_file_valid = str(
        get_copy_path(get_data_path("EHRD/ADS-B") / "EHRD_ads_b_data_valid.csv")
    )
    res, msg = validate_adsb_file(ads_b_file_valid)
    assert not res
