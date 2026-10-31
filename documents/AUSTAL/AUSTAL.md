# AUSTAL installation

This page explains how to install AUSTAL for use with OpenALAQS and which files of this folder to copy into the AUSTAL installation. It is for users who want to run dispersion from the plugin. How to prepare, run and view a dispersion run is in [Dispersion modelling with AUSTAL](../user/DISPERSION_AUSTAL.md).

AUSTAL is a dispersion model and the reference implementation of Annex 2 of the German Technical Instructions on Air Quality Control (TA Luft). The German Environment Agency (UBA) publishes it free of charge under the GNU Public Licence.

## Installation

1. Open the [AUSTAL download page](https://www.umweltbundesamt.de/en/topics/air/air-quality-control-in-europe/download) of the UBA.
2. Download the base package for your operating system. The plugin's help names the AUSTAL 3.3.0 packages:
   - Windows: `AUSTAL_3.3.0_Windows.zip`
   - Linux: `AUSTAL_3.3.0_Linux.zip`
3. Extract the package to a folder of your choice.
4. Replace `austal.settings` in that folder with the copy in this folder (see [Configuration files](#configuration-files)).
5. If the English language files are not in the AUSTAL folder, copy them from this folder.
6. In QGIS, open **Calculate Dispersion** and select `austal.exe` (Windows) or `austal` (Linux) in section 1, *AUSTAL Executable*. The plugin remembers the path. See [Calculate Dispersion dialog](../user/DISPERSION_AUSTAL.md#calculate-dispersion-dialog).

The **AUSTAL Help** button in that section repeats these steps and links to the files of this folder on GitHub, since the plugin package does not contain them.

## Configuration files

| File | Purpose | What to do |
|------|---------|------------|
| `austal.settings` | AUSTAL's system and substance settings, with the sections OpenALAQS needs added | Replace the file of the AUSTAL folder with this copy |
| `AST_en@latin1.nls` | English assistant messages | Copy into the AUSTAL folder if missing |
| `DIA_en@latin1.nls` | English diagnostic messages | Copy into the AUSTAL folder if missing |

### austal.settings

`austal.settings` contains:

- `[.system]`: deposition parameters of the five aerosol groups;
- `[.astl]`: the standard substance properties (units, concentration factor, reference values, deposition settings), the NO to NO2 conversion times and the odour threshold;
- one section per substance (`[SO2]`, `[NOX]`, `[NO2]`, `[PM]`, `[ODOR]`, ...) with its units, assessment values and, where relevant, deposition and washout parameters.

The OpenALAQS copy adds four substances that OpenALAQS writes to AUSTAL and that are not among AUSTAL's standard substances: `[SOX]`, `[HC]`, `[CO2]` and `[CO]`. They are gaseous (aerosol group 0) passive tracers with no deposition or washout, reported in µg/m³ (CO2 in mg/m³). Without them, AUSTAL cannot handle these pollutants.

The file does not hold the grid, meteorology, receptors or sources of a run. OpenALAQS writes those for each run; see [AUSTAL input files](../user/DISPERSION_AUSTAL.md#austal-input-files).

### Language files

`AST_en@latin1.nls` and `DIA_en@latin1.nls` make AUSTAL write its messages in English (Latin-1 / ISO-8859-1 encoding). They are part of the separate AUSTAL language pack ("Sprachpakete DE/EN, UTF-8/ISO-8859-1") on the same UBA page. The copies in this folder save that download.

## See also

- [Dispersion modelling with AUSTAL](../user/DISPERSION_AUSTAL.md)
- [AUSTAL documentation (UBA)](https://www.umweltbundesamt.de/en/topics/air/air-quality-control-in-europe/overview)
- [Janicke Consulting](https://www.janicke.de/), the developers of AUSTAL
