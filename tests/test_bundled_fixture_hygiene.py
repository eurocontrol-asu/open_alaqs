"""State of the tracked .alaqs files that tests and users read.

- No runway trajectory cache is committed: the plugin rebuilds it at run
  time, and a committed one would be read back instead of the current
  runway placement.
- shapes_runways.oid is the INTEGER PRIMARY KEY (rowid alias), as in the
  templates: a runway added in QGIS gets an oid. The one tracked .alaqs
  without a shapes_runways table is tools/template_build/spatialite_base.alaqs,
  the bare SpatiaLite scaffold the templates are generated from (no study
  tables at all); it is the only expected skip.
"""

import sqlite3
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
# The bare SpatiaLite scaffold the templates are generated from: no study tables
NO_STUDY_TABLES = {"tools/template_build/spatialite_base.alaqs"}


def _tracked_alaqs():
    try:
        out = subprocess.check_output(
            ["git", "ls-files", "*.alaqs"], cwd=REPO, text=True
        )
        files = out.split()
    except (OSError, subprocess.CalledProcessError):
        files = []
    if not files:
        files = [str(p.relative_to(REPO)) for p in REPO.rglob("*.alaqs")]
    return sorted(files)


def _connect(rel):
    return sqlite3.connect(f"file:{REPO / rel}?mode=ro", uri=True)


@pytest.mark.parametrize("rel", _tracked_alaqs())
def test_no_committed_runway_trajectory_cache(rel):
    with _connect(rel) as conn:
        names = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name LIKE 'cache_runway_trajectories%'"
            )
        ]
    assert names == []


@pytest.mark.parametrize("rel", _tracked_alaqs())
def test_runway_oid_is_the_primary_key(rel):
    with _connect(rel) as conn:
        info = {r[1]: r for r in conn.execute("PRAGMA table_info(shapes_runways)")}
    if not info:
        assert rel in NO_STUDY_TABLES, f"{rel} has no shapes_runways table"
        pytest.skip(f"{rel}: the bare SpatiaLite scaffold has no shapes_runways")
    oid = info["oid"]
    assert oid[2].upper() == "INTEGER" and oid[5] == 1
