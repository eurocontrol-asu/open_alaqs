# OpenALAQS

<!-- Add buttons here -->

<!-- Describe your project in brief -->

<!-- The project title should be self explanotory and try not to make it a mouthful. (Although exceptions exist- **awesome-readme-writing-guide-for-open-source-projects** - would have been a cool name)

Add a cover/banner image for your README. **Why?** Because it easily **grabs people's attention** and it **looks cool**(*duh!obviously!*).

The best dimensions for the banner is **1280x650px**. You could also use this for social preview of your repo.

I personally use [**Canva**](https://www.canva.com/) for creating the banner images. All the basic stuff is **free**(*you won't need the pro version in most cases*).

There are endless badges that you could use in your projects. And they do depend on the project. Some of the ones that I commonly use in every projects are given below.

I use [**Shields IO**](https://shields.io/) for making badges. It is a simple and easy to use tool that you can use for almost all your badge cravings. -->

<!-- Some badges that you could use -->

<!-- ![GitHub release (latest by date including pre-releases)](https://img.shields.io/github/v/release/navendu-pottekkat/awesome-readme?include_prereleases)
: This badge shows the version of the current release.

![GitHub last commit](https://img.shields.io/github/last-commit/navendu-pottekkat/awesome-readme)
: I think it is self-explanatory. This gives people an idea about how the project is being maintained.

![GitHub issues](https://img.shields.io/github/issues-raw/navendu-pottekkat/awesome-readme)
: This is a dynamic badge from [**Shields IO**](https://shields.io/) that tracks issues in your project and gets updated automatically. It gives the user an idea about the issues and they can just click the badge to view the issues.

![GitHub pull requests](https://img.shields.io/github/issues-pr/navendu-pottekkat/awesome-readme)
: This is also a dynamic badge that tracks pull requests. This notifies the maintainers of the project when a new pull request comes.

![GitHub All Releases](https://img.shields.io/github/downloads/navendu-pottekkat/awesome-readme/total): If you are not like me and your project gets a lot of downloads(*I envy you*) then you should have a badge that shows the number of downloads! This lets others know how **Awesome** your project is and is worth contributing to.

![GitHub](https://img.shields.io/github/license/navendu-pottekkat/awesome-readme)
: This shows what kind of open-source license your project uses. This is good idea as it lets people know how they can use your project for themselves.

![Tweet](https://img.shields.io/twitter/url?style=flat-square&logo=twitter&url=https%3A%2F%2Fnavendu.me%2Fnsfw-filter%2Findex.html): This is not essential but it is a cool way to let others know about your project! Clicking this button automatically opens twitter and writes a tweet about your project and link to it. All the user has to do is to click tweet. Isn't that neat? -->

<img src="./open_alaqs/assets/oa-logo.jpg" alt="OpenALAQS logo" width="50%">

## Table of contents

- [OpenALAQS](#openalaqs)
  - [Table of contents](#table-of-contents)
  - [Installation](#installation)
    - [Install QGIS](#install-qgis)
    - [Install dependencies](#install-dependencies)
    - [Install OpenALAQS](#install-openalaqs)
  - [Quick start](#quick-start)
    - [Example Files](#example-files)
    - [EHRD Example Study](#ehrd-example-study)
    - [Beta: Standalone Emissions + AUSTAL Inputs Exports Script](#beta-standalone-emissions--austal-inputs-export-script)
  - [GSE Application](#gse-application)

  - [Development](#development)
    - [Debugging](#debugging)
    - [Updating the OpenALAQS database templates](#updating-the-openalaqs-database-templates)
  - [Contribute](#contribute)
  - [License](#license)
  - [Contact](#contact)

## Installation

[(Back to top)](#table-of-contents)

To use OpenALAQS you need to install QGIS, as well as a couple of Python libraries for the proper functioning of the plugin.


### Install QGIS

Download and install QGIS on your operating system following the official [QGIS documentation](https://qgis.org/download/).

If you are running on Windows, you should install via [OSGeo4W installer](https://qgis.org/resources/installation-guide/#osgeo4w-installer) following the `Advanced Install` route.

> **Note:** If not installed using the OSGeo4W Network Installer, please uninstall the old version and install the new version using the OSGeo4W Network Installer or follow the installation guide from QGIS. During the installation process, accept the unmet dependencies and license agreements.


### Install dependencies

OpenALAQS is built on top of QGIS and a few external libraries that require separate installation.

You can find the list of libraries in the file `requirements.txt`.

**Primary method:** Use QPIP (Python Dependency Manager for QGIS Plugins) to check and install the required dependencies directly in the QGIS UI. See the **Install OpenALAQS** section for details.

**Alternative method:** Install the libraries manually using `pip install` in the Python environment used by QGIS:

```bash
pip install -r requirements.txt
```

<details>
<summary>OSGeo4W manual installation</summary>

Find and install those packages:

- `qgis-ltr-full` (3.34.x or newer)
- `python3-fiona`
- `python3-geopandas` (2.x.x)
- `python3-geographiclib`
- `python3-pandas` (2.2.1)
- `python3-matplotlib`
- `python3-numpy` (1.26.4)
- `python3-sqlalchemy` (2.0.28)
- `spatialite` (5.x.x)

Search for them in the search bar, and find them under the "Libs" sub-menu and select them such that they are not to be skipped in the installation (previously installed packages are shown as "Keep" in the "New" column). For QGIS you should select the latest version in the "Desktop" and "Libs" sub-menus.

</details>


### Install OpenALAQS

You can download OpenALAQS [latest release from GitHub](https://github.com/eurocontrol-asu/open_alaqs/releases/latest), or browse [previous releases](https://github.com/eurocontrol-asu/open_alaqs/releases/tag/v4.0.0).

Once you download the `.zip` file, go to QGIS, open the "Plugins", then "Manage and Install Plugins...".
In the newly opened window, select the "Install from ZIP" on the left sidebar.
Then select the recently downloaded `.zip` file and click "Install Plugin".

While installing OpenALAQS:

  + QGIS will first ask you to install its plugin dependency, called QPIP. Click `OK`.

    ![img.png](./open_alaqs/assets/install_plugin_dependencies.png)

  + Once QPIP is installed, QPIP asks to install the Python dependencies of OpenALAQS. If there is any conflicted dependency (marked in yellow), make sure you select a proper `Action` that allows OpenALAQS to find the required dependency version, like in the image below. Then click `OK`.

    ![img.png](./open_alaqs/assets/install_dependencies_via_qpip.png)

After that, QGIS will automatically install OpenALAQS in the appropriate location.

At this point the OpenALAQS toolbar is visible below the default QGIS toolbars.
If this is the case then the installation has been successful.

![img.png](./open_alaqs/assets/screenshot.png)


## Quick start

[(Back to top)](#table-of-contents)

### Example Files

Example study files are provided to help you get started with OpenALAQS:

- **For OpenALAQS v4.0.0:** Use the training example from `documents/Example-Training.zip`
- **For OpenALAQS v4.0.1+:** Use the example files from the `example/EHRD` folder, which includes 3D aircraft profiles support

### EHRD Example Study

Find an example study in the `example/EHRD` folder.

Here you can find the following files and directories:

- `./EHRD.alaqs` - the main ALAQS database, containing spatial and statistical information for a study of the Rotterdam The Hague airport.
- `./EHRD_out.alaqs` - the processed ALAQS database, containing spatial and statistical information for a study of the Rotterdam The Hague airport.
- `./EHRD_movements.csv` - the movements data in the study, used to generate `./EHRD_out.alaqs`.
- `./EHRD_meteo.csv` - the meteorological data in the study, used to generate `./EHRD_out.alaqs`.
- `./EHRD_AUSTAL/*` - a directory containing all files generated using OpenALAQS to be used as ALAQS input files.
- `./EHRD_AUSTAL/austal.txt` - the file containing all main input parameters except for time-dependent parameters.
- `./EHRD_AUSTAL/series.dmna` - the file containing all time-dependent parameters.
- `./EHRD_AUSTAL/01/e0001.dmna` - input grid file, with information on the user-defined grid and on the corresponding data.

For more detailed information on how to use OpenALAQS, the project files and expected outputs, read the [User Guide](documents/USER_GUIDE.md).

### Beta: Standalone Emissions + AUSTAL Inputs Export Script

This repository contains a beta standalone script that can generate emissions exports (CSV/GeoJSON) and AUSTAL input files. The script is experimental and may contain bugs or incomplete features.

- Script location: [open_alaqs/scripts/emissions_austal/run_emissions_austal.py](open_alaqs/scripts/emissions_austal/run_emissions_austal.py). A dedicated README file with detailed instructions with how to use the script is provided in the same folder.

## GSE Application

[(Back to top)](#table-of-contents)

The **GSE (Ground Support Equipment) Application** is a standalone desktop tool for assigning GSE to aircraft movements and calculating emissions. Results can be exported as CSV files or saved back to OpenALAQS database files (.alaqs).



### Running the GSE Application

From the `gse_application` directory, run:

```bash
python gse.py
```

For detailed information on installation, usage, and features, see the [GSE Application README](gse_application/README.md).


## Development
[(Back to top)](#table-of-contents)

1. Clone this repository.
2. Optionally, create a soft link between the local checkout and the QGIS plugin directory for easier developepment. (Linux instructions: `ln -s ${PWD} ${HOME}/.local/share/QGIS/QGIS3/profiles/default/python/plugins/open_alaqs/`).
3. Install [`pre-commit`](https://pre-commit.com).
4. Develop a new feature.
5. Open a PR.
6. Wait for the CI to succeed.
7. Ensure you have a PR approval from another reviewer.
8. Merge the PR.


### Code style

Use pre-commit locally:

```
pip install pre-commit
pre-commit install
```

Use pre-commit-ci autofix in a Pull Request (if the pre-commit-ci check detected some issues):

  + Add the following comment to the PR:

        pre-commit.ci autofix

    Which will create a commit with formatting fixes by pre-commit-ci.


### Debugging

Debugging can be done via [QGIS VSCode Debug plugin](https://plugins.qgis.org/plugins/debug_vs/) and [VSCode](https://code.visualstudio.com).

<details>
<summary>Sample `launch.json`</summary>

```
{
    // Use IntelliSense to learn about possible attributes.
    // Hover to view descriptions of existing attributes.
    // For more information, visit: https://go.microsoft.com/fwlink/?linkid=830387
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Remote Attach",
            "type": "python",
            "request": "attach",
            "port": 5678,
            "host": "localhost",
            "pathMappings": [
                {
                    "localRoot": "${workspaceFolder}/open_alaqs",
                    "remoteRoot": "${HOME}/.local/share/QGIS/QGIS3/profiles/default/python/plugins/open_alaqs/"
                }
            ]
        }
    ]
}
```
</details>


### Updating the OpenALAQS database templates

The plugin produced `.alaqs` files are cloned from a template databases, that are in `./open_alaqs/core/templates/*.alaqs`.
The template databases are generated from SQL and CSV files in the `./open_alaqs/database` directory.
All source files (`.sql` and `.csv`) needed for the build are inside the `./open_alaqs/database/sql` and `./open_alaqs/database/data` folder.
Other scripts and files supporting the creation of the SQL and CSV files are located in `./open_alaqs/database/scripts` and `./open_alaqs/database/src`.

Copy-pastable way to generate the template databases:

```
pipenv run pip install -r requirements.txt
pipenv run python -m open_alaqs.database.generate_templates --full-recreate
```

### Unit tests

To run the tests inside the same environment as they are executed on GitHub,
you need a [Docker](https://www.docker.com) installation.

Once you've installed Docker, go the root of the local repo and run the following commands, which will remove all containers after running the tests:

````
export QGIS_TEST_VERSION=3.40.11 # See https://hub.docker.com/r/qgis/qgis/tags/
docker run --rm -e PYTHONPATH=/usr/share/qgis/python/plugins -v $PWD:/usr/src -w /usr/src qgis/qgis:${QGIS_TEST_VERSION} sh -c 'pip3 install -r requirements.txt || pip3 install -r requirements.txt --break-system-packages;xvfb-run pytest'
````

## Contribute

[(Back to top)](#table-of-contents)

OpenALAQS welcomes all contributions - code or documentation wise.


## License

[(Back to top)](#table-of-contents)

This software is published under European Union Public Licence v. 1.2. [`LICENSE`](LICENSE) with certain amendments described in the [`AMENDMENT_TO_EUPL_license.md`](AMENDMENT_TO_EUPL_license.md) file, reflecting EUROCONTROL's status as an international organisation.

## Contact

[(Back to top)](#table-of-contents)

We'd love to hear from you! If you have any questions, feedback, or inquiries about OpenALAQS, feel free to reach out to us: [open-alaqs@eurocontrol.int](mailto:open-alaqs@eurocontrol.int)

Alternatively, you can visit our [website](https://www.eurocontrol.int/online-tool/airport-local-air-quality-studies) for more information or to fill out our contact form.
