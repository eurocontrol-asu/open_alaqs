"""
austal_prep — standalone AUSTAL input file generator for OpenALAQS.

Reads two parquets (sources + emissions) plus a receptor CSV and a study
config, writes austal.txt + series.dmna + per-source grid files into an
output directory ready to be fed to AUSTAL.

Public API:
    from austal_prep import run_austal_prep, AustalStudyConfig, AustalPrepReport

No QGIS dependency. No SQL. No project-specific code paths. The input
contract is the cross-project parquet schema produced by
`openalaqs_standalone` (see `openalaqs_standalone/inventory_gpkg.py`
and `extract_sources.py` for the producing side).
"""

from austal_prep.config import AustalPrepReport, AustalStudyConfig, GridSpec
from austal_prep.runner import run_austal_prep

__all__ = [
    "run_austal_prep",
    "AustalStudyConfig",
    "AustalPrepReport",
    "GridSpec",
]
