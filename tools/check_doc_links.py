"""Check the relative links of the repository's Markdown files.

For every ``*.md`` file under the repository root (``.git`` and virtual environments
excluded), each relative link ``[text](path#anchor)`` and each ``<img src="...">`` must
point to an existing file, and an anchor into a Markdown file must match one of its
headings (GitHub's slug rules) or an explicit ``<a id="...">``. External links
(``http``, ``https``, ``mailto``) are not checked. Code blocks and HTML comments are
ignored.

Usage, from the repository root::

    python3 tools/check_doc_links.py

Exit status 1 when a link is broken, with one line per broken link.
"""

import glob
import os
import re
import sys
from urllib.parse import unquote

SKIP_DIRS = (".git", "venv", ".venv", "site", "node_modules")
FENCE = re.compile(r"```.*?```", flags=re.S)
COMMENT = re.compile(r"<!--.*?-->", flags=re.S)
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$", flags=re.M)
LINK = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMG = re.compile(r"<img[^>]+src=\"([^\"]+)\"")
EXPLICIT_ANCHOR = re.compile(r"<a\s+(?:name|id)=\"([^\"]+)\"")


def _strip(text):
    return COMMENT.sub("", FENCE.sub("", text))


def _slug(heading):
    heading = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)  # [x](y) -> x
    heading = re.sub(r"`([^`]*)`", r"\1", heading)
    slug = heading.strip().lower()
    slug = re.sub(r"[^\w\- ]", "", slug, flags=re.U)
    return slug.replace(" ", "-")


_anchor_cache = {}


def anchors(path):
    if path not in _anchor_cache:
        with open(path, encoding="utf-8") as f:
            text = _strip(f.read())
        found, counts = set(), {}
        for m in HEADING.finditer(text):
            s = _slug(m.group(1))
            n = counts.get(s, 0)
            counts[s] = n + 1
            found.add(s if n == 0 else f"{s}-{n}")
        found.update(EXPLICIT_ANCHOR.findall(text))
        _anchor_cache[path] = found
    return _anchor_cache[path]


def markdown_files(root):
    for path in glob.glob(os.path.join(root, "**", "*.md"), recursive=True):
        rel = os.path.relpath(path, root)
        if not rel.split(os.sep)[0] in SKIP_DIRS:
            yield path


def check(root="."):
    broken = []
    for md in sorted(markdown_files(root)):
        with open(md, encoding="utf-8") as f:
            text = _strip(f.read())
        for target in LINK.findall(text) + IMG.findall(text):
            if re.match(r"^(https?:|mailto:)", target):
                continue
            path, _, fragment = target.partition("#")
            dest = (
                os.path.normpath(os.path.join(os.path.dirname(md), unquote(path)))
                if path
                else md
            )
            if path and not os.path.exists(dest):
                broken.append(f"{os.path.relpath(md, root)}: {target} (no such file)")
            elif fragment and dest.endswith(".md") and fragment not in anchors(dest):
                broken.append(f"{os.path.relpath(md, root)}: {target} (no such anchor)")
    return broken


if __name__ == "__main__":
    problems = check(sys.argv[1] if len(sys.argv) > 1 else ".")
    for p in problems:
        print(p)
    print(f"{len(problems)} broken link(s)")
    sys.exit(1 if problems else 0)
