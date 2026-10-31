"""Retake the documentation screenshots of the OpenALAQS dialogs and forms.

The images in ``open_alaqs/assets/`` that show an OpenALAQS dialog, form or
the toolbar are rendered offscreen from the real ``.ui`` files and dialog
classes, filled with the training study (``example/training``). The study
files are copied to a scratch folder first; the originals are not touched.

Usage (QGIS 3.34 Python, from the repository root)::

    QT_QPA_PLATFORM=offscreen PYTHONPATH=$PWD python tools/docs_site/make_screenshots.py
    ... make_screenshots.py --only gates.png toolbar.png   # some images only
    ... make_screenshots.py --out /tmp/shots               # another folder

Style: Fusion, Liberation Sans 9 pt, fixed widget sizes, and a plain title
strip with the window title (``QWidget.grab`` does not capture the window
manager's title bar). Run ``optipng -o5`` on the result if available
(``--optipng`` does it).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
TRAINING = REPO / "example" / "training"
ASSETS = REPO / "open_alaqs" / "assets"
ICON = REPO / "open_alaqs" / "icon.png"

from qgis.testing import start_app  # noqa: E402

QGIS_APP = start_app()

from qgis.core import (  # noqa: E402
    QgsEditFormConfig,
    QgsLayerTreeModel,
    QgsProject,
    QgsSettings,
)
from qgis.gui import (  # noqa: E402
    QgsAttributeEditorContext,
    QgsAttributeForm,
    QgsGui,
    QgsLayerTreeView,
)
from qgis.PyQt import QtCore, QtGui, QtWidgets  # noqa: E402

FONT = QtGui.QFont("Liberation Sans", 9)
TITLE_HEIGHT = 28

SHOTS = {}


def shot(*names):
    def register(func):
        SHOTS[func] = names
        return func

    return register


# ---------------------------------------------------------------- helpers


def settle(widget=None, rounds=5):
    for _ in range(rounds):
        QtWidgets.QApplication.processEvents()
    if widget is not None:
        widget.repaint()


def with_title(pixmap: QtGui.QPixmap, title: str | None, icon=True) -> QtGui.QImage:
    """The grabbed client area with a 1 px frame and, when given, a title
    strip (icon and window title) like a plain window decoration."""
    top = TITLE_HEIGHT if title else 0
    w, h = pixmap.width() + 2, pixmap.height() + top + 2
    image = QtGui.QImage(w, h, QtGui.QImage.Format.Format_RGB32)
    image.fill(QtGui.QColor("#ffffff"))
    p = QtGui.QPainter(image)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
    if title:
        p.fillRect(1, 1, w - 2, top, QtGui.QColor("#f3f3f3"))
        logo = QtGui.QPixmap(str(ICON)).scaled(
            16,
            16,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        if icon:
            p.drawPixmap(9, 1 + (top - 16) // 2, logo)
        p.setPen(QtGui.QColor("#202020"))
        p.setFont(QtGui.QFont("Liberation Sans", 10))
        p.drawText(
            QtCore.QRect(32 if icon else 10, 1, w - 70, top),
            QtCore.Qt.AlignmentFlag.AlignVCenter,
            title,
        )
        # close cross
        p.setPen(QtGui.QPen(QtGui.QColor("#404040"), 1.2))
        cx, cy = w - 20, 1 + top // 2
        p.drawLine(cx - 5, cy - 5, cx + 5, cy + 5)
        p.drawLine(cx - 5, cy + 5, cx + 5, cy - 5)
    p.drawPixmap(1, 1 + top, pixmap)
    p.setPen(QtGui.QColor("#8a8a8a"))
    p.drawRect(0, 0, w - 1, h - 1)
    p.end()
    return image


def save(image, name, out_dir: Path):
    path = out_dir / name
    if isinstance(image, QtGui.QPixmap):
        image = image.toImage()
    image.save(str(path), "PNG")
    _shrink(path)
    print(f"  wrote {path.relative_to(REPO) if path.is_relative_to(REPO) else path}")


def _shrink(path: Path):
    """Store as a 256-colour palette PNG (UI screenshots have few colours);
    needs Pillow, else the file stays RGB."""
    try:
        from PIL import Image
    except ImportError:
        return
    with Image.open(path) as im:
        rgb = im.convert("RGB")
    rgb.quantize(
        colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
    ).save(path, optimize=True)


def grab_window(
    widget: QtWidgets.QWidget, size: tuple[int, int], title=None, icon=True
):
    widget.setFixedSize(*size)
    widget.show()
    settle(widget)
    return with_title(widget.grab(), title or widget.windowTitle(), icon)


def set_file(widget, path):
    """QgsFileWidget: set the path and emit fileChanged like a user choice."""
    widget.setFilePath(str(path))
    settle()


# ---------------------------------------------------------------- set-up


class FakeIface:
    """The parts of QgisInterface the dialogs use."""

    def __init__(self):
        from qgis.gui import QgsMapCanvas

        self._main = QtWidgets.QMainWindow()
        self._canvas = QgsMapCanvas(self._main)

    def mainWindow(self):
        return self._main

    def mapCanvas(self):
        return self._canvas

    def addToolBar(self, name):
        return self._main.addToolBar(name)

    def messageBar(self):
        from qgis.gui import QgsMessageBar

        return QgsMessageBar(self._main)

    def __getattr__(self, name):  # anything else: a no-op
        return lambda *a, **k: None


class Study:
    """Copies of the training study files in a scratch folder."""

    def __init__(self):
        self.dir = Path(tempfile.gettempdir()) / "openalaqs-screenshots" / "training"
        if self.dir.exists():
            shutil.rmtree(self.dir)
        self.dir.mkdir(parents=True)
        for name in (
            "training.alaqs",
            "training_out.alaqs",
            "training_movements.csv",
            "training_meteo.csv",
            "training_ads_b_data.csv",
        ):
            shutil.copy(TRAINING / name, self.dir / name)
        self.db = self.dir / "training.alaqs"
        self.out = self.dir / "training_out.alaqs"
        self.austal_dir = self.dir / "AUSTAL"
        self.austal_dir.mkdir()

        from open_alaqs.core.alaqsdblite import ProjectDatabase

        ProjectDatabase().path = str(self.db)
        self.layers = {}

    def layer(self, alaqs_layer):
        """The study layer, loaded as the plugin loads it (form, style)."""
        from open_alaqs.alaqs_config import LAYERS_CONFIG
        from open_alaqs.openalaqsuitoolkit import load_spatialite_layer

        if alaqs_layer not in self.layers:
            name = LAYERS_CONFIG[alaqs_layer]["name"]

            def find():
                return [
                    lyr
                    for lyr in QgsProject.instance().mapLayersByName(name)
                    if str(self.db) in lyr.source()
                ]

            if not find():
                load_spatialite_layer(None, str(self.db), alaqs_layer)
            (layer,) = find()
            self.layers[alaqs_layer] = layer
        return self.layers[alaqs_layer]


def reset_settings(study: Study):
    """Remembered paths, so that the dialogs open on the training study."""
    s = QgsSettings()
    s.setValue("qgis/enableMacros", "Never")
    s.setValue("OpenALAQS/last_result_file_path", "")
    s.setValue("OpenALAQS/last_alaqs_file_path", "")
    s.setValue("OpenALAQS/last_work_directory_path", "")
    for key in (
        "open_alaqs/a2k_executable_path",
        "OpenALAQS/last_alaqs_output_file_path",
        "OpenALAQS/last_emissions_csv_path",
        "OpenALAQS/last_meteo_csv_path",
        "OpenALAQS/last_grid_file_path",
        "OpenALAQS/last_csv_output_directory_path",
    ):
        s.setValue(key, "")


_KEEP = []  # forms stay alive until the end (deleting them while connected crashes)


def feature_form(study, alaqs_layer, feature=None, tab=None):
    """The feature form of a layer, as QGIS opens it: QgsAttributeForm with
    the layer's .ui and field configuration, then the form's form_open."""
    from qgis.core import QgsVectorLayerUtils

    from open_alaqs.alaqs_config import LAYERS_CONFIG

    layer = study.layer(alaqs_layer)
    if not layer.isEditable():
        layer.startEditing()
    add = feature is None
    if add:
        feature = QgsVectorLayerUtils.createFeature(layer)

    cfg = layer.editFormConfig()
    keep = (cfg.initFunction(), cfg.initCodeSource())
    cfg.setInitFunction("")
    cfg.setInitCodeSource(QgsEditFormConfig.PythonInitCodeSource.CodeSourceNone)
    layer.setEditFormConfig(cfg)
    form = QgsAttributeForm(layer, feature, QgsAttributeEditorContext())
    form.setMode(
        QgsAttributeEditorContext.Mode.AddFeatureMode
        if add
        else QgsAttributeEditorContext.Mode.SingleEditMode
    )
    cfg.setInitFunction(keep[0])
    cfg.setInitCodeSource(keep[1])
    layer.setEditFormConfig(cfg)

    init_file = REPO / "open_alaqs" / "ui" / LAYERS_CONFIG[alaqs_layer]["py_filename"]
    namespace = {"__name__": f"_qgis_form_{init_file.stem}"}
    exec(
        compile(init_file.read_text(encoding="utf-8"), str(init_file), "exec"),
        namespace,
    )
    namespace["form_open"](form, layer, form.feature())
    form.showButtonBox()  # OK / Cancel, as in the feature dialog
    _KEEP.append(form)
    if tab is not None:
        tabs = form.findChild(QtWidgets.QTabWidget)
        tabs.setCurrentIndex(tab)
    title = f"{layer.name()} - Feature Attributes"
    return form, title


def first_feature(study, alaqs_layer):
    return next(study.layer(alaqs_layer).getFeatures())


# ---------------------------------------------------------------- toolbar


def _toolbar(project_open: bool):
    from open_alaqs import openalaqs

    iface = FakeIface()
    plugin = openalaqs.OpenALAQS(iface)
    plugin.macro_check = lambda: None  # no macro prompt
    plugin.initGui()
    if project_open:  # as run_project_load leaves it
        for key in (
            "study_setup",
            "osm_import",
            "profiles_edit",
            "taxi_routes",
            "build_inventory",
            "view_results_analysis",
            "calculate_dispersion",
            "project_close",
        ):
            plugin.actions[key].setEnabled(True)
        plugin.actions["project_load"].setEnabled(False)
        plugin.actions["project_create"].setEnabled(False)
    bar = plugin.open_alaqs_toolbar
    bar.setIconSize(QtCore.QSize(24, 24))
    bar.adjustSize()
    iface.mainWindow().resize(bar.sizeHint().width() + 20, 60)
    iface.mainWindow().show()
    settle(bar)
    _KEEP.append((iface, plugin))
    return with_title(bar.grab(), None)


@shot("screenshot.png", "toolbar.png")
def toolbar(study, out):
    # README: the toolbar after installation (no study open)
    save(_toolbar(project_open=False), "screenshot.png", out)
    # User guide: the toolbar with a study open
    save(_toolbar(project_open=True), "toolbar.png", out)


# ---------------------------------------------------------------- dialogs


@shot("alaqs-project-properties.png", "alaqs-project-properties2.png")
def study_setup(study, out):
    from open_alaqs.openalaqsdialog import OpenAlaqsStudySetup

    for tab, name in (
        (0, "alaqs-project-properties.png"),
        (1, "alaqs-project-properties2.png"),
    ):
        dlg = OpenAlaqsStudySetup(FakeIface())
        dlg.ui.tabWidget.setCurrentIndex(tab)
        save(grab_window(dlg, (567, 610)), name, out)
        _KEEP.append(dlg)


@shot("import-osm-data.png")
def osm_import(study, out):
    from open_alaqs.openalaqsdialog import OpenAlaqsOsmImport

    dlg = OpenAlaqsOsmImport()
    # The dialog as it opens when the QuickOSM plugin is installed (it is
    # not installed here, which disables the dialog and shows a warning).
    ui = dlg.ui
    for w in (ui.infoLabel, ui.selectLayersGroupBox, ui.importCheckBox):
        w.setEnabled(True)
    ui.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Yes).setEnabled(True)
    ui.errorLabel.setVisible(False)
    save(grab_window(dlg, (568, 410)), "import-osm-data.png", out)
    _KEEP.append(dlg)


@shot("activity-profiles.png")
def profiles(study, out):
    from open_alaqs.openalaqsdialog import OpenAlaqsProfiles

    dlg = OpenAlaqsProfiles(FakeIface())
    dlg.ui.tabWidget.setCurrentIndex(0)
    save(grab_window(dlg, (382, 470)), "activity-profiles.png", out)
    _KEEP.append(dlg)


@shot("taxiroutes-editor-1.png", "taxiroutes-editor-2.png")
def taxi_routes(study, out):
    from open_alaqs.openalaqsdialog import OpenAlaqsTaxiRoutes

    for tab, name in ((0, "taxiroutes-editor-1.png"), (1, "taxiroutes-editor-2.png")):
        dlg = OpenAlaqsTaxiRoutes(FakeIface())
        if tab == 0:  # create a route: gate, runway, operation, instance
            dlg.ui.createEditTaxiRouteTabWidget.setCurrentWidget(dlg.ui.createRouteTab)
            dlg.ui.gate.setCurrentIndex(dlg.ui.gate.findText("G4"))
        else:  # edit it: taxiways in order (and the aircraft groups tab)
            dlg.ui.createEditTaxiRouteTabWidget.setCurrentWidget(dlg.ui.editRouteTab)
            dlg.ui.taxiwaysAircraftGroupsTabWidget.setCurrentIndex(0)
        save(grab_window(dlg, (586, 510)), name, out)
        _KEEP.append(dlg)


@shot("generate-emissions-inventory.png")
def inventory(study, out):
    from open_alaqs.openalaqsdialog import OpenAlaqsInventory

    dlg = OpenAlaqsInventory()
    ui = dlg.ui
    set_file(ui.output_save_path, study.dir)
    ui.output_save_name.setText("training")
    set_file(ui.adsb_table_path, study.dir / "training_ads_b_data.csv")
    set_file(ui.movement_table_path, study.dir / "training_movements.csv")
    set_file(ui.met_file_path, study.dir / "training_meteo.csv")
    save(grab_window(dlg, (606, 700)), "generate-emissions-inventory.png", out)
    _KEEP.append(dlg)


def _results_dialog(study):
    from open_alaqs.openalaqsdialog import OpenAlaqsResultsAnalysis

    dlg = OpenAlaqsResultsAnalysis(FakeIface())
    set_file(dlg.ui.result_file_path, study.out)
    _KEEP.append(dlg)
    return dlg


@shot("emissions-calculation.png", "emissions-calculation-2.png")
def results_analysis(study, out):
    dlg = _results_dialog(study)
    dlg.ui.configuration_modules_list.setCurrentRow(0)
    save(grab_window(dlg, (666, 700)), "emissions-calculation.png", out)
    dlg = _results_dialog(study)
    dlg.ui.configuration_modules_list.setCurrentRow(2)
    save(grab_window(dlg, (666, 700)), "emissions-calculation-2.png", out)


@shot("running-austal.png", "running-austal-2.png")
def dispersion(study, out):
    from open_alaqs.gui.DispersionAnalysis import OpenAlaqsDispersionAnalysis

    # An empty stand-in for the AUSTAL executable: the picker only checks
    # that the file exists. Nothing is run.
    exe = study.dir / "austal" / ("austal.exe" if os.name == "nt" else "austal")
    exe.parent.mkdir(exist_ok=True)
    exe.touch()

    dlg = OpenAlaqsDispersionAnalysis(FakeIface())
    _KEEP.append(dlg)
    ui = dlg.ui
    set_file(ui.a2k_executable_path, exe)
    ui.generateFromAlaqsRadio.setChecked(True)
    set_file(ui.alaqs_output_file_path, study.out)
    set_file(ui.alaqs_output_work_dir_path, study.dir)
    ui.alaqs_pollutant_nox.setChecked(True)
    ui.alaqs_pollutant_pm10.setChecked(True)
    # Result Visualisation: Grid Management with the inventory of the run
    ui.alaqsGridGroupBox.setChecked(True)
    set_file(ui.alaqs_file_path, study.out)
    settle()

    # The whole dialog without a scroll bar: as tall as its contents.
    dlg.setFixedSize(818, 1200)
    dlg.show()
    settle(dlg)
    extra_w = dlg.width() - ui.scrollArea.viewport().width()
    extra_h = dlg.height() - ui.scrollArea.viewport().height()
    hint = ui.scrollContents.sizeHint()
    width = max(818, hint.width() + extra_w + 4)
    dlg.setFixedSize(width, 1200)
    settle(dlg)
    height = ui.scrollContents.heightForWidth(ui.scrollArea.viewport().width())
    height = max(height, ui.scrollContents.sizeHint().height()) + extra_h + 4
    save(grab_window(dlg, (width, height)), "running-austal.png", out)

    # Section 4 only
    box = ui.visualisationGroupBox
    top_left = box.mapTo(dlg, QtCore.QPoint(0, 0))
    rect = QtCore.QRect(
        top_left.x() - 4, top_left.y() - 2, box.width() + 8, box.height() + 6
    )
    save(with_title(dlg.grab(rect), None), "running-austal-2.png", out)


@shot("layers.png")
def layers_panel(study, out):
    """The Layers panel after loading the study (layers and basemap group
    as the plugin adds them)."""
    from open_alaqs.openalaqsuitoolkit import load_basemap_layers, load_layers

    load_layers(None, str(study.db))
    load_basemap_layers()
    root = QgsProject.instance().layerTreeRoot()
    model = QgsLayerTreeModel(root)
    model.setFlag(QgsLayerTreeModel.Flag.AllowNodeChangeVisibility)
    model.setFlag(QgsLayerTreeModel.Flag.ShowLegendAsTree)
    view = QgsLayerTreeView()
    view.setModel(model)
    view.expandAll()
    view.setIconSize(QtCore.QSize(16, 16))
    _KEEP.append((model, view))
    view.setCurrentIndex(QtCore.QModelIndex())
    view.clearSelection()
    save(grab_window(view, (300, 330), "Layers", icon=False), "layers.png", out)


# ---------------------------------------------------------------- feature forms


def _form_shot(study, out, alaqs_layer, name, size, feature=None, tab=None, typed=None):
    """typed: {widget name: text or combo index} entered in a new feature's form."""
    form, title = feature_form(study, alaqs_layer, feature, tab)
    for widget_name, value in (typed or {}).items():
        widget = form.findChild(QtWidgets.QWidget, widget_name)
        if isinstance(widget, QtWidgets.QComboBox):
            widget.setCurrentIndex(value)
        else:
            widget.setText(value)
    settle()
    save(grab_window(form, size, title), name, out)


