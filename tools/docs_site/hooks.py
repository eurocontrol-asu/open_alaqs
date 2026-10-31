"""MkDocs hooks of the documentation site (tools/docs_site/mkdocs.yml).

- A link from a page to a repository file that the site does not publish (a CSV, a
  script, a folder) points to that file on GitHub, so it does not end on a 404. On
  GitHub itself the Markdown links are unchanged and work as they are.
- The CHANGELOG stays searchable but ranks below the other pages: its long release
  notes otherwise come first for most technical terms.

DOCS_GIT_REF (environment) is the branch or tag the GitHub links point to; the
publishing workflow sets it to the release tag, so a version's site links to the code
of that version. Default: main.
"""

import os
import posixpath
import re
from urllib.parse import quote, unquote

REPO_URL = "https://github.com/eurocontrol-asu/open_alaqs"

_HREF = re.compile(r'(<a\b[^>]*?\shref=")([^"#?]+)((?:[#?][^"]*)?")')


def on_page_markdown(markdown, page, config, files):
    if page.file.src_uri == "CHANGELOG.md":
        page.meta.setdefault("search", {})["boost"] = 0.1
    return markdown


def on_page_content(html, page, config, files):
    ref = os.environ.get("DOCS_GIT_REF", "main")
    root = config["docs_dir"]
    published = {f.src_uri for f in files if not f.inclusion.is_excluded()}
    page_dir = posixpath.dirname(page.file.src_uri)

    def fix(match):
        target = unquote(match.group(2))
        if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("/"):
            return match.group(0)
        # Links to published pages were already rewritten by MkDocs (.html).
        if target.endswith(".html"):
            return match.group(0)
        path = posixpath.normpath(posixpath.join(page_dir, target))
        if path.startswith("..") or path in published:
            return match.group(0)
        full = os.path.join(root, path)
        if not os.path.exists(full):
            return match.group(0)
        kind = "tree" if os.path.isdir(full) else "blob"
        url = f"{REPO_URL}/{kind}/{ref}/{quote(path)}"
        return f"{match.group(1)}{url}{match.group(3)}"

    return _HREF.sub(fix, html)
