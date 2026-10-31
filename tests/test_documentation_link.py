"""The plugin opens the documentation site of its own version (toolbar action and About)."""

import pytest
from qgis.PyQt import QtGui
from qgis.testing import start_app
from qgis.testing.mocked import get_iface

from open_alaqs.core.tools.docs_url import DOCS_SITE, docs_url, plugin_version

start_app()


@pytest.mark.parametrize(
    "version, expected",
    [
        ("5.4.1", f"{DOCS_SITE}5.4.1/"),
        ("6.0.0", f"{DOCS_SITE}6.0.0/"),
        ("5.4.2-dev", f"{DOCS_SITE}latest/"),
        ("5.4", f"{DOCS_SITE}latest/"),
        ("", f"{DOCS_SITE}latest/"),
    ],
)
def test_release_versions_have_their_own_copy(version, expected):
    assert docs_url(version=version) == expected


def test_page_path():
    assert (
        docs_url("documents/user/USER_GUIDE.html", version="5.4.1")
        == f"{DOCS_SITE}5.4.1/documents/user/USER_GUIDE.html"
    )


def test_installed_version_is_read_from_metadata():
    version = plugin_version()
    assert version
    assert docs_url() == docs_url(version=version)


def test_toolbar_action_opens_the_documentation(monkeypatch):
    from open_alaqs.openalaqs import OpenALAQS

    opened = []
    monkeypatch.setattr(QtGui.QDesktopServices, "openUrl", opened.append)
    plugin = OpenALAQS(get_iface())
    plugin.initGui()
    try:
        action = plugin.actions["documentation"]
        added = [c.args[0] for c in plugin.open_alaqs_toolbar.addAction.call_args_list]
        assert action in added
        assert action.isEnabled()
        action.trigger()
        assert [u.toString() for u in opened] == [docs_url()]
    finally:
        plugin.unload()


def test_about_dialog_links_the_documentation():
    from open_alaqs.openalaqsdialog import OpenAlaqsAbout

    dialog = OpenAlaqsAbout(get_iface())
    text = dialog.ui.label.text()
    assert f'href="{docs_url()}"' in text
    assert "open-alaqs@eurocontrol.int" in text  # the rest of the text is kept