@shot(
    "gates.png",
    "runways-layer.png",
    "taxiways-layer.png",
    "tracks-layer.png",
    "parkings-layer.png",
    "parkings-layer-2.png",
    "parkings-layer-3.png",
    "roadways-layer.png",
    "points-layer.png",
    "area-sources-layer.png",
    "buildings-layer.png",
)
def forms(study, out):
    from open_alaqs.enums import AlaqsLayerType as L

    _form_shot(
        study, out, L.GATE, "gates.png", (364, 230), first_feature(study, L.GATE)
    )
    _form_shot(
        study,
        out,
        L.RUNWAY,
        "runways-layer.png",
        (380, 250),
        first_feature(study, L.RUNWAY),
    )
    _form_shot(
        study,
        out,
        L.TAXIWAY,
        "taxiways-layer.png",
        (364, 160),
        first_feature(study, L.TAXIWAY),
    )
    # the training study has no tracks or buildings: a new feature, typed in
    _form_shot(
        study,
        out,
        L.TRACK,
        "tracks-layer.png",
        (364, 190),
        typed={"track_id": "24 arrival", "runway": 2, "departure_arrival": 1},
    )
    park = first_feature(study, L.PARKING)
    for tab, name in (
        (0, "parkings-layer.png"),
        (2, "parkings-layer-2.png"),
        (3, "parkings-layer-3.png"),
    ):
        _form_shot(study, out, L.PARKING, name, (400, 460), park, tab)
    _form_shot(
        study,
        out,
        L.ROADWAY,
        "roadways-layer.png",
        (400, 460),
        first_feature(study, L.ROADWAY),
        0,
    )
    _form_shot(
        study,
        out,
        L.POINT_SOURCE,
        "points-layer.png",
        (400, 460),
        first_feature(study, L.POINT_SOURCE),
        0,
    )
    _form_shot(
        study,
        out,
        L.AREA,
        "area-sources-layer.png",
        (400, 440),
        first_feature(study, L.AREA),
        0,
    )
    _form_shot(
        study,
        out,
        L.BUILDING,
        "buildings-layer.png",
        (300, 160),
        typed={"building_id": "Terminal", "height": "15"},
    )


# ---------------------------------------------------------------- main


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ASSETS, help="output folder")
    parser.add_argument("--only", nargs="*", help="image names to make")
    parser.add_argument("--optipng", action="store_true", help="run optipng -o5")
    args = parser.parse_args(argv)

    QtWidgets.QApplication.setStyle("Fusion")
    QtWidgets.QApplication.setFont(FONT)
    QtWidgets.QApplication.setPalette(QtWidgets.QApplication.style().standardPalette())
    if not QgsGui.editorWidgetRegistry().factories():
        QgsGui.editorWidgetRegistry().initEditors()

    args.out.mkdir(parents=True, exist_ok=True)
    study = Study()
    reset_settings(study)
    for func, names in SHOTS.items():
        if args.only and not set(names) & set(args.only):
            continue
        print(f"{func.__name__}: {', '.join(names)}")
        func(study, args.out)
        if args.optipng and shutil.which("optipng"):
            for n in names:
                subprocess.run(
                    ["optipng", "-quiet", "-o5", str(args.out / n)], check=False
                )
    for layer in study.layers.values():
        layer.rollBack()
    QgsProject.instance().removeAllMapLayers()
    print(f"study copy: {study.dir}")


if __name__ == "__main__":
    main()
