"""Value-map lists read from a study whose path holds "#", "?" or "%".

`_study_values` opened the study with the URI f"file:{path}?mode=ro" without
percent-encoding: SQLite read "#" as the start of a fragment and "%41" as an
escape, opened the wrong file, and the point-source Category and Type lists
came up empty (the form has no other source for them). The URI is now built
with Path.as_uri().
"""

import shutil
from pathlib import Path, PureWindowsPath

import pytest
from qgis.testing import start_app

start_app()

from open_alaqs.openalaqsuitoolkit import (  # noqa: E402
    VALUE_MAP_SOURCES,
    _sqlite_read_only_uri,
)

REPO = Path(__file__).resolve().parents[1]
TRAINING = REPO / "example" / "training" / "training.alaqs"
SOURCES = ("stationary_categories", "stationary_types", "runway_directions")


def _lists(db: Path) -> dict:
    return {name: VALUE_MAP_SOURCES[name](str(db)) for name in SOURCES}


@pytest.fixture(scope="module")
def plain(tmp_path_factory):
    db = tmp_path_factory.mktemp("plain") / "training.alaqs"
    shutil.copy(TRAINING, db)
    return _lists(db)


@pytest.mark.parametrize(
    "folder, name",
    [
        ("dir #2", "training.alaqs"),
        ("dir 50%41", "training.alaqs"),
        ("dir ?x", "training.alaqs"),
        ("plain", "study #1 50%41.alaqs"),
    ],
)
def test_lists_do_not_depend_on_the_path(tmp_path, plain, folder, name):
    db = tmp_path / folder / name
    db.parent.mkdir()
    shutil.copy(TRAINING, db)
    lists = _lists(db)
    assert len(plain["stationary_categories"]) > 1
    assert len(plain["stationary_types"]) > 1
    assert plain["runway_directions"]
    assert lists == plain


def test_relative_path_is_resolved(tmp_path, plain, monkeypatch):
    db = tmp_path / "dir #2" / "training.alaqs"
    db.parent.mkdir()
    shutil.copy(TRAINING, db)
    monkeypatch.chdir(tmp_path)
    assert _lists(Path("dir #2") / "training.alaqs") == plain


def test_missing_or_empty_path_gives_no_values(tmp_path):
    assert VALUE_MAP_SOURCES["stationary_categories"]("") == []
    assert VALUE_MAP_SOURCES["stationary_categories"](str(tmp_path / "no.alaqs")) == []
    assert not (tmp_path / "no.alaqs").exists()  # read-only: nothing created


@pytest.mark.parametrize(
    "path, uri",
    [
        (
            r"C:\Users\me\dir #2\training.alaqs",
            "file:///C:/Users/me/dir%20%232/training.alaqs?mode=ro",
        ),
        (
            r"D:\dir 50%41\s.alaqs",
            "file:///D:/dir%2050%2541/s.alaqs?mode=ro",
        ),
        (
            r"\\server\share\dir #2\s.alaqs",
            "file:////server/share/dir%20%232/s.alaqs?mode=ro",
        ),
    ],
)
def test_windows_uris(path, uri):
    assert _sqlite_read_only_uri(PureWindowsPath(path)) == uri
