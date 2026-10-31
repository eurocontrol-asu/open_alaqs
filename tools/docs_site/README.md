# Documentation screenshots

`make_screenshots.py` retakes the images in `open_alaqs/assets/` that show an
OpenALAQS dialog, feature form, the toolbar or the Layers panel. It builds the
real dialogs and `.ui` forms offscreen, fills them with the training study
(`example/training`, copied to a scratch folder first), and saves PNG files
with the same names.

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=$PWD python tools/docs_site/make_screenshots.py
# some images only, or into another folder:
... make_screenshots.py --only gates.png toolbar.png --out /tmp/shots
```

Run it with the Python of QGIS 3.34 from the repository root. Pillow, when
available, stores the images as 256-colour PNGs.

Not made by the script: the QPIP dialogs, the QGIS Digitizing and Attributes
toolbars, the OSM import example map, and the method figures (`sas_*`,
`anp_*`, `smooth-and-shift.png`, `runway-touchdown-offset.svg`).
