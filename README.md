<!-- Add banner here -->

# Project Title

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

# Demo-Preview

<!-- Add a demo for your project -->

<!-- After you have written about your project, it is a good idea to have a demo/preview(**video/gif/screenshots** are good options) of your project so that people can know what to expect in your project. You could also add the demo in the previous section with the product description.

Here is a random GIF as a placeholder.

![Random GIF](https://media.giphy.com/media/ZVik7pBtu9dNS/giphy.gif) -->

# Table of contents

<!-- After you have introduced your project, it is a good idea to add a **Table of contents** or **TOC** as **cool** people say it. This would make it easier for people to navigate through your README and find exactly what they are looking for.

Here is a sample TOC(*wow! such cool!*) that is actually the TOC for this README. -->

- [Project Title](#project-title)
- [Demo-Preview](#demo-preview)
- [Table of contents](#table-of-contents)
- [Installation](#installation)
    - [Install QGIS](#install-qgis)
    - [Install Open-ALAQS](#install-open-alaqs)
- [Usage](#usage)
- [Development](#development)
    - [Debugging](#debugging)
    - [Updating the UI](#updating-the-ui)
    - [Updating the Open-ALAQS database templates](#updating-the-open-alaqs-database-templates)
- [Contribute](#contribute)
    - [Sponsor](#sponsor)
    - [Adding new features or fixing bugs](#adding-new-features-or-fixing-bugs)
- [License](#license)
- [Footer](#footer)

# Installation
[(Back to top)](#table-of-contents)

<!-- *You might have noticed the **Back to top** button(if not, please notice, it's right there!). This is a good idea because it makes your README **easy to navigate.***

The first one should be how to install(how to generally use your project or set-up for editing in their machine).

This should give the users a concrete idea with instructions on how they can use your project repo with all the steps.

Following this steps, **they should be able to run this in their device.**

A method I use is after completing the README, I go through the instructions from scratch and check if it is working. -->

<!-- Here is a sample instruction:

To use this project, first clone the repo on your device using the command below:

```git init```

```git clone https://github.com/navendu-pottekkat/nsfw-filter.git``` -->

Open-ALAQS is a QGIS plugin, so to install Open-ALAQS, QGIS needs to be installed.
After QGIS is installed, Open-ALAQS can be installed.

## Install QGIS

The simplest way to do this is via the OSGeo4W Network Installer.
You can find the OSGeo4W Network Installer on the QGIS website:

https://qgis.org/en/site/forusers/download.html

Once downloaded, run setup through the `Advanced Install` route.

In the `Select Packages` screen there are multiple packages that need installing:

- qgis-ltr-full (3.22.16-1)
- python3-geopandas (0.11.1-3)
- python3-shapely (1.8.5.post1-1)
- python3-geographiclib (1.50-1)
- python3-pandas (1.1.3-1)
- python3-matplotlib (3.5.1-1)
- spatialite (5.0.1-10)

To find these packages, search for them in the search bar, and find them under the 'Libs' sub-menu and select them such that they are not to be skipped in the installation (previously installed packages are shown as 'Keep' in the 'New' column). For QGIS you should select the latest version in the Desktop and Libs sub-menus.

Now finish the setup by accepting the unmet dependencies and accepting the license agreements.

> Running an old version of QGIS?
> If originally installed using the OSGeo4W Network Installer, the installer can also be used to upgrade to a newer version of QGIS.
> If not installed using the OSGeo4W Network Installer, please uninstall the old version and install the new version using the OSGeo4W Network Installer or follow the installation guide from QGIS.

## Install Open-ALAQS

First, the Open-ALAQS repository needs to be installed in the plugins folder of QGIS.

Depending on how you installed QGIS, you might find it in one of the following locations:

```
# If QGIS installed for all users, you can find the plugins folder here:
YOUR_QGIS_PLUGINS_PATH = C:\users\{YOUR_USER_NAME}\.qgis\python\plugins

# If installed for only yourself the plugins directory can be found here:
YOUR_QGIS_PLUGINS_PATH = C:\users\{YOUR_USER_NAME}\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins

# If filepaths specified above don't exist, the repository can also be placed in:
YOUR_QGIS_PLUGINS_PATH = {YOUR_QGIS_PATH}\apps\qgis\python\plugins
```

Now clone the repository in the plugins folder:

```
# Go to the plugins folder
cd {YOUR_QGIS_PLUGINS_PATH}

# Clone the repository
git clone git@gitlab.aerlabs.nl:eurocontrol/open_alaqs.git
```

The line above uses a git command.
However, it is also possible to get the source code as zip file and extract it in this location.

> Make sure that the Open-ALAQS plugin is located in the folder `{YOUR_QGIS_PLUGINS_PATH}/open_alaqs`, otherwise QGIS might have trouble finding the plugin!

Then start QGIS desktop and find the 'Plugins' button and select 'Manage and Install Plugins', here the Open-ALAQS plugin should be visible and can be activated.

At this point the Open-ALAQS toolbar is visible below the default QGIS toolbars. If this is the case then the installation has been successful.

![img.png](img.png)

# Usage
[(Back to top)](#table-of-contents)

<!-- This is optional and it is used to give the user info on how to use the project after installation. This could be added in the Installation section also. -->

Find a case in the `example\CAEPport` folder.

Load an OpenALAQS project using `example\CAEPport\CAEPport.alaqs`.

# Development
[(Back to top)](#table-of-contents)

<!-- This is the place where you give instructions to developers on how to modify the code.

You could give **instructions in depth** of **how the code works** and how everything is put together.

You could also give specific instructions to how they can setup their development environment.

Ideally, you should keep the README simple. If you need to add more complex explanations, use a wiki. Check out [this wiki](https://github.com/navendu-pottekkat/nsfw-filter/wiki) for inspiration. -->

## Debugging

During debugging, it's sometimes hard to understand when certain calls are made.
The following code sample can help to better understand where and when code is executed.

```python
from inspect import getframeinfo, currentframe

from open_alaqs.core.alaqslogging import get_logger

logger = get_logger(__name__)

# The line below is printed in the logs and informs you about the location of the code
logger.debug(f"{getframeinfo(currentframe())}")
```

In addition, the following wrapper can be used to track what's going in functions.
It can easily be extended to track the execution time of functions as well.

```python
from open_alaqs.core.alaqslogging import get_logger

logger = get_logger(__name__)

def log_activity(f):
    """
    Decorator to log activity

    :param f: function to execute
    :return:
    """

    def wrapper(*args, **kwargs):
        logger.debug(f"{f.__name__}(*args, **kwargs) with")
        logger.debug(f"\targs={args}")
        logger.debug(f"\tkwargs={kwargs}")
        return f(*args, **kwargs)

    return wrapper

@log_activity
def log_activity_of_this_function(random, argument, with_defaults='also supported'):
    pass
```

## Updating the UI

If you want to edit the UI, install [pyqt-tools](https://github.com/altendky/pyqt-tools) using `pip install pyqt5-tools~=5.15` and start the designer using `pyqt5-tools designer`.
After making changes to any `ui/ui_*.ui` files, you should update the matching `ui/ui_*.py` file by executing the pyuic5 command.
For example, the following command should be used to update the about widget:

```shell
pyuic5 -o ui/ui_about.py --from-imports ui/ui_about.ui
```

> Pro tip: if you want to view the interface without running QGIS, you can use the following command: `pyuic5 --preview ui/ui_about.ui`

## Updating the Open-ALAQS database templates

The plugin produced `.alaqs` files are cloned from a template databases, that are in `./open_alaqs/core/templates/*.alaqs`.
The template databases are generated from SQL and CSV files in the `./open_alaqs/database` directory.
All source files (`.sql` and `.csv`) needed for the build are inside the `./open_alaqs/database/sql` and `./open_alaqs/database/data` folder.
Other scripts and files supporting the creation of the SQL and CSV files are located in `./open_alaqs/database/scripts` and `./open_alaqs/database/src`.

Copy-pastable way to generate the template databases:

```
pipenv run pip install -r dev_requirements.txt
pipenv run python -m open_alaqs.database.generate_templates
```

To generate the CAEP examples, run the following command in the Python console in QGIS:

```python
from open_alaqs.database.create_caep_examples import create_caep_examples
create_caep_examples()
```

# Contribute
[(Back to top)](#table-of-contents)

<!-- This is where you can let people know how they can **contribute** to your project. Some of the ways are given below.

Also this shows how you can add subsections within a section. -->

### Sponsor
[(Back to top)](#table-of-contents)

<!-- Your project is gaining traction and it is being used by thousands of people(***with this README there will be even more***). Now it would be a good time to look for people or organisations to sponsor your project. This could be because you are not generating any revenue from your project and you require money for keeping the project alive.

You could add how people can sponsor your project in this section. Add your patreon or GitHub sponsor link here for easy access.

A good idea is to also display the sponsors with their organisation logos or badges to show them your love!(*Someday I will get a sponsor and I can show my love*) -->

### Adding new features or fixing bugs
[(Back to top)](#table-of-contents)

<!-- This is to give people an idea how they can raise issues or feature requests in your projects.

You could also give guidelines for submitting and issue or a pull request to your project.

Personally and by standard, you should use a [issue template](https://github.com/navendu-pottekkat/nsfw-filter/blob/master/ISSUE_TEMPLATE.md) and a [pull request template](https://github.com/navendu-pottekkat/nsfw-filter/blob/master/PULL_REQ_TEMPLATE.md)(click for examples) so that when a user opens a new issue they could easily format it as per your project guidelines.

You could also add contact details for people to get in touch with you regarding your project. -->

# License
[(Back to top)](#table-of-contents)

<!-- Adding the license to README is a good practice so that people can easily refer to it.

Make sure you have added a LICENSE file in your project folder. **Shortcut:** Click add new file in your root of your repo in GitHub > Set file name to LICENSE > GitHub shows LICENSE templates > Choose the one that best suits your project!

I personally add the name of the license and provide a link to it like below. -->

[GNU General Public License version 3](https://opensource.org/licenses/GPL-3.0)

# Footer
[(Back to top)](#table-of-contents)

<!-- Let's also add a footer because I love footers and also you **can** use this to convey important info.

Let's make it an image because by now you have realised that multimedia in images == cool(*please notice the subtle programming joke). -->

Leave a star in GitHub, give a clap in Medium and share this guide if you found this helpful.

<!-- Add the footer here -->

<!-- ![Footer](https://github.com/navendu-pottekkat/awesome-readme/blob/master/fooooooter.png) -->
