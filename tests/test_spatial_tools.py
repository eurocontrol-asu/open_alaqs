import pytest
from qgis.core import QgsGeometry, QgsPoint
from qgis.testing import start_app
from qgis.testing.mocked import get_iface

from open_alaqs.core.tools.spatial import get_line_vertices

start_app()


@pytest.fixture(scope="module")
def plugin_instance():
    print("\nINFO: Get plugin instance")
    from open_alaqs.openalaqs import OpenALAQS

    plugin = OpenALAQS(get_iface())
    yield plugin

    print(" [INFO] Tearing down plugin instance")
    plugin.unload()


@pytest.fixture(scope="module")
def datasets_to_test():
    print("\nINFO: Get datasets to test...")
    return {
        "line_vertices": [
            {
                "input": "LineString( 0 0 0.1, 10 10 1)",
                "expected": [QgsPoint(0, 0, 0.1), QgsPoint(10, 10, 1)],
            },
            {
                "input": "LineString( 0 0, 10 10)",
                "expected": [QgsPoint(0, 0), QgsPoint(10, 10)],
            },
            {"input": "LineString EMPTY", "expected": []},
            {"input": "LineString ()", "expected": []},
            {
                "input": "MULTILINESTRING((0 0 0.1, 10 10 1),(10 10 1, 20 20 2))",
                "expected": [
                    QgsPoint(0, 0, 0.1),
                    QgsPoint(10, 10, 1),
                    QgsPoint(10, 10, 1),
                    QgsPoint(20, 20, 2),
                ],
            },
            {
                "input": "MULTILINESTRING((0 0 0.1, 10 10 1),(20 20 2, 30 30 3))",
                "expected": [
                    QgsPoint(0, 0, 0.1),
                    QgsPoint(10, 10, 1),
                    QgsPoint(20, 20, 2),
                    QgsPoint(30, 30, 3),
                ],
            },
            {
                "input": "MULTILINESTRING((0 0, 10 10),(10 10, 20 20))",
                "expected": [
                    QgsPoint(0, 0),
                    QgsPoint(10, 10),
                    QgsPoint(10, 10),
                    QgsPoint(20, 20),
                ],
            },
            {
                "input": "MULTILINESTRING((0 0, 10 10),(20 20, 30 30))",
                "expected": [
                    QgsPoint(0, 0),
                    QgsPoint(10, 10),
                    QgsPoint(20, 20),
                    QgsPoint(30, 30),
                ],
            },
        ]
    }


def test_line_vertices(plugin_instance, datasets_to_test):
    print(" [INFO] Validating line vertices...")

    count = 0
    for dataset in datasets_to_test.get("line_vertices", []):
        count += 1

        vertices = get_line_vertices(QgsGeometry.fromWkt(dataset["input"]))
        assert vertices == dataset["expected"]

    assert count > 0
