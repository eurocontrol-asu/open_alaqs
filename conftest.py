"""
Root conftest.py for the open_alaqs test suite.

Adds infrastructure for slow-marked tests: tests tagged with
``@pytest.mark.slow`` are skipped by default (keeping the quick-feedback
loop fast) and only run when pytest is invoked with ``--run-slow``.

Rationale: a handful of database-layer tests need SpatiaLite's
``InitSpatialMetaData`` which takes ~30 seconds per test. Running them
on every commit makes the feedback cycle painful. Running them never
loses the coverage. The ``--run-slow`` flag lets CI do both: fast default
pass + a periodic full-coverage pass.

Usage::

    pytest                  # skips @pytest.mark.slow
    pytest --run-slow       # runs all tests including slow
"""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Run tests marked @pytest.mark.slow (typically take >10s each)",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (skipped by default, run with --run-slow)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-slow"):
        return
    skip_slow = pytest.mark.skip(reason="need --run-slow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
