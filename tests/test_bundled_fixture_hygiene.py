"""State of the tracked .alaqs files that tests and users read.

- No runway trajectory cache is committed: the plugin rebuilds it at run
  time, and a committed one would be read back instead of the current
  runway placement.
"""

import sqlite3
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


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
