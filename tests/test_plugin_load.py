import pytest
from qgis.testing import start_app
from qgis.testing.mocked import get_iface

start_app()


@pytest.fixture(scope="module")
def plugin_instance():
    print("\nINFO: Get plugin instance")
    from open_alaqs.openalaqs import OpenALAQS

    plugin = OpenALAQS(get_iface())
    yield plugin

    print(" [INFO] Tearing down plugin instance")
    plugin.unload()


def test_plugin_load(plugin_instance):
    """
    Basic test to check whether the plugin loads and unloads without GUI
    """
    print(" [INFO] Validating plugin load...")
    assert plugin_instance.iface is not None
