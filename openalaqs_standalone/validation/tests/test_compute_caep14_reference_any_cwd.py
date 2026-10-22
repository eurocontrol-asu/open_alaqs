"""compute_caep14_reference.py runs as a script from any working directory.

It put parents[1] (openalaqs_standalone/validation) on sys.path, so
`from open_alaqs...` failed with ModuleNotFoundError unless the repository
root was already importable. parents[3] is the repository root.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TOOL = (
    REPO
    / "openalaqs_standalone"
    / "validation"
    / "tools"
    / "compute_caep14_reference.py"
)


def _env_without_repo():
    env = dict(os.environ)
    keep = [
        p
        for p in env.get("PYTHONPATH", "").split(os.pathsep)
        if p and Path(p).resolve() != REPO
    ]
    env["PYTHONPATH"] = os.pathsep.join(keep)
    return env


def test_parents_index_is_repo_root():
    assert (REPO / "open_alaqs" / "__init__.py").is_file()
    assert TOOL.resolve().parents[3] == REPO


def test_tool_runs_from_another_cwd(tmp_path):
    res = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            str(REPO / "example" / "training" / "training_out.alaqs"),
            "--oid",
            "1",
        ],
        cwd=tmp_path,
        env=_env_without_repo(),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert res.returncode == 0, res.stderr
    assert "ModuleNotFoundError" not in res.stderr
