"""Address of the OpenALAQS documentation site for the installed plugin version.

The site is built from the repository's Markdown files (tools/docs_site/mkdocs.yml) and
published on GitHub Pages with one copy per release: ``<DOCS_SITE><version>/`` for a
release ``X.Y.Z`` and ``<DOCS_SITE>latest/`` for the newest one. A development version
(anything that is not ``X.Y.Z``) has no copy of its own and opens ``latest``.
"""

import configparser
import re
from pathlib import Path
from typing import Optional

DOCS_SITE = "https://eurocontrol-asu.github.io/open_alaqs/"

_RELEASE = re.compile(r"^\d+\.\d+\.\d+$")


def plugin_version() -> Optional[str]:
    """The ``version`` of the plugin's metadata.txt, or None if it cannot be read."""
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(Path(__file__).parents[2] / "metadata.txt", encoding="utf-8")
        return parser.get("general", "version").strip()
    except (configparser.Error, OSError):
        return None


def docs_url(page: str = "", version: Optional[str] = None) -> str:
    """URL of a documentation page for a plugin version.

    :param page: page path on the site, e.g. ``"documents/user/USER_GUIDE.html"``; empty
        for the home page.
    :param version: plugin version; by default the installed one (metadata.txt).
    """
    if version is None:
        version = plugin_version()
    folder = version if version and _RELEASE.match(version) else "latest"
    return f"{DOCS_SITE}{folder}/{page.lstrip('/')}"
