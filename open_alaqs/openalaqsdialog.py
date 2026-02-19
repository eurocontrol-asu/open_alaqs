# -*- coding: utf-8 -*-
"""
/***************************************************************************
 OpenALAQSDialog
                                 A QGIS plugin
 An open source version of the ALAQS project
                             -------------------
        copyright            : (C) 2019 by EUROCONTROL
        email                : open-alaqs@eurocontrol.int
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
import csv
import shutil

import geopandas as gpd
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsExpression,
    QgsFeatureRequest,
    QgsMapLayer,
    QgsProject,
    QgsSettings,
    QgsTextAnnotation,
    QgsVectorLayer,
    QgsVectorLayerUtils,
)
from qgis.core.additions.edit import edit
from qgis.gui import QgsDoubleSpinBox, QgsFileWidget, QgsMessageBar
from qgis.PyQt import QtCore, QtGui, QtWidgets
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QMessageBox, QSpacerItem, QSizePolicy
from qgis.PyQt.uic import loadUiType
from qgis.utils import OverrideCursor

from open_alaqs import openalaqsuitoolkit as oautk
from open_alaqs.alaqs_config import LAYERS_CONFIG
from open_alaqs.core import alaqs, alaqsutils
from open_alaqs.core.alaqsdblite import (
    ProjectDatabase,
    delete_records,
    get_inventory_timestamps,
    get_min_max_timestamps,
    is_output_db_file,
)
from open_alaqs.core.alaqslogging import get_logger, log_path
from open_alaqs.core.EmissionCalculation import EmissionCalculation, GridConfig
from open_alaqs.core.EmissionCalculatorService import (
    EmissionCalculationConfig,
    EmissionCalculatorService,
)
from open_alaqs.core.interfaces.Emissions import PollutantType
from open_alaqs.core.modules.ModuleConfigurationWidget import ModuleConfigurationWidget
from open_alaqs.core.modules.ModuleManager import (
    DispersionModuleRegistry,
    OutputAnalysisModuleRegistry,
    OutputDispersionModuleRegistry,
    SourceModuleRegistry,
)
from open_alaqs.core.tools import conversion
from open_alaqs.core.tools.Grid3D import Grid3D
from open_alaqs.core.tools.austal_csv_generation import generate_austal_from_csv
from open_alaqs.core.tools.csv_interface import (
    read_csv_to_dict,
    read_csv_to_geodataframe,
)
from open_alaqs.core.utils.osm import download_osm_airport_data
from open_alaqs.core.utils.qt import populate_combobox
from open_alaqs.enums import AlaqsLayerType
import re

logger = get_logger(__name__)


class Austal2000RunError(Exception):
    pass


def catch_errors(f):
    """
    Decorator to catch all errors when executing the function.
    This decorator catches errors and writes them to the log.

    :param f: function to execute
    :return:
    """

    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            alaqsutils.print_error(f.__name__, Exception, e)

    return wrapper


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


class OpenAlaqsAbout(QtWidgets.QDialog):
    """
    This class provides a dialog that presents a summary of the Open ALAQS
    project.
    """

    def __init__(self, iface):
        """
        Initialises QDialog that displays the about UI for the plugin.
        """
        main_window = iface.mainWindow() if iface is not None else None
        QtWidgets.QDialog.__init__(self, main_window)

        Ui_DialogAbout, _ = loadUiType(
            os.path.join(os.path.dirname(__file__), "ui", "ui_about.ui")
        )
        self.ui = Ui_DialogAbout()
        self.ui.setupUi(self)
        self.iface = iface
        # self.ui.AddWatermarkButton.clicked.connect(self.addWatermark)


class OpenAlaqsOpenDatabase:
    """
    This class defines the 'open existing database' functionality.
    """

    def __init__(self, iface):
        self.iface = iface
        self.canvas = self.iface.mapCanvas()

        # define some variables that are used throughout the class
        self.db_path = None

    def load_database(self):
        """
        Open file dialog and browse for an existing alaqs database, then try
        and load the database file into QGIS
        """
        filename, _filter = QtWidgets.QFileDialog.getOpenFileName(
            None, "Open an ALAQS database file", "", "(*.alaqs)"
        )

        try:
            if os.path.exists(filename) and os.path.isfile(filename):
                self.db_path = filename
                # Store the database in-memory for future use
                project_database = ProjectDatabase()
                project_database.path = self.db_path

                with OverrideCursor(Qt.CursorShape.WaitCursor):
                    result = alaqs.load_study_setup()

                study_data = alaqs.load_study_setup()
                if study_data:
                    oautk.set_default_zoom(
                        self.canvas,
                        study_data["airport_latitude"],
                        study_data["airport_longitude"],
                    )

                if result is not None:
                    return True
                else:
                    return False
        except Exception as e:
            error_message = "Could not open database file:  %s." % e
            QtWidgets.QMessageBox.warning(
                self.iface.mainWindow(), "Error", error_message
            )
            return False

    def get_database_path(self):
        return self.db_path


class OpenAlaqsStudySetup(QtWidgets.QDialog):
    """
    This class defines the various methods used in setting and updating the
    'Study Setup' UI. This includes taking existing data from the project data
    (if available) and making updates to the data if it changes.
    """

    def __init__(self, iface):
        main_window = iface.mainWindow() if iface is not None else None
        QtWidgets.QDialog.__init__(self, main_window)

        # Setup the user interface from Designer
        Ui_DialogStudySetup, _ = loadUiType(
            os.path.join(os.path.dirname(__file__), "ui", "ui_study_setup.ui")
        )
        self.ui = Ui_DialogStudySetup()
        self.ui.setupUi(self)

        self.iface = iface

        self.ui.comboBoxAirportCode.addItem("")
        for airport in alaqs.get_airport_codes():
            self.ui.comboBoxAirportCode.addItem(airport["airport_code"])

        # Define some of the variables that are used throughout the class
        self.project_name = None
        self.airport_name = None
        self.airport_id = None
        self.icao_code = None
        self.airport_latitude = None
        self.airport_longitude = None
        self.airport_country = None
        self.airport_elevation = None
        self.airport_temperature = None
        self.parking_method = None
        self.roadway_method = None
        self.roadway_country = None
        self.roadway_fleet_year = None
        self.vertical_limit = None
        self.study_info = None

        self.load_study_data()

        self.ui.comboBoxAirportCode.currentTextChanged.connect(self.airport_lookup)

        self.ui.buttonBox.button(
            QtWidgets.QDialogButtonBox.StandardButton.Save
        ).clicked.connect(self.save_study_setup)
        self.ui.buttonBox.button(
            QtWidgets.QDialogButtonBox.StandardButton.Close
        ).clicked.connect(self.close)

    def load_study_data(self):
        """
        This function loads an existing study from a Spatialite database into
        the QGIS environment.
        """
        result = alaqs.load_study_setup()
        if (result is not None) and (result != []):
            # try and load stuff into the UI
            study_data = result

            self.ui.lineEditProjectName.setText(study_data["project_name"])
            self.ui.lineEditAirportName.setText(study_data["airport_name"])
            self.ui.lineEditAirportID.setText(str(study_data["oid"]))
            self.ui.lineEditAirportID.setEnabled(False)
            self.ui.comboBoxAirportCode.setCurrentText(study_data["airport_code"])
            self.ui.lineEditAirportCountry.setText(study_data["airport_country"])
            self.ui.spinBoxAirportLatitude.setValue(study_data["airport_latitude"])
            self.ui.spinBoxAirportLongitude.setValue(study_data["airport_longitude"])
            self.ui.spinBoxAirportElevation.setValue(study_data["airport_elevation"])
            self.ui.spinBoxAirportTemperature.setValue(
                study_data["airport_temperature"]
            )
            # TODO OPENGIS.ch: remove the Vertical limit from the form, use the one in the Emission Inventory Analysis only
            self.ui.spinBoxVerticalLimit.setValue(study_data["vertical_limit"])

            populate_combobox(
                self.ui.comboBoxRoadwayMethod,
                alaqs.get_roadway_methods(),
            )
            populate_combobox(
                self.ui.comboBoxRoadwayFleetYear,
                (str(r["fleet_year"]) for r in alaqs.get_roadway_fleet_years()),
                study_data["roadway_country"],
                "2020",
            )
            populate_combobox(
                self.ui.comboBoxRoadwayCountry,
                (str(r["country"]) for r in alaqs.get_roadway_countries()),
                study_data["roadway_country"],
                "EU27",
            )

            self.ui.textEditStudyInformation.setPlainText(study_data["study_info"])

            try:
                date_created = datetime.datetime.fromisoformat(
                    study_data["date_created"]
                )
            except Exception:
                date_created = datetime.now()

            try:
                date_modified = datetime.datetime.fromisoformat(
                    study_data["date_modified"]
                )
            except Exception:
                date_modified = datetime.now()

            self.ui.labelDateCreated.setText(
                date_created.isoformat(sep=" ", timespec="seconds")
            )
            self.ui.labelDateModified.setText(
                date_modified.isoformat(sep=" ", timespec="seconds")
            )
        else:
            # load some defaults
            raise Exception("Could not load study setup.")

    def airport_lookup(self):
        """
        This function looks up airport details (name, lat, lon, country) based
        on an ICAO code and fills in the study setup UI accordingly.
        """
        airport_code = self.ui.comboBoxAirportCode.currentText()
        if len(airport_code) == 4:
            # Look up that ICAO code in the ALAQS database
            airport_data = alaqs.airport_lookup(airport_code)
            if airport_data and not isinstance(airport_data, str):
                self.ui.lineEditAirportName.setText(airport_data["airport_name"])
                self.ui.lineEditAirportCountry.setText(airport_data["airport_country"])
                self.ui.spinBoxAirportLatitude.setValue(
                    airport_data["airport_latitude"]
                )
                self.ui.spinBoxAirportLongitude.setValue(
                    airport_data["airport_longitude"]
                )
                self.ui.spinBoxAirportElevation.setValue(
                    int(airport_data["airport_elevation"] * 0.3048)
                )  # in meters from ft

                oautk.set_default_zoom(
                    self.iface.mapCanvas(),
                    airport_data["airport_latitude"],
                    airport_data["airport_longitude"],
                )

    def save_study_setup(self):
        """
        Saves any updates to the study setup back to the study database.
        """
        # Collect form information
        self.project_name = oautk.validate_field(self.ui.lineEditProjectName, "str")
        self.airport_name = oautk.validate_field(self.ui.lineEditAirportName, "str")
        self.airport_id = oautk.validate_field(self.ui.lineEditAirportID, "str")
        self.icao_code = oautk.validate_field(self.ui.comboBoxAirportCode, "str")
        self.airport_country = oautk.validate_field(
            self.ui.lineEditAirportCountry, "str"
        )
        self.airport_latitude = self.ui.spinBoxAirportLatitude.value()
        self.airport_longitude = self.ui.spinBoxAirportLongitude.value()
        self.airport_elevation = self.ui.spinBoxAirportElevation.value()
        self.airport_temperature = self.ui.spinBoxAirportTemperature.value()
        self.vertical_limit = self.ui.spinBoxVerticalLimit.value()
        self.roadway_method = oautk.validate_field(self.ui.comboBoxRoadwayMethod, "str")
        self.roadway_fleet_year = oautk.validate_field(
            self.ui.comboBoxRoadwayFleetYear, "int"
        )
        self.roadway_country = oautk.validate_field(
            self.ui.comboBoxRoadwayCountry, "str"
        )
        self.study_info = str(self.ui.textEditStudyInformation.toPlainText())
        if self.study_info == "":
            self.study_info = "Not set"

        study_setup = {
            "project_name": self.project_name,
            "airport_name": self.airport_name,
            "airport_id": self.airport_id,
            "airport_code": self.icao_code,
            "airport_country": self.airport_country,
            "airport_latitude": self.airport_latitude,
            "airport_longitude": self.airport_longitude,
            "airport_elevation": self.airport_elevation,
            "airport_temperature": self.airport_temperature,
            "vertical_limit": self.vertical_limit,
            "parking_method": self.parking_method,
            "roadway_method": self.roadway_method,
            "roadway_fleet_year": self.roadway_fleet_year,
            "roadway_country": self.roadway_country,
            "study_info": self.study_info,
        }

        # Check for values that failed validation
        for value in study_setup:
            if value is False:
                QtWidgets.QMessageBox.information(
                    self, "Information", "Please correct input parameters"
                )
                return

        result = alaqs.save_study_setup(study_setup)
        if result is None:
            self.hide()
            self.get_values()
            return None
        else:
            QtWidgets.QMessageBox.warning(
                self, "Study Setup", "Update Unsuccessful: %s" % result
            )
            return result

    def get_values(self):
        """
        returns the airport name back to the main openalaqs class
        """
        return self.airport_name


class OpenAlaqsProfiles(QtWidgets.QDialog):
    """
    Creates a dialog used to create and manage activity profiles within ALAQS
    """

    def __init__(self, iface):
        QtWidgets.QWidget.__init__(self, None, Qt.WindowType.WindowStaysOnTopHint)

        # Build the UI
        Ui_FormProfiles, _ = loadUiType(
            os.path.join(os.path.dirname(__file__), "ui", "ui_profiles_widget.ui")
        )
        self.ui = Ui_FormProfiles()
        self.ui.setupUi(self)

        # Collect some UI components
        self.iface = iface
        self.canvas = self.iface.mapCanvas()

        # Bindings
        self.ui.comboBoxHourlyName.currentIndexChanged.connect(
            self.change_hourly_profile
        )
        self.ui.pushButtonHourlyDelete.clicked.connect(self.delete_hourly_profile)
        self.ui.pushButtonHourlyNew.clicked.connect(self.new_hourly_profile)
        self.ui.pushButtonHourlySave.clicked.connect(self.save_hourly_profile)
        self.ui.pushButtonHourlyClear.clicked.connect(self.clear_hourly_profile)

        self.ui.comboBoxDailyName.currentIndexChanged.connect(self.change_daily_profile)
        self.ui.pushButtonDailyDelete.clicked.connect(self.delete_daily_profile)
        self.ui.pushButtonDailyNew.clicked.connect(self.new_daily_profile)
        self.ui.pushButtonDailySave.clicked.connect(self.save_daily_profile)
        self.ui.pushButtonDailyClear.clicked.connect(self.clear_daily_profile)

        self.ui.comboBoxMonthlyName.currentIndexChanged.connect(
            self.change_monthly_profile
        )
        self.ui.pushButtonMonthlyDelete.clicked.connect(self.delete_monthly_profile)
        self.ui.pushButtonMonthlyNew.clicked.connect(self.new_monthly_profile)
        self.ui.pushButtonMonthlySave.clicked.connect(self.save_monthly_profile)
        self.ui.pushButtonMonthlyClear.clicked.connect(self.clear_monthly_profile)

        # Populate the comboBox menus
        self.populate_hourly_profiles()
        self.populate_daily_profiles()
        self.populate_monthly_profiles()

    @catch_errors
    def populate_hourly_profiles(self):
        """
        Gets a list of hourly profiles from current database and populate
        """
        profiles = alaqs.get_hourly_profiles()
        self.ui.comboBoxHourlyName.clear()
        if (profiles is None) or (profiles == []):
            return None
        else:
            for profile in profiles:
                self.ui.comboBoxHourlyName.addItem(profile[1])
            self.ui.comboBoxHourlyName.setCurrentIndex(0)
            self.ui.comboBoxHourlyName.setEditable(False)
            return None

    @catch_errors
    def populate_daily_profiles(self):
        """
        Gets a list of daily profiles from current database and populate
        """
        profiles = alaqs.get_daily_profiles()
        self.ui.comboBoxDailyName.clear()
        if (profiles is None) or (profiles == []):
            return None
        else:
            for profile in profiles:
                self.ui.comboBoxDailyName.addItem(profile[1])
            self.ui.comboBoxDailyName.setCurrentIndex(0)
            self.ui.comboBoxDailyName.setEditable(False)

    @catch_errors
    def populate_monthly_profiles(self):
        """
        Gets a list of daily profiles from current database and populate
        """
        profiles = alaqs.get_monthly_profiles()
        self.ui.comboBoxMonthlyName.clear()
        if (profiles is None) or (profiles == []):
            return None
        else:
            for profile in profiles:
                self.ui.comboBoxMonthlyName.addItem(profile[1])
            self.ui.comboBoxMonthlyName.setCurrentIndex(0)
            self.ui.comboBoxMonthlyName.setEditable(False)

    @catch_errors
    def change_hourly_profile(self, profile_id):
        """
        This reloads the profile UI to show the currently selected hourly
        profile in the UI.

        :param profile_id: the unique ID of the hourly profile to be displayed
        :return: :raise Exception:
        """
        if str(profile_id).strip() == "":
            self.clear_hourly_profile()
            return None

        profile_data = alaqs.get_hourly_profile(profile_id)
        if isinstance(profile_data, str):
            raise Exception(profile_data)
        elif profile_data is None:
            return None
        else:
            self.ui.lineEditHourly00.setText(str(profile_data[0][2]))
            self.ui.lineEditHourly01.setText(str(profile_data[0][3]))
            self.ui.lineEditHourly02.setText(str(profile_data[0][4]))
            self.ui.lineEditHourly03.setText(str(profile_data[0][5]))
            self.ui.lineEditHourly04.setText(str(profile_data[0][6]))
            self.ui.lineEditHourly05.setText(str(profile_data[0][7]))
            self.ui.lineEditHourly06.setText(str(profile_data[0][8]))
            self.ui.lineEditHourly07.setText(str(profile_data[0][9]))
            self.ui.lineEditHourly08.setText(str(profile_data[0][10]))
            self.ui.lineEditHourly09.setText(str(profile_data[0][11]))
            self.ui.lineEditHourly10.setText(str(profile_data[0][12]))
            self.ui.lineEditHourly11.setText(str(profile_data[0][13]))
            self.ui.lineEditHourly12.setText(str(profile_data[0][14]))
            self.ui.lineEditHourly13.setText(str(profile_data[0][15]))
            self.ui.lineEditHourly14.setText(str(profile_data[0][16]))
            self.ui.lineEditHourly15.setText(str(profile_data[0][17]))
            self.ui.lineEditHourly16.setText(str(profile_data[0][18]))
            self.ui.lineEditHourly17.setText(str(profile_data[0][19]))
            self.ui.lineEditHourly18.setText(str(profile_data[0][20]))
            self.ui.lineEditHourly19.setText(str(profile_data[0][21]))
            self.ui.lineEditHourly20.setText(str(profile_data[0][22]))
            self.ui.lineEditHourly21.setText(str(profile_data[0][23]))
            self.ui.lineEditHourly22.setText(str(profile_data[0][24]))
            self.ui.lineEditHourly23.setText(str(profile_data[0][25]))
            return None

    @catch_errors
    def change_daily_profile(self, profile_id):
        """
        This reloads the profile UI to show the currently selected daily profile
        in the UI.

        :param profile_id: the unique ID of the daily profile to be displayed
        """
        if str(profile_id).strip() == "":
            self.clear_daily_profile()
            return None
        profile_data = alaqs.get_daily_profile(profile_id)
        if isinstance(profile_data, str):
            raise Exception(profile_data)
        elif profile_data is None:
            return None
        else:
            self.ui.lineEditDailyMon.setText(str(profile_data[0][2]))
            self.ui.lineEditDailyTues.setText(str(profile_data[0][3]))
            self.ui.lineEditDailyWed.setText(str(profile_data[0][4]))
            self.ui.lineEditDailyThurs.setText(str(profile_data[0][5]))
            self.ui.lineEditDailyFri.setText(str(profile_data[0][6]))
            self.ui.lineEditDailySat.setText(str(profile_data[0][7]))
            self.ui.lineEditDailySun.setText(str(profile_data[0][8]))
            return None

    @catch_errors
    def change_monthly_profile(self, profile_id):
        """
        This reloads the profile UI to show the currently selected monthly
        profile in the UI.

        :param profile_id: the unique ID of the monthly profile to be displayed
        """
        if str(profile_id).strip() == "":
            self.clear_monthly_profile()
            return None
        profile_data = alaqs.get_monthly_profile(profile_id)
        if isinstance(profile_data, str):
            raise Exception(profile_data)
        elif profile_data is None:
            return None
        else:
            self.ui.lineEditMonthlyJan.setText(str(profile_data[0][2]))
            self.ui.lineEditMonthlyFeb.setText(str(profile_data[0][3]))
            self.ui.lineEditMonthlyMar.setText(str(profile_data[0][4]))
            self.ui.lineEditMonthlyApr.setText(str(profile_data[0][5]))
            self.ui.lineEditMonthlyMay.setText(str(profile_data[0][6]))
            self.ui.lineEditMonthlyJun.setText(str(profile_data[0][7]))
            self.ui.lineEditMonthlyJul.setText(str(profile_data[0][8]))
            self.ui.lineEditMonthlyAug.setText(str(profile_data[0][9]))
            self.ui.lineEditMonthlySep.setText(str(profile_data[0][10]))
            self.ui.lineEditMonthlyOct.setText(str(profile_data[0][11]))
            self.ui.lineEditMonthlyNov.setText(str(profile_data[0][12]))
            self.ui.lineEditMonthlyDec.setText(str(profile_data[0][13]))
            return None

    def confirm_profile_deletion(self):
        result = QtWidgets.QMessageBox.warning(
            self,
            "Delete Profiles",
            "Are you sure you want to delete this profile?",
            QtWidgets.QMessageBox.StandardButton.Yes,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        return result != QtWidgets.QMessageBox.StandardButton.Yes

    def delete_hourly_profile(self):
        """
        This removes an hourly profile from the currently active ALAQS database.
        """
        if self.confirm_profile_deletion():
            return

        profile_name = self.ui.comboBoxHourlyName.currentText().strip()

        delete_records("user_hour_profile", {"profile_name": profile_name})
        self.populate_hourly_profiles()

    def delete_daily_profile(self):
        """
        This removes a daily profile from the currently active ALAQS database.
        """
        if self.confirm_profile_deletion():
            return

        profile_name = self.ui.comboBoxDailyName.currentText().strip()

        delete_records("user_day_profile", {"profile_name": profile_name})
        self.populate_daily_profiles()

    def delete_monthly_profile(self):
        """
        This removes an monthly profile from the currently active ALAQS database.
        """
        if self.confirm_profile_deletion():
            return

        profile_name = self.ui.comboBoxMonthlyName.currentText().strip()

        delete_records("user_month_profile", {"profile_name": profile_name})
        self.populate_monthly_profiles()

    @catch_errors
    def new_hourly_profile(self, _checked: bool) -> None:
        """
        This adds a new blank hourly profile to the UI
        :return: None if successful; error message as a string if its
         unsuccessful
        """
        self.clear_hourly_profile()
        self.ui.comboBoxHourlyName.addItem("New Profile")
        index = self.ui.comboBoxHourlyName.count()
        self.ui.comboBoxHourlyName.setCurrentIndex(index - 1)
        self.ui.comboBoxHourlyName.setEditable(True)
        return None

    @catch_errors
    def new_daily_profile(self, _checked: bool) -> None:
        """
        This adds a new blank daily profile to the UI
        :return: None if successful; error message as a string if its
         unsuccessful
        """
        self.clear_daily_profile()
        self.ui.comboBoxDailyName.addItem("New Profile")
        index = self.ui.comboBoxDailyName.count()
        self.ui.comboBoxDailyName.setCurrentIndex(index - 1)
        self.ui.comboBoxDailyName.setEditable(True)
        return None

    @catch_errors
    def new_monthly_profile(self, _checked: bool) -> None:
        """
        Adds a new blank monthly profile to the UI
        :return: None if successful; error message as a string if its
         unsuccessful
        """
        self.clear_monthly_profile()
        self.ui.comboBoxMonthlyName.addItem("New Profile")
        index = self.ui.comboBoxMonthlyName.count()
        self.ui.comboBoxMonthlyName.setCurrentIndex(index - 1)
        self.ui.comboBoxMonthlyName.setEditable(True)

    @catch_errors
    def save_hourly_profile(self, checked=False):
        """
        Takes data from the UI and saves a new hourly profile to the currently
         active ALAQS database
        :return:
        """
        profile_name = oautk.validate_field(self.ui.comboBoxHourlyName, "str")
        h00 = oautk.validate_field(self.ui.lineEditHourly00, "float")
        h01 = oautk.validate_field(self.ui.lineEditHourly01, "float")
        h02 = oautk.validate_field(self.ui.lineEditHourly02, "float")
        h03 = oautk.validate_field(self.ui.lineEditHourly03, "float")
        h04 = oautk.validate_field(self.ui.lineEditHourly04, "float")
        h05 = oautk.validate_field(self.ui.lineEditHourly05, "float")
        h06 = oautk.validate_field(self.ui.lineEditHourly06, "float")
        h07 = oautk.validate_field(self.ui.lineEditHourly07, "float")
        h08 = oautk.validate_field(self.ui.lineEditHourly08, "float")
        h09 = oautk.validate_field(self.ui.lineEditHourly09, "float")
        h10 = oautk.validate_field(self.ui.lineEditHourly10, "float")
        h11 = oautk.validate_field(self.ui.lineEditHourly11, "float")
        h12 = oautk.validate_field(self.ui.lineEditHourly12, "float")
        h13 = oautk.validate_field(self.ui.lineEditHourly13, "float")
        h14 = oautk.validate_field(self.ui.lineEditHourly14, "float")
        h15 = oautk.validate_field(self.ui.lineEditHourly15, "float")
        h16 = oautk.validate_field(self.ui.lineEditHourly16, "float")
        h17 = oautk.validate_field(self.ui.lineEditHourly17, "float")
        h18 = oautk.validate_field(self.ui.lineEditHourly18, "float")
        h19 = oautk.validate_field(self.ui.lineEditHourly19, "float")
        h20 = oautk.validate_field(self.ui.lineEditHourly20, "float")
        h21 = oautk.validate_field(self.ui.lineEditHourly21, "float")
        h22 = oautk.validate_field(self.ui.lineEditHourly22, "float")
        h23 = oautk.validate_field(self.ui.lineEditHourly23, "float")

        properties = [
            profile_name,
            h00,
            h01,
            h02,
            h03,
            h04,
            h05,
            h06,
            h07,
            h08,
            h09,
            h10,
            h11,
            h12,
            h13,
            h14,
            h15,
            h16,
            h17,
            h18,
            h19,
            h20,
            h21,
            h22,
            h23,
        ]

        for value in properties:
            if value is False:
                QtWidgets.QMessageBox.warning(
                    self, "Error", "Please correct all input fields"
                )
                return

        for value in properties[1:]:
            if value > 1:
                QtWidgets.QMessageBox.warning(
                    self, "Error", "Profile values cannot be greater than 1"
                )
                return

        pass_check = False
        for value in properties[1:]:
            if value == 1:
                pass_check = True
        if pass_check is False:
            QtWidgets.QMessageBox.warning(
                self, "Error", "At least one profile value must be equal to 1"
            )
            return

        if profile_name == "New Profile":
            QtWidgets.QMessageBox.warning(
                self, "Error", "Profile name cannot be 'New Profile'"
            )
            return

        answer = QtWidgets.QMessageBox.information(
            self,
            "New Profile",
            "Are you sure you want to save changes to this profile?",
            QtWidgets.QMessageBox.StandardButton.Yes,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if answer == QtWidgets.QMessageBox.StandardButton.Yes:
            # Commit to database
            result = alaqs.add_hourly_profile(properties)
            if result is None:
                self.populate_hourly_profiles()
                return None
            else:
                QtWidgets.QMessageBox.warning(
                    self, "New profile", "Profile could not be saved: %s" % result
                )
                return None

    def save_daily_profile(self, checked=False):
        """
        Takes data from the UI and saves a new daily profile to the currently
        active ALAQS database.

        :return: None if successful; error message as a string if its
         unsuccessful
        """

        profile_name = oautk.validate_field(self.ui.comboBoxDailyName, "str")
        mon = oautk.validate_field(self.ui.lineEditDailyMon, "float")
        tue = oautk.validate_field(self.ui.lineEditDailyTues, "float")
        wed = oautk.validate_field(self.ui.lineEditDailyWed, "float")
        thu = oautk.validate_field(self.ui.lineEditDailyThurs, "float")
        fri = oautk.validate_field(self.ui.lineEditDailyFri, "float")
        sat = oautk.validate_field(self.ui.lineEditDailySat, "float")
        sun = oautk.validate_field(self.ui.lineEditDailySun, "float")

        properties = [profile_name, mon, tue, wed, thu, fri, sat, sun]

        for value in properties:
            if value is False:
                QtWidgets.QMessageBox.warning(
                    self, "New Profile", "Please correct all input values"
                )
                return None

        for value in properties[2:]:
            if value > 1:
                QtWidgets.QMessageBox.warning(
                    self, "Error", "Profile values cannot be greater than 1"
                )
                return

        pass_check = False
        for value in properties[2:]:
            if value == 1:
                pass_check = True
        if pass_check is False:
            QtWidgets.QMessageBox.warning(
                self, "Error", "At least one profile value must be equal to 1"
            )
            return

        if profile_name == "New Profile":
            QtWidgets.QMessageBox.warning(
                self, "New Profile", "Profile name cannot be 'New Profile'"
            )
            return None

        answer = QtWidgets.QMessageBox.warning(
            self,
            "New Profile",
            "Are you sure you want to save changes to this profile?",
            QtWidgets.QMessageBox.StandardButton.Yes,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if answer == QtWidgets.QMessageBox.Yes:
            # Commit to database
            result = alaqs.add_daily_profile(properties)
            if result is None:
                self.populate_daily_profiles()
                return None
            else:
                QtWidgets.QMessageBox.warning(
                    self, "New profile", "Profile could not be saved: %s" % result
                )
                return None

    def save_monthly_profile(self, checked=False):
        """
        Takes data from the UI and saves a new monthly profile to the currently
         active ALAQS database
        :return: None if successful; error message as a string if its
         unsuccessful
        """

        profile_name = oautk.validate_field(self.ui.comboBoxMonthlyName, "str")
        january = oautk.validate_field(self.ui.lineEditMonthlyJan, "float")
        february = oautk.validate_field(self.ui.lineEditMonthlyFeb, "float")
        march = oautk.validate_field(self.ui.lineEditMonthlyMar, "float")
        april = oautk.validate_field(self.ui.lineEditMonthlyApr, "float")
        may = oautk.validate_field(self.ui.lineEditMonthlyMay, "float")
        june = oautk.validate_field(self.ui.lineEditMonthlyJun, "float")
        july = oautk.validate_field(self.ui.lineEditMonthlyJul, "float")
        august = oautk.validate_field(self.ui.lineEditMonthlyAug, "float")
        september = oautk.validate_field(self.ui.lineEditMonthlySep, "float")
        october = oautk.validate_field(self.ui.lineEditMonthlyOct, "float")
        november = oautk.validate_field(self.ui.lineEditMonthlyNov, "float")
        december = oautk.validate_field(self.ui.lineEditMonthlyDec, "float")

        properties = [
            profile_name,
            january,
            february,
            march,
            april,
            may,
            june,
            july,
            august,
            september,
            october,
            november,
            december,
        ]

        for value in properties:
            if value is False:
                QtWidgets.QMessageBox.warning(
                    self, "New Profile", "Please complete all input values"
                )
                return None

        if profile_name == "New Profile":
            QtWidgets.QMessageBox.warning(
                self, "New Profile", "Profile name cannot be 'New Profile'"
            )
            return None

        for value in properties[2:]:
            if value > 1:
                QtWidgets.QMessageBox.warning(
                    self, "Error", "Profile values cannot be greater than 1"
                )
                return

        pass_check = False
        for value in properties[2:]:
            if value == 1:
                pass_check = True
        if pass_check is False:
            QtWidgets.QMessageBox.warning(
                self, "Error", "At least one profile value must be equal to 1"
            )
            return

        answer = QtWidgets.QMessageBox.warning(
            self,
            "New Profile",
            "Are you sure you want to save changes to this profile?",
            QtWidgets.QMessageBox.Yes,
            QtWidgets.QMessageBox.No,
        )

        if answer == QtWidgets.QMessageBox.Yes:
            # Commit to database
            result = alaqs.add_monthly_profile(properties)
            if result is None:
                self.populate_monthly_profiles()
                return None
            else:
                QtWidgets.QMessageBox.warning(
                    self, "New profile", "Profile could not be saved: %s" % result
                )
                return None

    @catch_errors
    def clear_hourly_profile(self, checked=False):
        self.ui.lineEditHourly00.setText("")
        self.ui.lineEditHourly01.setText("")
        self.ui.lineEditHourly02.setText("")
        self.ui.lineEditHourly03.setText("")
        self.ui.lineEditHourly04.setText("")
        self.ui.lineEditHourly05.setText("")
        self.ui.lineEditHourly06.setText("")
        self.ui.lineEditHourly07.setText("")
        self.ui.lineEditHourly08.setText("")
        self.ui.lineEditHourly09.setText("")
        self.ui.lineEditHourly10.setText("")
        self.ui.lineEditHourly11.setText("")
        self.ui.lineEditHourly12.setText("")
        self.ui.lineEditHourly13.setText("")
        self.ui.lineEditHourly14.setText("")
        self.ui.lineEditHourly15.setText("")
        self.ui.lineEditHourly16.setText("")
        self.ui.lineEditHourly17.setText("")
        self.ui.lineEditHourly18.setText("")
        self.ui.lineEditHourly19.setText("")
        self.ui.lineEditHourly20.setText("")
        self.ui.lineEditHourly21.setText("")
        self.ui.lineEditHourly22.setText("")
        self.ui.lineEditHourly23.setText("")
        return None

    @catch_errors
    def clear_daily_profile(self, checked=False):
        """
        Clears the currently displayed data for hourly profiles ready to receive
         new data.

        :return: None if successful; error message as a string if its
         unsuccessful
        """
        self.ui.lineEditDailyMon.setText("")
        self.ui.lineEditDailyTues.setText("")
        self.ui.lineEditDailyWed.setText("")
        self.ui.lineEditDailyThurs.setText("")
        self.ui.lineEditDailyFri.setText("")
        self.ui.lineEditDailySat.setText("")
        self.ui.lineEditDailySun.setText("")
        return None

    @catch_errors
    def clear_monthly_profile(self, checked=False):
        """
        Clears the currently displayed data for hourly profiles ready to receive
         new data

        :return: None if successful; error message as a string if its
         unsuccessful
        """
        self.ui.lineEditMonthlyJan.setText("")
        self.ui.lineEditMonthlyFeb.setText("")
        self.ui.lineEditMonthlyMar.setText("")
        self.ui.lineEditMonthlyApr.setText("")
        self.ui.lineEditMonthlyMay.setText("")
        self.ui.lineEditMonthlyJun.setText("")
        self.ui.lineEditMonthlyJul.setText("")
        self.ui.lineEditMonthlyAug.setText("")
        self.ui.lineEditMonthlySep.setText("")
        self.ui.lineEditMonthlyOct.setText("")
        self.ui.lineEditMonthlyNov.setText("")
        self.ui.lineEditMonthlyDec.setText("")
        return None

    @catch_errors
    def close_ui(self):
        """
        Exit function used to close the UI and tidy up QGIS of any temporary
         files and/or refreshes that might be needed.
        """
        self.close()


class OpenAlaqsTaxiRoutes(QtWidgets.QDialog):
    def __init__(self, iface):
        main_window = None if iface is None else iface.mainWindow()
        QtWidgets.QDialog.__init__(self, main_window)

        Ui_TaxiRoutesDialog, _ = loadUiType(
            os.path.join(os.path.dirname(__file__), "ui", "ui_taxiway_routes.ui")
        )
        self.ui = Ui_TaxiRoutesDialog()
        self.ui.setupUi(self)

        self.iface = iface
        self.canvas = None if iface is None else self.iface.mapCanvas()

        self.populate_arr_dep()
        self.populate_runways()
        self.populate_gates()
        self.populate_routes()
        self.populate_aircraft_groups()
        self.populate_instance()
        self.visualize_route_name()

        self.ui.gate.currentIndexChanged.connect(self.visualize_route_name)
        self.ui.runway.currentIndexChanged.connect(self.visualize_route_name)
        self.ui.instance.currentIndexChanged.connect(self.visualize_route_name)
        self.ui.arrdep.currentIndexChanged.connect(self.visualize_route_name)

        self.ui.routes.currentIndexChanged.connect(self.route_changed)
        self.ui.create.clicked.connect(self.create_new_taxi_route)
        self.ui.close_button.clicked.connect(self.close)

        # routes
        self.ui.delete_route.clicked.connect(self.delete_taxiway_route)
        self.ui.clear_route.clicked.connect(self.clear_taxiway_segments_table)
        self.ui.save_route.clicked.connect(self.save_taxiway_route)

        # ac groups
        self.ui.add_ac_group.clicked.connect(self.add_aircraft_group)
        self.ui.delete_ac_group.clicked.connect(self.delete_aircraft_group)

        # initialize selection of taxi routes (emits SIGNAL for route_changed)
        if self.ui.routes.count():
            # requires two changes to be fired
            self.ui.routes.setCurrentIndex(1)
            self.ui.routes.setCurrentIndex(0)

        # visualization

        # disable index number in tables
        self.ui.taxiway_segments.verticalHeader().setVisible(False)
        self.ui.available_ac_groups.verticalHeader().setVisible(False)
        self.ui.selected_ac_groups.verticalHeader().setVisible(False)

    def add_taxiways_from_canvas_to_table(self, *args, **kwargs):
        select_taxiways = self.get_selected_taxiways_from_canvas()
        self.update_taxiway_segments_table(select_taxiways)

    def remove_taxiway_from_table(self):
        names_to_remove = ""
        names_to_remove = [
            item.text() for item in self.ui.taxiway_segments.selectedItems()
        ]

        if len(names_to_remove):
            all_taxiway_segments_ = list()
            table_rows = self.ui.taxiway_segments.rowCount()
            if table_rows > 0:
                for row in range(table_rows):
                    all_taxiway_segments_.append(
                        self.ui.taxiway_segments.item(row, 0).text()
                    )

            for name_ in names_to_remove:
                if name_ in all_taxiway_segments_:
                    all_taxiway_segments_.pop(all_taxiway_segments_.index(name_))
            self.update_taxiway_segments_table(all_taxiway_segments_)

    @catch_errors
    def populate_gates(self):
        """
        Completes the UI dropdown box with the names of all gates in the current
         study
        :return: None if successful; error message as a string if its
         unsuccessful
        """
        gates = alaqs.get_gates()
        self.ui.gate.clear()
        if (gates is None) or (gates == []):
            return None
        else:
            for gate in gates:
                self.ui.gate.addItem(gate["gate_id"])
            self.ui.gate.setEditable(False)

    @catch_errors
    def populate_runways(self):
        """
        Completes the UI dropdown box with the names of all runways in the
         current study
        :return: None if successful; error message as a string if its
         unsuccessful
        """
        runways = alaqs.get_runways()
        self.ui.runway.clear()
        if (runways is None) or (runways == []):
            logger.warning("Taxiway Routes Tool: No runways found")
        else:
            for runway in runways:
                data = runway["runway_id"].split("/")
                for rw in data:
                    self.ui.runway.addItem(rw)
            self.ui.runway.setEditable(False)
            # logger.debug("Taxiway Routes Tool: Runways populated")

    def populate_instance(self):
        """
        Add ten non-used instances to the UI to allow the user to define
         multiple
        """
        counter_ = 1
        found_ = 0
        while True:
            if found_ > 10:
                break
            rn_ = self.build_route_name(instance=counter_)
            if self.ui.routes.findText(rn_) == -1:
                self.ui.instance.addItem(str(counter_))
                found_ += 1
            counter_ += 1

    def populate_arr_dep(self):
        """
        Adds A (arrival) and D (departure) to the UI
        """
        self.ui.arrdep.addItem("A")
        self.ui.arrdep.addItem("D")

    @catch_errors
    # @log_activity
    def populate_routes(self, select_name=""):
        """
        Completes the UI dropdown box with the names of all routes in the
         current study
        :return: None if successful; error message as a string if its
         unsuccessful
        """

        # Remove any existing elements
        self.ui.routes.clear()

        # Get taxiway routes
        taxiway_routes = alaqs.get_taxiway_routes()

        if taxiway_routes is not None:
            for taxiway_route in taxiway_routes:
                self.ui.routes.addItem(taxiway_route[2])
            logger.debug("Taxiway Routes Tool: routes populated")

        # Add the signal to pick up new selected taxiways
        self.canvas.selectionChanged.connect(self.add_taxiways_from_canvas_to_table)

        if select_name:
            index_select_name_ = self.ui.routes.findText(select_name)
            if index_select_name_ != -1:
                self.ui.routes.setCurrentIndex(index_select_name_)
        else:
            logger.warning("Taxiway Routes Tool: No routes defined")

    def populate_aircraft_groups(self):
        """
        Completes the UI dropdown box with the names of all aircraft groups in
         the current study
        """
        # TODO these values should really come from database rather than being
        #  hard coded
        aircraft_groups = [
            "JET SMALL",
            "JET MEDIUM",
            "JET LARGE",
            "JET BUSINESS",
            "JET REGIONAL",
            "TURBOPROP",
            "PROPELLER",
        ]
        self.ui.available_ac_groups.clear()
        self.ui.available_ac_groups.setColumnCount(1)
        self.ui.available_ac_groups.setHorizontalHeaderLabels(["Group Name"])
        self.ui.available_ac_groups.setRowCount(len(aircraft_groups))
        for row, aircraft_group in enumerate(sorted(aircraft_groups)):
            table_item = QtWidgets.QTableWidgetItem(str(aircraft_group))
            self.ui.available_ac_groups.setItem(row, 0, table_item)

    # @log_activity
    def add_aircraft_group(self, *args, **kwargs):
        """
        Adds the selected aircraft group from the available aircraft group list
         to the selected aircraft group list
        """
        # Get a list of the groups already in the list
        selected_groups = list()
        table_rows = self.ui.selected_ac_groups.rowCount()
        if table_rows > 0:
            for row in range(table_rows):
                group_name = str(self.ui.selected_ac_groups.item(row, 0).text())
                selected_groups.append(group_name)

        # Loop over the selected rows and add them to the selected list if not
        # present
        for index in self.ui.available_ac_groups.selectedIndexes():
            row = index.row()
            group_name = str(self.ui.available_ac_groups.item(row, 0).text())
            if group_name not in selected_groups:
                selected_groups.append(group_name)
                selected_groups = sorted(list(set(selected_groups)))

        # Get rid of any None values that may have appeared
        try:
            selected_groups.remove("None")
        except Exception:
            pass

        # Update the UI
        self.update_selected_ac_groups(selected_groups)

    def delete_aircraft_group(self):
        """
        Removes an aircraft group from the currently selected aircraft groups
         list
        """
        # Get a list of the groups already in the list
        selected_groups = list()
        table_rows = self.ui.selected_ac_groups.rowCount()
        if table_rows > 0:
            for row in range(table_rows):
                group_name = str(self.ui.selected_ac_groups.item(row, 0).text())
                selected_groups.append(group_name)

        # Get the groups to be removed
        to_remove = list()
        for index in self.ui.selected_ac_groups.selectedIndexes():
            row = index.row()
            group_name = str(self.ui.selected_ac_groups.item(row, 0).text())
            to_remove.append(group_name)

        # Remove these from the list
        for group in to_remove:
            selected_groups.remove(group)

        # Repopulate the table
        self.update_selected_ac_groups(selected_groups)

    def visualize_route_name(self, args=None, route_name=None):
        if route_name is None:
            route_name = self.build_route_name()
            if route_name is None:
                route_name = ""

        self.ui.taxiway_route_name.setText(route_name)

        # TODO Highlight the chosen features
        oautk.get_layer(self.iface, "Gates")
        oautk.get_layer(self.iface, "Runways")

    def build_route_name(
        self, gate_name=None, runway_name=None, instance=None, arrdep=None
    ):
        """
        This function builds a correctly formatted taxiway route name based on
         the gate and runway combination defined
        by the user.
        """

        if gate_name is None:
            gate_name = self.ui.gate.currentText()
        if runway_name is None:
            runway_name = self.ui.runway.currentText()
        if instance is None:
            instance = self.ui.instance.currentText()
        if arrdep is None:
            arrdep = self.ui.arrdep.currentText()

        route_name = "%s/%s/%s/%s" % (gate_name, runway_name, arrdep, instance)
        return route_name

    @catch_errors
    # @log_activity
    def create_new_taxi_route(self, *args, **kwargs):
        """
        This function clears the UI ready to accept a new taxiway route
         definition.
        """

        # Get proposed taxi route name
        new_taxi_route_name = str(self.ui.taxiway_route_name.text())

        # Get existing taxi routes
        existing_taxi_routes = [
            self.ui.routes.itemText(i) for i in range(self.ui.routes.count())
        ]

        if new_taxi_route_name in existing_taxi_routes:
            QtWidgets.QMessageBox.information(
                self, "Notice", "Taxi route already exists"
            )
            return

        # Add the new route name to the list
        self.ui.routes.addItem(new_taxi_route_name)
        index = self.ui.routes.findText(new_taxi_route_name)
        self.ui.routes.setCurrentIndex(index)

        # Clear the taxiways table
        self.clear_taxiway_segments_table()

        # Clear the selected aircraft groups table
        self.update_selected_ac_groups([])

        # open the "Edit route" tab
        self.ui.createEditTaxiRouteTabWidget.setCurrentWidget(
            self.ui.createEditTaxiRouteTabWidget.findChild(
                QtWidgets.QWidget, "editRouteTab"
            )
        )

    def update_selected_ac_groups(self, values_list):
        # Clear the selected aircraft groups table
        self.ui.selected_ac_groups.clear()
        if len(values_list) == 0:
            self.ui.selected_ac_groups.setColumnCount(0)
            self.ui.selected_ac_groups.setRowCount(0)
        else:
            self.ui.selected_ac_groups.setColumnCount(1)
            self.ui.selected_ac_groups.setHorizontalHeaderLabels(["Group Name"])
            self.ui.selected_ac_groups.setRowCount(len(values_list))

        for row, group in enumerate(values_list):
            table_item = QtWidgets.QTableWidgetItem(str(group))
            self.ui.selected_ac_groups.setItem(row, 0, table_item)

    def select_taxiways_on_canvas(self, taxiway_segments):
        """
        Select all taxi ways on a route also on the canvas
        """
        self.canvas.blockSignals(True)
        # self.closeEvent()

        layer = self.iface.activeLayer()
        if layer is None:
            return

        # TODO OPENGIS.ch: this is should be the taxiway layer, not the currently active (possible raster) layer
        layer.removeSelection()
        layer.select(layer.dataProvider().attributeIndexes())

        to_select = []
        for feature in layer.getFeatures():
            if (
                len(feature.attributes()) > 1
                and str(feature.attributes()[1]) in taxiway_segments
            ):
                to_select.append(feature.id())

        if to_select:
            layer.selectByIds([s for s in to_select])

        self.canvas.blockSignals(False)

    # def closeEvent(self, event=None):
    #     try:
    #         self.canvas.selectionChanged.disconnect(
    #             self.add_taxiways_from_canvas_to_table
    #         )
    #     except Exception, e:
    #         logger.info(e)
    #     if not event is None:
    #         event.accept()

    def get_selected_taxiways_from_canvas(self):
        """
        Return the currently selected taxi ways from canvas
        """
        taxiway_segments = []
        # Get the features that are now selected
        layer = self.iface.activeLayer()
        selected_features = layer.selectedFeatures()

        # Loop over the selected features and check them against the features
        # already listed
        # If the feature is not in list, then it must be the one just selected
        for feature in selected_features:
            try:
                # generic index for name
                selected_taxiway_id = str(feature.attribute("taxiway_id"))

                if selected_taxiway_id not in taxiway_segments:
                    taxiway_segments.append(selected_taxiway_id)
            except Exception:
                pass

        return taxiway_segments

    def clear_taxiway_segments_table(self, *args, **kwargs):
        self.update_taxiway_segments_table([])

    def update_taxiway_segments_table(self, taxiway_segments_list):
        self.ui.taxiway_segments.clear()
        if len(taxiway_segments_list) == 0:
            self.ui.taxiway_segments.setColumnCount(0)
        else:
            self.ui.taxiway_segments.setColumnCount(1)
            self.ui.taxiway_segments.setHorizontalHeaderLabels(["Taxiway Name"])

        self.ui.taxiway_segments.setRowCount(len(taxiway_segments_list))

        for row, taxiway_name in enumerate(taxiway_segments_list):
            self.ui.taxiway_segments.setItem(
                row, 0, QtWidgets.QTableWidgetItem(str(taxiway_name))
            )

        self.select_taxiways_on_canvas(taxiway_segments_list)

    @catch_errors
    def route_changed(self, *args, **kwargs):
        """
        Automatically updates the UI when the selected route is changed so that
        the appropriate data is displayed in
        the UI.
        """
        new_route_name = self.ui.routes.currentText()
        if new_route_name != "":
            route_data = alaqs.get_taxiway_route(new_route_name)
            if route_data is not None:
                taxiway_segments_ = (
                    route_data[0][6].split(",") if route_data[0][6] else []
                )
                self.update_taxiway_segments_table(taxiway_segments_)

                selected_ac_groups_ = (
                    route_data[0][7].split(",") if route_data[0][7] else []
                )
                self.update_selected_ac_groups(selected_ac_groups_)

    def delete_taxiway_route(self, name=""):
        """
        Deletes a saved taxi route from the current study
        """
        taxi_route_name = self.ui.routes.currentText() if not name else name
        result = alaqs.delete_taxiway_route(taxi_route_name)
        if result is not None:
            QtWidgets.QMessageBox.warning(
                self, "Notice", "Taxi route not deleted: %s" % result
            )
            return
        self.populate_routes()

    def save_taxiway_route(self, *args, **kwargs):
        """
        Saves a new taxiroute to the current study
        """

        # See if the route already exists in the database
        already_exists = False
        delete_taxiroute = False
        taxi_route_name = self.ui.routes.currentText()
        existing_taxi_routes = alaqs.get_taxiway_routes()

        if existing_taxi_routes is not None:
            for existing_taxi_route in existing_taxi_routes:
                if existing_taxi_route[2] == taxi_route_name:
                    already_exists = True
        if already_exists:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Notice",
                "Taxi route '%s' already exists in database."
                " Overwrite existing route?" % taxi_route_name,
                QtWidgets.QMessageBox.Yes,
                QtWidgets.QMessageBox.No,
            )
            if reply == QtWidgets.QMessageBox.Yes:
                delete_taxiroute = True
            else:
                return False

        # Get the taxi route
        taxiway_segments = list()
        table_rows = self.ui.taxiway_segments.rowCount()

        # Notify the user that the taxiway list is blank
        if table_rows <= 0:
            QtWidgets.QMessageBox.information(self, "Notice", "Taxiway list is blank.")
            return

        for row in range(table_rows):
            taxiway_segments.append(str(self.ui.taxiway_segments.item(row, 0).text()))

        # Now get the assigned aircraft groups
        aircraft_groups = list()
        table_rows = self.ui.selected_ac_groups.rowCount()
        if table_rows > 0:
            for row in range(table_rows):
                aircraft_groups.append(
                    str(self.ui.selected_ac_groups.item(row, 0).text())
                )

        # Create the taxiway route dict
        split_data = taxi_route_name.split("/")
        taxiway_route = dict()
        taxiway_route["name"] = taxi_route_name
        taxiway_route["gate"] = split_data[0]
        taxiway_route["runway"] = split_data[1]
        taxiway_route["dept_arr"] = split_data[2]
        taxiway_route["instance"] = split_data[3]
        taxiway_route["sequence"] = ",".join(taxiway_segments)
        taxiway_route["groups"] = ",".join(aircraft_groups)

        # Delete existing route
        if delete_taxiroute:
            self.delete_taxiway_route(taxi_route_name)

        # Save to database
        result = alaqs.add_taxiway_route(taxiway_route)

        # Repopulate sources
        self.populate_routes(taxi_route_name)

        if result is not None:
            QtWidgets.QMessageBox.warning(
                self, "Notice", "Taxi route could not be saved: %s" % str(result)
            )
        else:
            QtWidgets.QMessageBox.information(self, "Notice", "Taxi route was saved.")
        return


class OpenAlaqsLogfile(QtWidgets.QDialog):
    """
    This class provides a dialog that presents the current Open ALAQS log file
    """

    def __init__(self):
        """
        Initialises QDialog that displays the about UI for the plugin.
        """
        QtWidgets.QDialog.__init__(self)

        Ui_DialogLogfile, _ = loadUiType(
            os.path.join(os.path.dirname(__file__), "ui", "ui_logfile.ui")
        )
        self.ui = Ui_DialogLogfile()
        self.ui.setupUi(self)

        self.ui.clear.clicked.connect(self.clear_logfile)
        self.ui.save.clicked.connect(self.save_logfile)
        self.ui.close.clicked.connect(self.close)

        self.load_log_file()

    def load_log_file(self):
        """
        Find and load the content of the ALAQS log file to a basic UI.
        :return:
        """
        try:
            self.ui.logfile_text_area.clear()
            with log_path.open("rt") as log_file:
                data = "".join(log_file.readlines())
                self.ui.logfile_text_area.setText(data)
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "Error", "Could not open log file: %s" % e
            )

    def clear_logfile(self):
        """
        Clear the log file display window of all current log records
        :return:
        """

        question = QtWidgets.QMessageBox.question(
            self,
            "",
            "Delete the log file?",
            QtWidgets.QMessageBox.Yes,
            QtWidgets.QMessageBox.No,
        )

        if question == QtWidgets.QMessageBox.Yes:
            self.ui.logfile_text_area.clear()
            self.reset_logfile()

    def reset_logfile(self):
        """
        Reset the log file
        :return:
        """
        try:
            with log_path.open("w"):
                pass

            self.load_log_file()
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "Error", "Could not reset the log file: %s" % e
            )

    def save_logfile(self):
        """
        Save the current log file display to the log file
        :return:
        """
        try:
            # Get the current log file path
            with log_path.open("r") as current_log_file:
                current_log_file_text = current_log_file.read()

                new_path = QtWidgets.QFileDialog.getSaveFileName(
                    self, "Save log file as ...", ""
                )
                if new_path:
                    new_file = open(new_path, "wt")
                    new_file.write(current_log_file_text)
                    new_file.close()

            self.load_log_file()
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "Error", "Could not reset the log file: %s" % e
            )


class OpenAlaqsInventory(QtWidgets.QDialog):
    """
    This class provides a dialog that is used to define and initialize the
     creation of a new emission inventory.
    """

    def __init__(self):
        QtWidgets.QDialog.__init__(self)

        # Setup the user interface from Designer
        Ui_DialogInventory, _ = loadUiType(
            os.path.join(os.path.dirname(__file__), "ui", "ui_inventory.ui")
        )
        self.ui = Ui_DialogInventory()
        self.ui.setupUi(self)

        # Connections
        # TODO OPENGIS.ch: remove the Vertical limit from the form, use the one in the Emission Inventory Analysis only
        self.ui.vert_limit_m.valueChanged.connect(self.m_to_ft)
        self.ui.vert_limit_ft.setEnabled(False)

        self.ui.status_update.setText("Ready")
        self.ui.buttonBox.button(
            QtWidgets.QDialogButtonBox.StandardButton.Save
        ).setText("Create Inventory")
        self.ui.buttonBox.button(
            QtWidgets.QDialogButtonBox.StandardButton.Save
        ).clicked.connect(self.create_inventory)
        self.ui.buttonBox.button(
            QtWidgets.QDialogButtonBox.StandardButton.Close
        ).clicked.connect(self.close)

        # Set some default values
        self.ui.movement_table_path.setFilter("CSV (*.csv);;TXT (*.txt)")
        self.ui.movement_table_path.setDialogTitle("Open ALAQS Movement Data")
        self.ui.movement_table_path.fileChanged.connect(
            self.movement_table_path_changed
        )
        self.ui.met_file_path.setFilter("CSV (*.csv);;TXT (*.txt)")
        self.ui.met_file_path.setDialogTitle("Open ALAQS Meteorological Data")
        self.ui.met_file_path.fileChanged.connect(self.met_file_path_changed)
        self.ui.output_save_path.setStorageMode(QgsFileWidget.GetDirectory)
        self.ui.towing_speed.setValue(10.0)
        self.ui.vert_limit_m.setValue(914.4)
        self.ui.x_resolution.setValue(250)
        self.ui.y_resolution.setValue(250)
        self.ui.z_resolution.setValue(50)
        self.ui.x_cells.setValue(50)
        self.ui.y_cells.setValue(50)
        self.ui.z_cells.setValue(20)

    def movement_table_path_changed(self, path):
        try:
            if os.path.exists(path):
                with OverrideCursor(Qt.CursorShape.WaitCursor):
                    result = self.examine_movements(path)

                if isinstance(result, str) or isinstance(result, Exception):
                    raise Exception(result)
                return None
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", "%s" % e)
            return e

    def examine_movements(self, movement_file):
        """
        Takes a look inside the selected movement file to check that data is as
         we would expect it to be (a more
        thorough investigation is performed on data import later).

        :param movement_file: path to the selected movement file [string]
        :return: None if successful, error message otherwise
        """
        try:
            # Make the UI update for progress label to change
            self.ui.status_update.setText("Evaluating movement file...")
            QtWidgets.qApp.processEvents()

            # Open the movement file
            with open(movement_file, "r") as movement_file:
                # with open(movement_file, 'rt') as movement_file:
                movement_line = 0

                # Arbitrarily out of range first guess dates
                start_date = datetime.strptime(
                    "2999-01-01 00:00:00", "%Y-%m-%d %H:%M:%S"
                )
                end_date = datetime.strptime("1900-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")

                # Loop over the movement file and perform some basic checks
                for index_line, line in enumerate(movement_file):
                    movement_line += 1
                    movement_data = line.split(";")
                    # skip empty lines
                    if len(movement_data) == 1 and movement_data[0] == "\n":
                        continue

                    if movement_line == 1:
                        # Check out the header row
                        if len(movement_data) < 1:
                            raise Exception("Movement file contains no data on line 1")
                        if not isinstance(movement_data[0], str):
                            raise Exception("Movement file is missing header row")
                    else:
                        # Get the range of movement dates
                        try:
                            alaqsutils.dict_movement(movement_data)
                        except Exception as e:
                            raise Exception(
                                "Line'%i':\n%s\nhas the following error:"
                                "\n %s" % (index_line, line, e)
                            )

                        date_time = datetime.strptime(
                            movement_data[0], "%Y-%m-%d %H:%M:%S"
                        )
                        if date_time < start_date:
                            start_date = (date_time).replace(minute=0, second=0)
                        if date_time > end_date:
                            end_date = (date_time + timedelta(hours=1)).replace(
                                minute=0, second=0
                            )

            self.ui.study_start_date.setDateTime(
                QtCore.QDateTime.fromString(
                    start_date.strftime("%Y-%m-%d %H:%M:%S"), "yyyy-M-d hh:mm:ss"
                )
            )
            self.ui.study_end_date.setDateTime(
                QtCore.QDateTime.fromString(
                    end_date.strftime("%Y-%m-%d %H:%M:%S"), "yyyy-M-d hh:mm:ss"
                )
            )

            self.ui.movements_summary.setText(
                "Total Movements: %d; Start: %s; End: %s"
                % (
                    (int(movement_line) - 1),
                    start_date.strftime("%Y-%m-%d %H:%M:%S"),
                    end_date.strftime("%Y-%m-%d %H:%M:%S"),
                )
            )
            self.ui.status_update.setText("Movement file seems OK")
        except Exception as e:
            self.ui.status_update.setText("Problem with movement file. See log file")
            alaqsutils.print_error(self.examine_movements.__name__, Exception, e)
            return e
        return None

    def met_file_path_changed(self, path):
        """
        Opens a dialog window for a user to be able to find and load a
         meteorological file into the current study
        database
        :return:
        """
        try:
            if os.path.exists(path):
                with OverrideCursor(Qt.CursorShape.WaitCursor):
                    result = self.examine_met_file(path)

                if isinstance(result, str):
                    raise Exception()
                return
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "Error", "Could not open met file:  %s." % e
            )
            return e

    def examine_met_file(self, met_file):
        """
        Open and validate a meteorological file for use in the current study
        :param met_file: the path to the selected meteorological file
        :return:
        """

        logger.info("Processing meteorological file.")

        # ToDo: More general configuration
        def CheckAmbientConditions(parameter, isa_value, tolerance):
            return 100 * float(abs(parameter - isa_value)) / isa_value > tolerance

        csv = read_csv_to_dict(met_file)

        headers_ = {
            "Scenario": "Scenario",
            "DateTime(YYYY-mm-dd hh:mm:ss)": "DateTime",
            "Temperature(K)": "Temperature",
            "Humidity(kg_water/kg_dry_air)": "Humidity",
            "RelativeHumidity(%)": "RelativeHumidity",
            "SeaLevelPressure(mb)": "SeaLevelPressure",
            "WindSpeed(m/s)": "WindSpeed",
            "WindDirection(degrees)": "WindDirection",
            "ObukhovLength(m)": "ObukhovLength",
            "MixingHeight(m)": "MixingHeight",
        }

        # check if all headers are found
        if not sorted(csv.keys()) == sorted(headers_.keys()):
            QtWidgets.QMessageBox.information(
                self, "Warning", "Headers of meteo csv file do not match.."
            )

            for key in list(headers_.keys()):
                if not list(csv.keys()):
                    QtWidgets.QMessageBox.information(
                        self, "Warning", "Did not find header '%s' in csv file." % (key)
                    )
            return False

        # Arbitrarily out of range first guess dates
        start_date = datetime.strptime("2999-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
        end_date = datetime.strptime("1900-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")

        # Loop over the MET file and perform some basic checks
        for row_, date_ in enumerate(csv["DateTime(YYYY-mm-dd hh:mm:ss)"]):
            logger.debug(
                "Processing time interval: %s"
                % (csv["DateTime(YYYY-mm-dd hh:mm:ss)"][row_])
            )

            date_time = datetime.strptime(
                csv["DateTime(YYYY-mm-dd hh:mm:ss)"][row_], "%Y-%m-%d %H:%M:%S"
            )
            if date_time < start_date:
                start_date = (date_time).replace(minute=0, second=0)
            if date_time > end_date:
                end_date = (date_time + timedelta(hours=1)).replace(minute=0, second=0)

            if CheckAmbientConditions(
                conversion.convertToFloat(csv["Temperature(K)"][row_]), 288.15, 50
            ):
                logger.warning("Check temperature units/value.")
            if CheckAmbientConditions(
                conversion.convertToFloat(csv["Humidity(kg_water/kg_dry_air)"][row_]),
                0.00634,
                100,
            ):
                logger.warning("Check Humidity units/value.")
            if CheckAmbientConditions(
                conversion.convertToFloat(csv["RelativeHumidity(%)"][row_]), 0.6, 90
            ):
                logger.warning("Check Relative Humidity units/value.")
            if CheckAmbientConditions(
                conversion.convertToFloat(csv["SeaLevelPressure(mb)"][row_]),
                101325.0,
                70,
            ):
                logger.warning("Check Sea Level Pressure units/value.")
            if CheckAmbientConditions(
                conversion.convertToFloat(csv["WindSpeed(m/s)"][row_]), 15.0, 100
            ):
                logger.warning("Check Wind Speed units/value.")
            if CheckAmbientConditions(
                conversion.convertToFloat(csv["WindDirection(degrees)"][row_]),
                360.0,
                100,
            ):
                logger.warning("Check Wind Direction units/value.")
            if CheckAmbientConditions(
                conversion.convertToFloat(csv["MixingHeight(m)"][row_]), 914.4, 100
            ):
                logger.warning("Check Mixing Height units/value.")

        self.ui.met_summary.setText(
            "Start: %s; End: %s"
            % (
                start_date.strftime("%Y-%m-%d %H:%M:%S"),
                end_date.strftime("%Y-%m-%d %H:%M:%S"),
            )
        )

        self.ui.status_update.setText("MET file seems OK")
        return True

    def create_inventory(self):
        """
        This function takes and validates the users choices for creation of an
         emission inventory and then tries to
        create this inventory.
        """
        try:
            # Collect parameters
            movement_file_path = self.ui.movement_table_path.filePath()
            output_save_name = oautk.validate_field(self.ui.output_save_name, "str")
            output_save_path = self.ui.output_save_path.filePath()
            met_csv_path = oautk.validate_field(self.ui.met_file_path, "str")
            study_start_date = oautk.validate_field(self.ui.study_start_date, "str")
            study_end_date = oautk.validate_field(self.ui.study_end_date, "str")
            vert_limit = self.ui.vert_limit_m.value()
            towing_speed = self.ui.towing_speed.value()
            #   method = self.ui.method.currentText()
            #   met_file_path = oautk.validate_field(self, self.ui.met_file_path, "str")
            x_resolution = self.ui.x_resolution.value()
            y_resolution = self.ui.y_resolution.value()
            z_resolution = self.ui.z_resolution.value()
            x_cells = self.ui.x_cells.value()
            y_cells = self.ui.y_cells.value()
            z_cells = self.ui.z_cells.value()

            if (
                (movement_file_path is None)
                or (output_save_name is False)
                or (output_save_path is None)
                or (study_start_date is False)
                or (study_end_date is False)
                or (vert_limit is False)
                or (towing_speed is False)
                or (x_resolution is False)
                or (y_resolution is False)
                or (z_resolution is False)
                or (x_cells is False)
                or (y_cells is False)
                or (z_cells is False)
            ):
                QtWidgets.QMessageBox.warning(
                    self, "Error", "Please correct your input parameters."
                )
                return

            # Check dates - Start should be before end
            study_start_date = datetime.strptime(study_start_date, "%Y-%m-%d %H:%M:%S")
            study_end_date = datetime.strptime(study_end_date, "%Y-%m-%d %H:%M:%S")
            if study_start_date >= study_end_date:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Error",
                    "Study end date cannot be before or equal to start date.",
                )
                return

            full_save_path = os.path.join(
                output_save_path, output_save_name, "_out.alaqs"
            )
            if os.path.isfile(full_save_path):
                overwrite_msg = (
                    "A file with this name already exists."
                    " Are you sure you want to overwrite it?"
                )
                reply = QtWidgets.QMessageBox.question(
                    self,
                    "Message",
                    overwrite_msg,
                    QtWidgets.QMessageBox.Yes,
                    QtWidgets.QMessageBox.No,
                )
                if reply == QtWidgets.QMessageBox.Yes:
                    pass
                else:
                    return False

            # build some dict to control what is and is not run
            model_parameters = dict()

            model_parameters["movement_path"] = movement_file_path
            model_parameters["study_start_date"] = study_start_date
            model_parameters["study_end_date"] = study_end_date
            model_parameters["towing_speed"] = towing_speed
            model_parameters["vertical_limit"] = vert_limit
            model_parameters["x_resolution"] = x_resolution
            model_parameters["y_resolution"] = y_resolution
            model_parameters["z_resolution"] = z_resolution
            model_parameters["x_cells"] = x_cells
            model_parameters["y_cells"] = y_cells
            model_parameters["z_cells"] = z_cells

            model_parameters["include_area_sources"] = True
            model_parameters["include_building"] = True
            model_parameters["include_gates"] = True
            model_parameters["include_parkings"] = True
            model_parameters["include_roadways"] = True
            model_parameters["include_stationary_sources"] = True
            model_parameters["include_taxiway_queues"] = True

            model_parameters["use_copert"] = False
            model_parameters["use_fuel_flow"] = False
            model_parameters["use_variable_mixing_height"] = False
            model_parameters["use_nox_correction"] = False
            model_parameters["use_smooth_and_shift"] = False
            model_parameters["use_3d_grid"] = True

            # Get the study setup as well
            study_setup = alaqs.load_study_setup()

            # Create a blank study output database
            self.ui.status_update.setText("Copying inventory database template...")
            QtWidgets.qApp.processEvents()
            output_save_name = "%s_out.alaqs" % output_save_name
            inventory_path = os.path.join(output_save_path, output_save_name)

            with OverrideCursor(Qt.CursorShape.WaitCursor):
                result = alaqs.inventory_creation_new(
                    inventory_path, model_parameters, study_setup, met_csv_path
                )

            if isinstance(result, str):
                QtWidgets.QMessageBox.warning(
                    self, "Error", "A new ALAQS output file could not be created."
                )
                return
            else:
                QtWidgets.QMessageBox.information(
                    self,
                    "ALAQS - Inventory",
                    "A new ALAQS output file has been created. "
                    "Please use the 'Results' tool to evaluate the output.",
                )
            self.ui.status_update.setText("Done.")
        except Exception as e:
            self.ui.status_update.setText("**Error** See log file")
            error = alaqsutils.print_error(self.create_inventory.__name__, Exception, e)
            return error

    def m_to_ft(self):
        """
        Function that converts the user entered vertical limit in metres in feet
         as well.
        This isn't an essential process - more cosmetic
        """
        try:
            m_value = self.ui.vert_limit_m.value()
            ft_value = m_value * 3.2808399
            self.ui.vert_limit_ft.setValue(ft_value)
            # Make sure that the cell background is plain white
            oautk.color_ui_background(self.ui.vert_limit_m, "transparent")
        except Exception:
            # Make the cell background red to highlight an error
            oautk.color_ui_background(self.ui.vert_limit_m, "red")

    @staticmethod
    def check_state(ui_element):
        """
        This function checks and returns the state of a checkbox as boolean
        :param ui_element: the name of the checkbox to be reviewed
        :return: boolean - True for checked, False for unchecked
        """
        try:
            return ui_element.checkState() == Qt.CheckState.Checked
        except Exception:
            return None


class OpenAlaqsResultsAnalysis(QtWidgets.QDialog):
    """
    This class provides a dialog for visualizing ALAQS results.
    """

    settings_schema = {
        "start_dt_inclusive": {
            "label": "Start (incl.)",
            "widget_type": QtWidgets.QDateTimeEdit,
            "initial_value": "2000-01-01 00:00:00",
        },
        "end_dt_inclusive": {
            "label": "End (incl.)",
            "initial_value": "2000-01-02 00:00:00",
            "widget_type": QtWidgets.QDateTimeEdit,
        },
        "method": {
            "label": "Method",
            "widget_type": QtWidgets.QComboBox,
            "initial_value": None,
            "widget_config": {
                "options": [],
            },
        },
        "should_apply_nox_corrections": {
            "label": "Apply NOx Corrections",
            "widget_type": QtWidgets.QCheckBox,
            "initial_value": False,
            "tooltip": "Only available when the method is set to 'bymode'.",
        },
        "source_dynamics": {
            "label": "Source Dynamics",
            "widget_type": QtWidgets.QComboBox,
            "initial_value": "none",
            "widget_config": {
                "options": ["none", "default", "smooth & shift"],
            },
        },
        "time_interval": {
            "label": "Time Interval",
            "widget_type": QtWidgets.QComboBox,
            "initial_value": "3600",
            "widget_config": {
                "options": [
                    ("60", "1 minute"),
                    ("300", "5 minutes"),
                    ("600", "10 minutes"),
                    ("900", "15 minutes"),
                    ("1200", "20 minutes"),
                    ("1800", "30 minutes"),
                    ("3600", "1 hour"),
                ],
            },
        },
        "vertical_limit_m": {
            "label": "Vertical Limit",
            "widget_type": QgsDoubleSpinBox,
            "initial_value": 914.4,
            "widget_config": {"minimum": 0, "maximum": 999999.9, "suffix": "m"},
        },
        "receptor_points": {
            "label": "Receptor Points",
            "widget_type": QgsFileWidget,
            "widget_config": {
                "filter": "CSV (*.csv)",
                "dialog_title": "Select CSV File with Receptor Points",
            },
        },
    }

    def __init__(self, iface=None):
        main_window = iface.mainWindow() if iface is not None else None
        QtWidgets.QDialog.__init__(self, main_window)

        # store the pointer to the QGIS interface
        self._iface = iface

        # Setup the user interface from Designer
        Ui_ResultsAnalysisDialog, _ = loadUiType(
            os.path.join(os.path.dirname(__file__), "ui", "ui_results_analysis.ui")
        )
        self.ui = Ui_ResultsAnalysisDialog()
        self.ui.setupUi(self)
        self.ui.configuration_splitter.setSizes([80, 200])

        # Create and add a message bar in the QGIS interface
        self.message_bar = QgsMessageBar()
        self.message_bar.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )

        # Find the main layout of the dialog
        main_layout = self.layout()

        if main_layout is not None:
            # Insert the message bar at the top
            main_layout.insertWidget(0, self.message_bar)

        else:
            logger.warning("Could not find main layout to insert message bar.")

        # initialize calculation
        self._emission_calculation_ = None
        self._emission_calculation_configuration_widget = None

        # Initialise the service for the emission calculator
        self._emission_calculator_service = EmissionCalculatorService()

        self.resetModuleConfiguration(module_names=[])
        self.resetEmissionCalculationConfiguration()

        self.ui.configuration_modules_list.setCurrentRow(0)
        self.ui.configuration_stack.setCurrentIndex(0)
        self.ui.configuration_modules_list.currentRowChanged.connect(
            self.configuration_modules_list_current_row_changed
        )
        self.ui.configuration_stack.currentChanged.connect(
            self.configuration_stack_current_changed
        )

        # initialize GUI
        # self._pollutants_list = ["CO", "HC", "NOx", "SOx", "PM10", "P1", "P2"]
        self._pollutants_list = ["CO2", "CO", "HC", "NOx", "SOx", "PM10"]
        self.populate_pollutants()
        self.updateMinMaxGUI()

        self.ui.pollutants_names.currentIndexChanged.connect(self.pollutant_changed)
        self.ui.source_names.currentIndexChanged.connect(self.source_name_changed)
        self.ui.source_types.currentIndexChanged.connect(self.source_type_changed)

        self.ui.ResultsTableButton.clicked.connect(
            lambda: self.outputModuleRequested("TableViewWidgetOutputModule")
        )
        self.ui.plot_time_series_vs_emissions.clicked.connect(
            lambda: self.outputModuleRequested("TimeSeriesWidgetOutputModule")
        )
        self.ui.add_contour.clicked.connect(
            lambda: self.outputModuleRequested("EmissionsQGISVectorLayerOutputModule")
        )

        s = QgsSettings()
        last_result_file_path = s.value("OpenALAQS/last_result_file_path", "")

        self.ui.result_file_path.setFilter("ALAQS (*.alaqs)")
        self.ui.result_file_path.setDialogTitle("Open Emission Inventory Data")
        self.ui.result_file_path.fileChanged.connect(self.result_file_path_changed)
        self.ui.result_file_path.setFilePath(last_result_file_path)

        if os.path.isfile(last_result_file_path):
            self.updateMinMaxGUI(last_result_file_path)
            self.populate_source_types()

        self._return_values = {}
        self._receptor_points = gpd.GeoDataFrame()

    def configuration_modules_list_current_row_changed(self, row):
        self.ui.configuration_stack.setCurrentIndex(row)

    def configuration_stack_current_changed(self, index):
        self.ui.configuration_modules_list.setCurrentRow(index)

    def pollutant_changed(self):
        self.populate_calculation_methods(
            pollutant=self.ui.pollutants_names.currentText()
        )

    @catch_errors
    def populate_calculation_methods(self, pollutant=None):
        """
        Populate the UI with a list of method names that can be examined
        """
        if pollutant is None:
            pollutant = self.ui.pollutants_names.currentText()
        available_methods = []
        if pollutant in ["CO", "NOx", "HC"]:
            available_methods = ["bymode", "BFFM2"]
        else:
            available_methods = ["bymode"]

        self._emission_calculation_configuration_widget.patch_schema(
            {
                "method": {
                    "initial_value": available_methods[0],
                    "widget_config": {
                        "options": available_methods,
                    },
                }
            }
        )

    def resetEmissionCalculationConfiguration(self, config=None):
        if config is None:
            config = {}

        if self._emission_calculation_configuration_widget is None:

            def load_receptors_csv(path):
                self._receptor_points = read_csv_to_geodataframe(path)

            self._emission_calculation_configuration_widget = ModuleConfigurationWidget(
                self.settings_schema
            )
            self._emission_calculation_configuration_widget.get_widget(
                "receptor_points"
            ).fileChanged.connect(load_receptors_csv)

            self.ui.configuration_stack.insertWidget(
                0, self._emission_calculation_configuration_widget
            )

        self._emission_calculation_configuration_widget.init_values(config)
        self.update()

    def resetModuleConfiguration(self, module_names):
        self.ui.dispersion_modules_tab_widget.clear()
        self.ui.output_modules_tab_widget.clear()

        for module_name in DispersionModuleRegistry().get_module_names():
            module = DispersionModuleRegistry().get_module(module_name)
            config_widget = module.getConfigurationWidget()

            if config_widget is None:
                continue

            scroll_widget = QtWidgets.QScrollArea(self)
            scroll_widget.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            scroll_widget.setWidget(config_widget)
            scroll_widget.setWidgetResizable(True)
            self.ui.dispersion_modules_tab_widget.addTab(
                scroll_widget, module.getModuleDisplayName()
            )

        for module_name in OutputAnalysisModuleRegistry().get_module_names():
            module = OutputAnalysisModuleRegistry().get_module(module_name)
            config_widget = module.getConfigurationWidget2()

            if config_widget is None:
                continue

            scroll_widget = QtWidgets.QScrollArea(self)
            scroll_widget.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            scroll_widget.setWidget(config_widget)
            scroll_widget.setWidgetResizable(True)
            self.ui.output_modules_tab_widget.addTab(
                scroll_widget, module.getModuleDisplayName()
            )

    def getOutputModulesConfiguration(self):
        tab = self.ui.output_modules_tab_widget
        return {
            tab.tabText(index): tab.widget(index).widget().get_values()
            for index in range(0, tab.count())
        }

    def getDispersionModulesConfiguration(self):
        tab = self.ui.dispersion_modules_tab_widget
        return {
            tab.tabText(index): tab.widget(index).widget().get_values()
            for index in range(0, tab.count())
        }

    def outputModuleRequested(self, name: str) -> None:
        # Check if there is a valid output file at the beginning
        inventory_path = self.ui.result_file_path.filePath()

        if not inventory_path or not os.path.isfile(inventory_path):
            # Get a log warning
            logger.warning("Please select a valid output database file first.")

            # Get a message warning
            self.message_bar.pushWarning(
                "No File Selected", "Please select a valid output database file first."
            )
            return None

        if not is_output_db_file(inventory_path):
            # Get a log warning
            logger.warning(f"File {inventory_path} is not a valid output database.")

            # Get a message warning
            self.message_bar.pushWarning(
                "Invalid Results File", "File is not a valid output database."
            )
            return None

        OutputModule = OutputAnalysisModuleRegistry().get_module(name)

        if OutputModule is None:
            logger.error("Did not find module '%s'", name)
            return None

        output_module, res = self.runOutputModule(OutputModule)
        self.handleOutputModuleResult(output_module, res)

    def runOutputModule(self, OutputModule: Any) -> tuple[Any, Any]:
        # calculate all emissions
        logger.info("calculate all emissions...")
        self._emission_calculation_ = None
        if self._emission_calculation_ is None:
            self.update_emissions()

        if self._emission_calculation_ is None:
            logger.error("Cannot calculate emissions.")
            QMessageBox.warning(self, "Warning", "Cannot calculate emissions.")
            return

        logger.info("emissions calculated!")

        module_name = str(self.ui.source_types.currentText())
        source_name = str(self.ui.source_names.currentText())
        pollutant = str(self.ui.pollutants_names.currentText())

        config = {
            "parent": self,
            "pollutant": pollutant,
            "pollutants_list": [pollutant],
            "title": "Total emissions of '%s'"
            % (
                source_name
                if source_name.lower() != "all"
                else ("%s sources" % module_name)
            ),
            "ytitle": "Emissions of '%s' [kg]" % pollutant,
            "grid": self._emission_calculation_.get3DGrid(),
            "database_path": self._emission_calculation_.getDatabasePath(),
        }

        # Configuration of the emissions calculation
        em_configuration = self._emission_calculation_configuration_widget.get_values()
        em_configuration["receptors"] = self._receptor_points
        em_configuration["start_dt_inclusive"] = datetime.fromisoformat(
            em_configuration["start_dt_inclusive"]
        )
        em_configuration["end_dt_inclusive"] = datetime.fromisoformat(
            em_configuration["end_dt_inclusive"]
        )

        config.update(em_configuration)

        kwargs = {}
        # Get the configuration for the OutputModule
        gui_modules_config_ = self.getOutputModulesConfiguration()
        if OutputModule.getModuleDisplayName() in gui_modules_config_:
            config.update(gui_modules_config_[OutputModule.getModuleDisplayName()])

        # Configure and run the OutputModule
        output_module = OutputModule(values_dict=config)
        output_module.beginJob()
        for timeval, rows in list(self._emission_calculation_.getEmissions().items()):
            output_module.process(timeval, rows, **kwargs)
        return output_module, output_module.endJob()

    def handleOutputModuleResult(self, output_module: Any, res: Any) -> None:
        if isinstance(res, QtWidgets.QDialog):
            res.show()
        elif isinstance(res, QgsMapLayer):
            # Replace existing layers with same name...
            for layer in self._iface.mapCanvas().layers():
                if layer.name() == res.name():
                    QgsProject.instance().removeMapLayers([layer.id()])

            # and add the vector layer to the existing QGIS layers
            QgsProject.instance().addMapLayers([res])

            # automatically zoom to new layer
            self._iface.mapCanvas().setExtent(res.extent())

            # add coordinate-references system
            if res.crs() is not None:
                # self._iface.mapCanvas().mapRenderer().setDestinationCrs(res.crs())
                self._iface.mapCanvas().mapSettings().setDestinationCrs(res.crs())

            if output_module.getModuleName() == "EmissionsQGISVectorLayerOutputModule":
                # add text to graphics renderer
                gui_modules_config_ = self.getOutputModulesConfiguration()
                addTitleToLayer = gui_modules_config_.get("Add title", False)
                if addTitleToLayer:
                    textItem = QgsTextAnnotation(self._iface.mapCanvas())
                    textItem.setHasFixedMapPosition(False)
                    text = QtGui.QTextDocument(
                        "%s emissions (%.1f kg)\n%s - %s"
                        % (
                            str(output_module.getPollutant()),
                            round(output_module.getTotalEmissions(), 1),
                            str(output_module.getTimeStart()),
                            str(output_module.getTimeEnd()),
                        )
                    )
                    text.setDefaultFont(QtGui.QFont("Arial", 12))
                    textItem.setDocument(text)
                    textItem.setFrameSize(QtCore.QSizeF(500, 48))
                    textItem.setFrameOffsetFromReferencePoint(QtCore.QPointF(20, 75))
                    # textItem.setFrameBorderWidth(0.0)
                    # textItem.setFrameColor(QColor("white"))

                    self._iface.mapCanvas().scene().addItem(textItem)

    def updateMinMaxGUI(self, db_path_=""):
        (time_start_calc_, time_end_calc_) = get_min_max_timestamps(db_path_)
        # self.ui.start_dateTime.setMinimumDateTime(time_start_calc_)
        # self.ui.end_dateTime.setMaximumDateTime(time_end_calc_)

        self.resetEmissionCalculationConfiguration(
            config={
                "start_dt_inclusive": time_start_calc_,
                "end_dt_inclusive": time_end_calc_,
            }
        )
        self.ui.source_types.clear()
        self.ui.source_names.clear()

    @catch_errors
    def populate_source_types(self):
        """
        Populate the UI with a list of source types that can be examined
        """
        self.ui.source_types.clear()
        self.ui.source_types.addItem("all")
        self.ui.source_types.addItems(SourceModuleRegistry().get_module_names())
        self.ui.source_names.clear()
        self.ui.source_names.addItem("all")

    @catch_errors
    def populate_pollutants(self):
        """
        Populate the UI with a list of pollutant names that can be examined
        """
        self.ui.pollutants_names.clear()
        for pollutant in sorted(self._pollutants_list):
            self.ui.pollutants_names.addItem(pollutant)
        if self.ui.pollutants_names.count():
            self.ui.pollutants_names.setCurrentIndex(0)
        self.populate_calculation_methods(
            pollutant=self.ui.pollutants_names.currentText()
        )

    def result_file_path_changed(self, path):
        """
        Open a file browse window for the user to be able to locate and load an
        ALAQS output file
        """
        # Fill in the UI
        self.ui.source_names.clear()
        self.ui.source_types.clear()

        if not os.path.isfile(path):
            # Get a log warning
            logger.warning(f"File {path} does not exist.")

            # Show the message in the UI
            self.message_bar.pushWarning("Invalid File", f"File does not exist: {path}")
            return

        # Check if the path is a valid output file before proceeding
        if not is_output_db_file(path):
            # Get a log warning
            logger.warning(f"File {path} is not a valid output database.")

            # Show the message in the UI
            self.message_bar.pushWarning(
                "Invalid Results File", "File is not a valid output database."
            )

            return

        s = QgsSettings()
        s.setValue("OpenALAQS/last_result_file_path", path)

        self.updateMinMaxGUI(path)
        self.populate_source_types()

    def source_name_changed(self):
        # reset calculation
        self._emission_calculation_ = None
        # self._emission_calculation_configuration_widget = None

    def source_type_changed(self, *args, **kwargs):
        """
        This function updates the UI based on the new source type chosen by the
        user (e.g. list all gates, taxiways, roadways, etc.)
        :return:
        """

        # reset calculation
        self._emission_calculation_ = None
        inventory_path = self.ui.result_file_path.filePath()
        module_name = self.ui.source_types.currentText()

        EmissionSourceModule = SourceModuleRegistry().get_module(module_name)

        if EmissionSourceModule is None:
            return

        # instantiate module to get access to the sources
        em_config = {"database_path": inventory_path}
        if module_name == "MovementSource":
            widget_values = self._emission_calculation_configuration_widget.get_values()
            em_config.update(widget_values)
            em_config["receptors"] = self._receptor_points

        mod_ = EmissionSourceModule(em_config)
        mod_.loadSources()

        self.ui.source_names.clear()
        self.ui.source_names.addItem("all")
        for source_name_ in mod_.getSourceNames():
            self.ui.source_names.addItem(source_name_)

    def update_emissions(self):

        inventory_path = self.ui.result_file_path.filePath()

        if not Path(inventory_path).exists() or not Path(inventory_path).is_file():
            logger.error(
                "Inventory path `%s` is not a file!",
                inventory_path,
            )
            return

        # Build config from GUI
        config = self._build_config_from_gui(inventory_path)
        if config is None:
            return

        # Run calculation via service
        result = self._emission_calculator_service.calculate_emissions(config)

        if not result.success:
            logger.error(f"Emission calculation failed: {result.error_message}")
            self.message_bar.pushWarning(
                "Calculation Failed", result.error_message or "Unknown error"
            )
            return

        # Show warnings if any
        for warning in result.warnings:
            logger.warning(warning)

        # Store reference to the calculation for output modules
        self._emission_calculation_ = (
            self._emission_calculator_service.get_calculation()
        )

        logger.info("Emissions updated successfully")

    def get_values(self):
        """
        This function is used to pass data back to the main alaqs.py class when the UI exits.
        """
        return self._return_values

    def _build_config_from_gui(
        self, inventory_path: str
    ) -> Optional[EmissionCalculationConfig]:
        """
        Build an EmissionCalculationConfig from the current GUI state.

        :param inventory_path: Path to the inventory database
        :return: EmissionCalculationConfig or None if building fails
        """
        try:
            # Get airport reference data from database
            project_database = ProjectDatabase()
            project_database_path = getattr(project_database, "path", None)
            project_database.path = inventory_path
            study_data = alaqs.load_study_setup()
            ref_latitude = study_data.get("airport_latitude", 0.0)
            ref_longitude = study_data.get("airport_longitude", 0.0)
            ref_altitude = study_data.get("airport_elevation", 0.0)

            # Restore original database path
            if project_database_path is None:
                del project_database.path
            else:
                project_database.path = project_database_path

            # Build grid configuration
            grid_config = {
                "x_cells": 100,
                "y_cells": 100,
                "z_cells": 1,
                "x_resolution": 100,
                "y_resolution": 100,
                "z_resolution": 100,
                "reference_latitude": ref_latitude,
                "reference_longitude": ref_longitude,
                "reference_altitude": ref_altitude,
            }

            # Get values from configuration widget
            em_config = self._emission_calculation_configuration_widget.get_values()

            # Get source selection
            selected_source_type = self.ui.source_types.currentText()
            source_name = self.ui.source_names.currentText()
            source_names = (
                [source_name] if source_name and source_name.lower() != "all" else []
            )

            # Get pollutant
            pollutant = self.ui.pollutants_names.currentText()

            # Build the config object
            config = EmissionCalculationConfig(
                db_path=inventory_path,
                start_dt_inclusive=datetime.fromisoformat(
                    em_config["start_dt_inclusive"]
                ),
                end_dt_inclusive=datetime.fromisoformat(em_config["end_dt_inclusive"]),
                time_interval=timedelta(seconds=int(em_config["time_interval"])),
                pollutant=pollutant,
                method=em_config.get("method", "bymode"),
                source_type=selected_source_type,
                source_names=source_names,
                vertical_limit_m=em_config.get("vertical_limit_m", 914.4),
                should_apply_nox_corrections=em_config.get(
                    "should_apply_nox_corrections", False
                ),
                source_dynamics=em_config.get("source_dynamics", "none"),
                grid_config=grid_config,
                receptor_points=self._receptor_points,
                dispersion_modules_config=self.getDispersionModulesConfiguration(),
                output_modules_config=self.getOutputModulesConfiguration(),
            )

            return config

        except Exception as e:
            logger.error(f"Failed to build config from GUI: {e}", exc_info=True)
            self.message_bar.pushWarning(
                "Configuration Error", f"Failed to build configuration: {str(e)}"
            )
            return None


class OpenAlaqsDispersionAnalysis(QtWidgets.QDialog):
    """
    This class provides a dialog that launches the Dispersion Analysis
    """

    settings_schema = {
        "start_dt_inclusive": {
            "label": "Start (incl.)",
            "widget_type": QtWidgets.QDateTimeEdit,
            "initial_value": datetime(2023, 3, 1, 0, 0, 0),
        },
        "end_dt_inclusive": {
            "label": "End (incl.)",
            "widget_type": QtWidgets.QDateTimeEdit,
            "initial_value": datetime(2023, 3, 1, 23, 0, 0),
        },
        "averaging": {
            "label": "Averaging",
            "widget_type": QtWidgets.QComboBox,
            "initial_value": "annual mean",
            "widget_config": {
                "options": [
                    "hourly",
                    "8-hours mean",
                    "daily mean",
                    "annual mean",
                ],
            },
        },
        "pollutant": {
            "label": "Pollutant",
            "widget_type": QtWidgets.QComboBox,
            "initial_value": None,
            "widget_config": {
                "options": list(
                    p.value
                    for p in (
                        PollutantType.CO2,
                        PollutantType.CO,
                        PollutantType.HC,
                        PollutantType.NOx,
                        PollutantType.SOx,
                        PollutantType.PM10,
                    )
                ),
            },
        },
        "is_uncertainty_enabled": {
            "label": "Enable Uncertainty",
            "widget_type": QtWidgets.QCheckBox,
            "initial_value": False,
        },
    }

    def __init__(self, iface=None):
        """
        Initialises QDialog that displays the about UI for the plugin.
        """
        main_window = iface.mainWindow() if iface is not None else None
        QtWidgets.QDialog.__init__(self, main_window)

        # store the pointer to the QGIS interface
        self._iface = iface

        # Setup the user interface from Designer
        Ui_DialogRunAUSTAL, _ = loadUiType(
            os.path.join(os.path.dirname(__file__), "ui", "ui_run_austal.ui")
        )
        self.ui = Ui_DialogRunAUSTAL()
        self.ui.setupUi(self)
        
        # Set default values for calculation configuration widgets and make
        # them read-only for the moment — they are populated from the loaded file.

        # TODO: Implement the averaging strategy and enable to change the time
        if hasattr(self.ui, 'startDtEdit'):
            self.ui.startDtEdit.setDateTime(QtCore.QDateTime(2023, 3, 1, 0, 0, 0))
            self.ui.startDtEdit.setEnabled(False)
        if hasattr(self.ui, 'endDtEdit'):
            self.ui.endDtEdit.setDateTime(QtCore.QDateTime(2023, 3, 1, 23, 0, 0))
            self.ui.endDtEdit.setEnabled(False)
        if hasattr(self.ui, 'averagingCombo'):
            idx = self.ui.averagingCombo.findText("annual mean")
            if idx >= 0:
                self.ui.averagingCombo.setCurrentIndex(idx)
        
        # Set locale for coordinate and resolution spinboxes to use point as decimal separator
        c_locale = QtCore.QLocale(QtCore.QLocale.C)
        self.ui.refLatSpinBox.setLocale(c_locale)
        self.ui.refLonSpinBox.setLocale(c_locale)
        self.ui.xResolutionSpinBox.setLocale(c_locale)
        self.ui.yResolutionSpinBox.setLocale(c_locale)
        self.ui.zResolutionSpinBox.setLocale(c_locale)
        self.ui.refAltSpinBox.setLocale(c_locale)
        
        # Immediately hide gray feedback/summary boxes that appear in collapsible sections
        # These should only be visible when their parent sections are expanded
        self.ui.currentGridSummaryLabel.setVisible(True)
        self.ui.alaqsGridStatusLabel.setVisible(True)

        # Setup collapsible sections
        self._setup_collapsible_sections()

        # Connect grid checkbox from the result visualisation section toggle to update visualisation status
        self.ui.alaqsGridGroupBox.toggled.connect(self._update_visualization_status_label)

        # initialize calculation
        self._conc_calculation_ = None
        self._concentration_visualization_widget = ModuleConfigurationWidget(
            settings_schema=self.settings_schema
        )
        self.resetConcentrationCalculationConfiguration()
        self.updateMinMaxGUI()

        # Update the averaging option menu such that only the annual mean is enabled
        self._setup_averaging_options()
        
        # Initialize current grid configuration - stores in-memory grid values
        # These values are updated whenever spinboxes change and are used for calculations
        # until the user closes the dialog
        self._current_grid_config = None
        
        # G1: Snapshot of the grid as originally loaded from file and used to detect
        # whether the user has modified the spinboxes after loading.
        self._g1_original_grid_config = None
        self._g1_loaded_file_path = None
        
        # Separate grid loaded from Grid Management in Result Visualisation.
        # This is independent of the spinboxes and overrides the spinbox grid
        # for visualisation purposes only.
        self._visualization_grid_config = None
        self._visualization_grid_file_path = None
        
        # Track whether results are available (AUSTAL ran or results directory loaded)
        self._results_loaded = False
        
        # Track whether AUSTAL was actually run (vs results loaded from directory)
        self._austal_ran = False
        
        # Track whether AUSTAL input files have been successfully generated
        self._austal_input_files_generated = False

        # Track the directory where input files were generated
        self._generated_austal_work_dir = None
        
        # Snapshot of grid at the moment AUSTAL ran and never read spinboxes
        # dynamically for the visualisation status.
        self._austal_grid_config = None

        s = QgsSettings()
        last_alaqs_file_path = s.value("OpenALAQS/last_alaqs_file_path", "")
        last_work_directory_path = s.value("OpenALAQS/last_work_directory_path", "")
        last_a2k_executable_path = s.value("open_alaqs/a2k_executable_path", "")
        self.ui.a2k_executable_path.setFilter("AUSTAL Executable (austal.exe austal)")
        self.ui.a2k_executable_path.setDialogTitle("Select AUSTAL Executable File")
        self.ui.a2k_executable_path.setFilePath(last_a2k_executable_path)
        self.ui.a2k_executable_path.fileChanged.connect(
            self.a2k_executable_path_file_changed
        )
        # Set initial status for executable if one was saved
        if last_a2k_executable_path and os.path.isfile(last_a2k_executable_path):
            executable_name = os.path.basename(last_a2k_executable_path)
            status_text = f"Executable Loaded. File: {executable_name}"
            self.ui.executableStatusLabel.setText(status_text)
            self.ui.executableStatusLabel.setStyleSheet("background-color: #d4edda; padding: 8px; border-radius: 4px; border-left: 4px solid #28a745; color: #155724; font-weight: bold;")
        else:
            status_text = "No Executable Loaded\nPlease select the AUSTAL executable file to proceed."
            self.ui.executableStatusLabel.setText(status_text)
            self.ui.executableStatusLabel.setStyleSheet("background-color: #fff3cd; padding: 8px; border-radius: 4px; color: #856404; border-left: 4px solid #ffc107; font-weight: bold;")
        self.ui.work_directory_path.setStorageMode(QgsFileWidget.GetDirectory)
        self.ui.work_directory_path.setDialogTitle(
            "Select AUSTAL Input Files (.txt, .dmna, etc.) Directory"
        )
        self.ui.work_directory_path.setFilePath(last_work_directory_path)
        self.ui.work_directory_path.fileChanged.connect(
            self._on_work_directory_path_changed
        )
        # Set initial status for work directory if one was saved
        if os.path.isdir(last_work_directory_path):
            dir_name = os.path.basename(last_work_directory_path)
            status_text = f"Input Directory Loaded. Directory: {dir_name}"
            self.ui.existingFilesStatusLabel.setText(status_text)
            self.ui.existingFilesStatusLabel.setStyleSheet("background-color: #d4edda; padding: 8px; border-radius: 4px; border-left: 4px solid #28a745; color: #155724; font-weight: bold;")
        else:
            status_text = "No Input Directory Loaded. Select directory with AUSTAL input files (.txt, .dmna, etc.)"
            self.ui.existingFilesStatusLabel.setText(status_text)
            self.ui.existingFilesStatusLabel.setStyleSheet("background-color: #fff3cd; padding: 8px; border-radius: 4px; color: #856404; border-left: 4px solid #ffc107; font-weight: bold;")
        self.ui.alaqs_file_path.setFilter("ALAQS (*.alaqs)")
        self.ui.alaqs_file_path.setDialogTitle("Select ALAQS Output File")
        self.ui.alaqs_file_path.setFilePath(last_alaqs_file_path)
        self.ui.alaqs_file_path.fileChanged.connect(self.load_alaqs_source_file)

        if os.path.isfile(last_alaqs_file_path):
            self.load_alaqs_source_file(last_alaqs_file_path)

        self.ui.RunA2K.clicked.connect(self.run_austal)
        
        # Initialize execution status label
        self.ui.executionStatusLabel.setText("Status: Idle")
        self.ui.executionStatusLabel.setStyleSheet("background-color: #fff3cd; padding: 8px; border-radius: 4px; color: #856404; border-left: 4px solid #ffc107; font-weight: bold;")

        # Setup results work directory widget - auto-load when path changes
        self.ui.resultsWorkDirectoryPath.setStorageMode(QgsFileWidget.GetDirectory)
        self.ui.resultsWorkDirectoryPath.setDialogTitle("Select Work Directory with AUSTAL Results")
        self.ui.resultsWorkDirectoryPath.fileChanged.connect(self._on_results_directory_changed)

        # Setup grid source file widget - auto-load when path changes
        last_grid_file_path = s.value("OpenALAQS/last_grid_file_path", "")
        self.ui.gridSourceFilePath.setFilter("Grid Files (*.csv *.alaqs);;CSV Files (*.csv);;OpenALAQS Files (*.alaqs);;All Files (*)")
        self.ui.gridSourceFilePath.setDialogTitle("Select Grid Configuration File")
        self.ui.gridSourceFilePath.setFilePath(last_grid_file_path)
        self.ui.gridSourceFilePath.fileChanged.connect(self._on_grid_source_file_changed)
        
        # If a grid file was saved, load it immediately
        if last_grid_file_path and os.path.isfile(last_grid_file_path):
            self._on_grid_source_file_changed(last_grid_file_path)

        self.ui.ResultsTable.clicked.connect(
            lambda: self.runOutputModule("TableViewDispersionModule")
        )
        self.ui.VisualiseResults.clicked.connect(
            lambda: self.runOutputModule("QGISVectorLayerDispersionModule")
        )
        self.ui.PlotTimeSeries.clicked.connect(
            lambda: self.runOutputModule("TimeSeriesDispersionModule")
        )

        # Add AUSTAL Help Button
        self.ui.austal_help_button = QtWidgets.QPushButton("AUSTAL Help")
        self.ui.austal_help_button.clicked.connect(self.show_austal_help)

        # Find the layout containing the a2k_executable_path and add button next to it
        layout = self.ui.a2k_executable_path.layout()
        if layout is not None:
            layout.addWidget(self.ui.austal_help_button)

        # Setup external CSV file inputs
        self._setup_external_csv_inputs(s)

        # Add the save grid as csv button
        self.ui.saveGridCsvBtn.clicked.connect(self.save_grid_as_csv)
                
        # Add the update file button - gets file path from widget when clicked
        self.ui.updateFileBtn.clicked.connect(lambda: self.update_file(self.ui.gridSourceFilePath.filePath()))
        
        # Connect spinbox value changes to update grid status in real-time
        self.ui.xCellsSpinBox.valueChanged.connect(self._update_grid_status_label)
        self.ui.yCellsSpinBox.valueChanged.connect(self._update_grid_status_label)
        self.ui.zCellsSpinBox.valueChanged.connect(self._update_grid_status_label)
        self.ui.xResolutionSpinBox.valueChanged.connect(self._update_grid_status_label)
        self.ui.yResolutionSpinBox.valueChanged.connect(self._update_grid_status_label)
        self.ui.zResolutionSpinBox.valueChanged.connect(self._update_grid_status_label)
        self.ui.refLatSpinBox.valueChanged.connect(self._update_grid_status_label)
        self.ui.refLonSpinBox.valueChanged.connect(self._update_grid_status_label)
        self.ui.refAltSpinBox.valueChanged.connect(self._update_grid_status_label)


        self.resetModuleConfiguration(
            module_names=[
                "CSVDispersionModule",
                "TableViewDispersionModule",
                "TimeSeriesDispersionModule",
                "QGISVectorLayerDispersionModule",
            ]
        )

    def _setup_collapsible_sections(self):
        """Setup collapsible/expandable sections with proper hide/show behavior."""
        # Helper to recursively set visibility on all layout items including nested layouts
        def set_layout_visibility(layout, visible):
            """Recursively set visibility for all items in a layout."""
            if layout is None:
                return
            
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item is None:
                    continue
                
                # Handle widgets
                if item.widget():
                    item.widget().setVisible(visible)
                # Handle nested layouts
                elif item.layout():
                    set_layout_visibility(item.layout(), visible)
                # Handle spacers
                elif isinstance(item, QSpacerItem):
                    item.changeSize(item.sizeHint().width() if visible else 0, 
                                   item.sizeHint().height() if visible else 0)
        
        # Helper to make a groupbox collapsible by toggling its layout visibility
        def make_collapsible(groupbox):
            """Connect groupbox toggle to show/hide its contents."""
            if not hasattr(groupbox, 'isCheckable') or not groupbox.isCheckable():
                return
            
            # Get the layout
            layout = groupbox.layout()
            if layout is None:
                return
            
            # Set initial visibility based on checked state
            set_layout_visibility(layout, groupbox.isChecked())
            
            # Connect toggled signal with layout update
            def on_toggle(checked):
                set_layout_visibility(layout, checked)
                # Force layout recalculation and window resize
                self.ui.scrollArea.widget().layout().activate()
                self.ui.scrollArea.updateGeometry()
            groupbox.toggled.connect(on_toggle)
        
        # Setup collapsible sections
        make_collapsible(self.ui.executableGroupBox)
        make_collapsible(self.ui.visualisationGroupBox)
        make_collapsible(self.ui.gridManagementGroupBox)
        make_collapsible(self.ui.gridDetailsGroupBox)
        make_collapsible(self.ui.alaqsGridGroupBox)
        make_collapsible(self.ui.loadResultsGroupBox)
        
        # G1 grid status label (currentGridSummaryLabel) should always be visible
        # Refresh status message when grid details section is expanded
        self.ui.gridDetailsGroupBox.toggled.connect(self._update_grid_status_label)
        
        # G2 grid status label (alaqsGridStatusLabel) hides when section is collapsed
        def toggle_alaqs_grid_visibility(checked):
            self.ui.alaqsGridStatusLabel.setVisible(checked)
        
        self.ui.alaqsGridGroupBox.toggled.connect(toggle_alaqs_grid_visibility)
        self.ui.alaqsGridStatusLabel.setVisible(self.ui.alaqsGridGroupBox.isChecked())
        
        # Force hide all feedback labels when their parent sections are collapsed
        # These are specifically the gray boxes that appear as status/feedback
        self.ui.alaqsGridStatusLabel.setVisible(self.ui.alaqsGridGroupBox.isChecked())
        
        # CSV feedback visibility depends on CSV mode being selected
        self.ui.external_files_feedback.setVisible(self.ui.generateFromCsvRadio.isChecked())
        
        # Connect CSV mode toggle for feedback visibility
        def toggle_csv_feedback_visibility():
            self.ui.external_files_feedback.setVisible(self.ui.generateFromCsvRadio.isChecked())
        self.ui.generateFromCsvRadio.toggled.connect(toggle_csv_feedback_visibility)
        self.ui.useExistingFilesRadio.toggled.connect(toggle_csv_feedback_visibility)
        
        # Connect ALAQS feedback visibility
        def toggle_alaqs_feedback_visibility(checked):
            self.ui.alaqsGridStatusLabel.setVisible(checked)
        self.ui.alaqsGridGroupBox.toggled.connect(toggle_alaqs_feedback_visibility)
        
        # For calculation config, search for any feedback-like labels and hide them when collapsed
        def hide_calc_feedback(checked):
            # Hide any labels with feedback/status in the calculation config
            calc_layout = self.ui.calculationConfigGroupBox.layout()
            if calc_layout:
                for i in range(calc_layout.count()):
                    item = calc_layout.itemAt(i)
                    if item and item.widget() and 'feedback' in item.widget().objectName().lower():
                        item.widget().setVisible(checked)
        
        self.ui.calculationConfigGroupBox.toggled.connect(hide_calc_feedback)
        hide_calc_feedback(self.ui.calculationConfigGroupBox.isChecked())
        
        # Connect configuration toggles to update button state
        self.ui.loadResultsGroupBox.toggled.connect(self._update_result_buttons_state)
        self.ui.gridManagementGroupBox.toggled.connect(self._update_result_buttons_state)
        self.ui.alaqsGridGroupBox.toggled.connect(self._update_result_buttons_state)
        self.ui.resultsWorkDirectoryPath.fileChanged.connect(self._update_result_buttons_state)
        self.ui.alaqs_file_path.fileChanged.connect(self._update_result_buttons_state)
        self.ui.gridSourceFilePath.fileChanged.connect(self._update_result_buttons_state)
        # Connect spinbox changes for grid management
        self.ui.xCellsSpinBox.valueChanged.connect(self._update_result_buttons_state)
        self.ui.yCellsSpinBox.valueChanged.connect(self._update_result_buttons_state)

    def _update_result_buttons_state(self):
        """Update the enabled state of result visualisation buttons.
        
        Logic:
        - ResultsTable & PlotTimeSeries: Enable if (AUSTAL completed) OR (output files loaded)
          These don't require grid as they display tabular/time series data
        - VisualiseResults (Vector Layer): Enable if (AUSTAL completed with grid) OR (output files loaded AND grid provided)
          Vector visualisation requires grid for spatial information
        """
        # Check if AUSTAL ran successfully
        austal_completed = "Completed" in self.ui.executionStatusLabel.text()
        
        # Check if output files are loaded (results work directory selected)
        has_output_files = bool(
            self.ui.loadResultsGroupBox.isChecked() and 
            self.ui.resultsWorkDirectoryPath.filePath() and 
            os.path.isdir(self.ui.resultsWorkDirectoryPath.filePath())
        )
        
        # Check if grid is configured
        # Grid can come from: Grid Management spinboxes OR OpenALAQS file OR Grid Source File
        has_grid_from_management = bool(
            int(self.ui.xCellsSpinBox.value()) > 0 and
            int(self.ui.yCellsSpinBox.value()) > 0
        )
        
        has_grid_from_alaqs = bool(
            self.ui.alaqsGridGroupBox.isChecked() and 
            self.ui.alaqs_file_path.filePath() and
            os.path.isfile(self.ui.alaqs_file_path.filePath())
        )
        
        has_grid_from_file = bool(
            self.ui.gridSourceFilePath.filePath() and
            os.path.isfile(self.ui.gridSourceFilePath.filePath())
        )
        
        has_grid_config = bool(has_grid_from_management or has_grid_from_alaqs or has_grid_from_file)
        
        # Logic for table and time series - no grid required
        can_show_table_and_timeseries = bool(austal_completed or has_output_files)
        
        # Logic for vector visualisation - requires grid
        can_visualize_vector = bool(
            (austal_completed and has_grid_config) or 
            (has_output_files and has_grid_config)
        )
        
        # Enable/disable buttons accordingly
        # self.ui.ResultsTable.setEnabled(bool(can_show_table_and_timeseries))
        # self.ui.PlotTimeSeries.setEnabled(bool(can_show_table_and_timeseries))
        
        # TODO: ResultsTable and PlotTimeSeries buttons are currently disabled as they dont work with annual mean and they should be reactivated in future development
        self.ui.ResultsTable.setEnabled(False)
        self.ui.PlotTimeSeries.setEnabled(False)

        self.ui.VisualiseResults.setEnabled(bool(can_visualize_vector))

    def updateMinMaxGUI(self, db_path_=""):
        (time_start_calc_, time_end_calc_) = get_min_max_timestamps(db_path_)
        self.resetConcentrationCalculationConfiguration(
            config={
                "start_dt_inclusive": time_start_calc_,
                "end_dt_inclusive": time_end_calc_,
            }
        )
        # Populate the grayed-out start/end datetime entries with the real timestamps directly from the database.
        if hasattr(self.ui, 'startDtEdit'):
            self.ui.startDtEdit.setDateTime(
                QtCore.QDateTime(
                    time_start_calc_.year, time_start_calc_.month, time_start_calc_.day,
                    time_start_calc_.hour, time_start_calc_.minute, time_start_calc_.second,
                )
            )
        if hasattr(self.ui, 'endDtEdit'):
            self.ui.endDtEdit.setDateTime(
                QtCore.QDateTime(
                    time_end_calc_.year, time_end_calc_.month, time_end_calc_.day,
                    time_end_calc_.hour, time_end_calc_.minute, time_end_calc_.second,
                )
            )

    def getTimeSeries(self, db_path="") -> list[datetime]:
        time_series_ = get_inventory_timestamps(db_path)
        return time_series_

    def resetModuleConfiguration(self, module_names):  
        # Holder for future development
        pass

    def a2k_executable_path_file_changed(self, path):
        """
        Save the selected austal executable file path to restore on dialog
        opening
        """
        if path and os.path.isfile(path):
            settings = QgsSettings()
            settings.setValue("open_alaqs/a2k_executable_path", path)
            # Update status label with success styling and explicit information
            executable_name = os.path.basename(path)
            status_text = f"Executable Loaded. File: {executable_name}"
            self.ui.executableStatusLabel.setText(status_text)
            self.ui.executableStatusLabel.setStyleSheet("background-color: #d4edda; padding: 8px; border-radius: 4px; border-left: 4px solid #28a745; color: #155724; font-weight: bold;")
            logger.info(f"AUSTAL executable selected: {path}")
        else:
            status_text = "No Executable Loaded\nPlease select the AUSTAL executable file to proceed."
            self.ui.executableStatusLabel.setText(status_text)
            self.ui.executableStatusLabel.setStyleSheet("background-color: #fff3cd; padding: 8px; border-radius: 4px; color: #856404; border-left: 4px solid #ffc107; font-weight: bold;")
            if path:  # Only clear settings if a path was explicitly cleared
                settings = QgsSettings()
                settings.setValue("open_alaqs/a2k_executable_path", "")

    def set_feedback(self, feedback: str, is_success: bool) -> None:
        # Update alaqsGridStatusLabel with feedback styling
        if is_success:
            self.ui.alaqsGridStatusLabel.setText(feedback)
            self.ui.alaqsGridStatusLabel.setStyleSheet("background-color: #d4edda; padding: 8px; border-radius: 4px; border-left: 4px solid #28a745; color: #155724; font-weight: bold;")
        else:
            self.ui.alaqsGridStatusLabel.setText(feedback)
            self.ui.alaqsGridStatusLabel.setStyleSheet("background-color: #f8d7da; padding: 8px; border-radius: 4px; border-left: 4px solid #f5c6cb; color: #721c24; font-weight: bold;")

        # Update button state based on feedback
        self._update_result_buttons_state()

    def load_alaqs_source_file(self, filename):
        """
        Open a file browse window for the user to be able to locate and load an
         ALAQS output file
        """
        path = Path(filename)
        if not filename or not path.is_file() or path.suffix != ".alaqs":
            self.set_feedback("Please select an existing *_out.alaqs file", False)
            self.ui.alaqsGridStatusLabel.setText("No Grid selected")
            self.ui.alaqsGridStatusLabel.setStyleSheet("background-color: #fff3cd; padding: 8px; border-radius: 4px; border-left: 4px solid #ffc107; color: #856404; font-weight: bold;")
            
            # Clear G2 visualization grid when file is deselected
            self._visualization_grid_config = None
            self._visualization_grid_file_path = None
            self._update_visualization_status_label()
            return

        # Update status to loading state (blue)
        self.ui.alaqsGridStatusLabel.setText(f"Status: Loading {path.name}...")
        self.ui.alaqsGridStatusLabel.setStyleSheet("background-color: #cce5ff; padding: 8px; border-radius: 4px; border-left: 4px solid #0c63e4; color: #084298; font-weight: bold;")
        QtWidgets.QApplication.processEvents()  # Update UI immediately

        try:
            self.updateMinMaxGUI(filename)

            project_database = ProjectDatabase()
            project_database.path = filename

            study_data = alaqs.load_study_setup()

            # Read actual grid definition from the database
            conn = sqlite3.connect(filename)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                'SELECT x_cells, y_cells, z_cells, '
                'x_resolution, y_resolution, z_resolution, '
                'reference_latitude, reference_longitude '
                'FROM "grid_3d_definition"'
            )
            grid_row = cursor.fetchone()
            conn.close()

            if grid_row is not None:
                grid_configuration: GridConfig = {
                    "x_cells": int(grid_row["x_cells"]),
                    "y_cells": int(grid_row["y_cells"]),
                    "z_cells": int(grid_row["z_cells"]),
                    "x_resolution": float(grid_row["x_resolution"]),
                    "y_resolution": float(grid_row["y_resolution"]),
                    "z_resolution": float(grid_row["z_resolution"]),
                    "reference_latitude": float(grid_row["reference_latitude"]),
                    "reference_longitude": float(grid_row["reference_longitude"]),
                    "reference_altitude": study_data.get("airport_elevation", 0.0),
                }
            else:
                # Fallback if grid_3d_definition table is missing/empty
                grid_configuration: GridConfig = {
                    "x_cells": 100,
                    "y_cells": 100,
                    "z_cells": 1,
                    "x_resolution": 250,
                    "y_resolution": 250,
                    "z_resolution": 300,
                    "reference_latitude": study_data.get("airport_latitude", 0.0),
                    "reference_longitude": study_data.get("airport_longitude", 0.0),
                    "reference_altitude": study_data.get("airport_elevation", 0.0),
                }

            # Only proceed with full loading if concentration visualisation widget is initialized
            if self._concentration_visualization_widget is not None:
                # get values from GUI settings
                em_config = self._concentration_visualization_widget.get_values()

                start_dt = datetime.fromisoformat(em_config["start_dt_inclusive"])
                end_dt = datetime.fromisoformat(em_config["end_dt_inclusive"])

                time_series = self.getTimeSeries(filename)

                assert len(time_series) > 1

                time_interval = time_series[1] - time_series[0]

                self._conc_calculation_ = EmissionCalculation(
                    db_path=filename,
                    grid_config=grid_configuration,
                    start_dt=start_dt,
                    end_dt=end_dt,
                    time_interval=time_interval,
                )

            s = QgsSettings()
            s.setValue("OpenALAQS/last_alaqs_file_path", filename)

            self.set_feedback("Valid ALAQS file selected", True)
            # Update status label with loaded filename and grid parameters - green success
            grid_params = (f"Grid: {grid_configuration['x_cells']}×{grid_configuration['y_cells']}×{grid_configuration['z_cells']} cells | "
                          f"Res: {grid_configuration['x_resolution']:.0f}×{grid_configuration['y_resolution']:.0f}×{grid_configuration['z_resolution']:.0f}m | "
                          f"Ref: ({grid_configuration['reference_latitude']:.4f}°, {grid_configuration['reference_longitude']:.4f}°, {grid_configuration['reference_altitude']:.0f}m)")
            status_text = f"Loaded: {path.name}\n{grid_params}"
            self.ui.alaqsGridStatusLabel.setText(status_text)
            self.ui.alaqsGridStatusLabel.setStyleSheet("background-color: #d4edda; padding: 8px; border-radius: 4px; border-left: 4px solid #28a745; color: #155724; font-weight: bold;")

            # Store grid into G2 visualization config and update the visualization status label
            self._visualization_grid_config = grid_configuration.copy()
            self._visualization_grid_file_path = filename
            self._update_visualization_status_label()

        except sqlite3.OperationalError as err:
            self.set_feedback(f"Could not open database file: {err}.", False)
            self.ui.alaqsGridStatusLabel.setText("Status: Error loading file")
            self.ui.alaqsGridStatusLabel.setStyleSheet("background-color: #f8d7da; padding: 8px; border-radius: 4px; border-left: 4px solid #f5c6cb; color: #721c24; font-weight: bold;")
        except Exception as err:
            self.set_feedback(f"Error loading file: {err}", False)
            self.ui.alaqsGridStatusLabel.setText("Status: Error loading file")
            self.ui.alaqsGridStatusLabel.setStyleSheet("background-color: #f8d7da; padding: 8px; border-radius: 4px; border-left: 4px solid #f5c6cb; color: #721c24; font-weight: bold;")

    def _on_work_directory_path_changed(self, dirname: str) -> None:
        s = QgsSettings()

        if os.path.isdir(dirname):
            s.setValue("OpenALAQS/last_work_directory_path", dirname)
            # Update status label with success styling and explicit information
            dir_name = os.path.basename(dirname)
            status_text = f"Input Directory Loaded\nDirectory: {dir_name}"
            self.ui.existingFilesStatusLabel.setText(status_text)
            self.ui.existingFilesStatusLabel.setStyleSheet("background-color: #d4edda; padding: 8px; border-radius: 4px; border-left: 4px solid #28a745; color: #155724; font-weight: bold;")
            logger.info(f"Work directory selected: {dirname}")
        else:
            status_text = "No Input Directory Loaded\nSelect directory with AUSTAL input files (.txt, .dmna, etc.)"
            self.ui.existingFilesStatusLabel.setText(status_text)
            self.ui.existingFilesStatusLabel.setStyleSheet("background-color: #fff3cd; padding: 8px; border-radius: 4px; color: #856404; border-left: 4px solid #ffc107; font-weight: bold;")
            if dirname:  # Only clear settings if a path was explicitly cleared
                s.setValue("OpenALAQS/last_work_directory_path", "")

    def _on_results_directory_changed(self, results_dir: str) -> None:
        """Auto-load AUSTAL results when a valid work directory is selected."""
        if not results_dir or not os.path.isdir(results_dir):
            # Update status label when directory is deselected
            status_text = "No Results Directory Loaded. Select a directory with AUSTAL output files"
            self.ui.resultsStatusLabel.setText(status_text)
            self.ui.resultsStatusLabel.setStyleSheet("background-color: #fff3cd; padding: 8px; border-radius: 4px; color: #856404; border-left: 4px solid #ffc107; font-weight: bold;")
            self._results_loaded = False
            self._austal_ran = False
            self._update_visualization_status_label()
            self._update_result_buttons_state()
            return
        
        # Set the results directory as the work directory for visualisation
        self.ui.work_directory_path.setFilePath(results_dir)
        s = QgsSettings()
        s.setValue("OpenALAQS/last_work_directory_path", results_dir)
        
        # Update results status label with success styling and explicit information
        dir_name = os.path.basename(results_dir)
        status_text = f"Results Directory Loaded. Directory: {dir_name}"
        self.ui.resultsStatusLabel.setText(status_text)
        self.ui.resultsStatusLabel.setStyleSheet("background-color: #d4edda; padding: 8px; border-radius: 4px; border-left: 4px solid #28a745; color: #155724; font-weight: bold;")
        
        # Mark results as loaded and update visualisation status with grid details
        self._results_loaded = True
        self._austal_ran = False  # Results loaded from directory, not from AUSTAL run
        # Set header first so _update_visualization_status_label can preserve it
        self.ui.visualisationStatusLabel.setText(f"Results loaded from {os.path.basename(results_dir)}")
        self._update_visualization_status_label()
        
        # Auto-detect available pollutants and averaging options from result files
        try:
            self._detect_and_update_pollutants_and_averaging(results_dir)
        except Exception as _e:
            logger.warning('Could not auto-detect pollutants/averaging from results directory: %s', _e)

        # Update button state - will check if grid is also available
        self._update_result_buttons_state()
        
        logger.info(f"Results loaded from: {results_dir}")

    def _update_visualization_status_label(self) -> None:
        """Update the visualization status label.
        
        Priority for grid display (highest to lowest):
        1. G2 grid loaded from Result Visualisation section (alaqsGridGroupBox)
        2. If AUSTAL ran from OpenALAQS generation -> show G1 from that ALAQS file
        3. If AUSTAL ran from CSV generation -> show G1 from spinboxes
        4. If AUSTAL ran from existing files -> show default grid
        5. If results loaded from directory -> show default grid with warning
        6. No results -> show appropriate message
        """
        try:
            has_g2 = bool(
                self._visualization_grid_config 
                and self._visualization_grid_file_path
                and self.ui.alaqsGridGroupBox.isChecked()
            )
            
            # Helper to format grid config
            def _fmt(gc: dict) -> str:
                return (
                    f"Grid: {gc['x_cells']}×{gc['y_cells']}×{gc['z_cells']} cells | "
                    f"Resolution: {gc['x_resolution']:.0f}×{gc['y_resolution']:.0f}×"
                    f"{gc['z_resolution']:.0f}m | "
                    f"Reference: ({gc['reference_latitude']:.4f}°, "
                    f"{gc['reference_longitude']:.4f}°, "
                    f"{gc['reference_altitude']:.0f}m)"
                )
            
            # ---- No results loaded ----
            if not self._results_loaded:
                if has_g2:
                    text = f"Please run AUSTAL or load results.\n\n{_fmt(self._visualization_grid_config)}"
                else:
                    text = "Please run AUSTAL or load results."
                
                self.ui.visualisationStatusLabel.setText(text)
                self.ui.visualisationStatusLabel.setStyleSheet(
                    "background-color: #fff3cd; padding: 8px; border-radius: 4px; "
                    "border-left: 4px solid #ffc107; color: #856404; font-weight: bold;"
                )
            
            # ---- Results are available ----
            else:
                # Priority 1: G2 grid from Result Visualisation section
                if has_g2:
                    text = f"Using Grid from Result Visualisation Section\n{_fmt(self._visualization_grid_config)}"
                    bg_color = "background-color: #d4edda; padding: 8px; border-radius: 4px; border-left: 4px solid #28a745; color: #155724; font-weight: bold;"
                
                # Priority 2-4: AUSTAL ran - determine which grid was used
                elif self._austal_ran:
                    # Priority 2: AUSTAL ran from OpenALAQS generation (Option B)
                    if self.ui.generateFromAlaqsRadio.isChecked() and self._austal_grid_config:
                        alaqs_file = self.ui.alaqs_output_file_path.filePath()
                        text = f"Using Grid from OpenALAQS file: {os.path.basename(alaqs_file)}\n{_fmt(self._austal_grid_config)}"
                        bg_color = "background-color: #d4edda; padding: 8px; border-radius: 4px; border-left: 4px solid #28a745; color: #155724; font-weight: bold;"
                    
                    # Priority 3: AUSTAL ran from CSV generation (Option C)
                    elif self.ui.generateFromCsvRadio.isChecked() and self._austal_grid_config:
                        text = f"Using Grid from CSV Generation\n{_fmt(self._austal_grid_config)}"
                        bg_color = "background-color: #d4edda; padding: 8px; border-radius: 4px; border-left: 4px solid #28a745; color: #155724; font-weight: bold;"
                    
                    # Priority 4: AUSTAL ran from existing files (Option A) - default grid
                    elif self.ui.useExistingFilesRadio.isChecked():
                        if self._austal_grid_config:
                            text = f"Using Default Grid\n{_fmt(self._austal_grid_config)}\n\nRecommendation: Load a Grid from Result Visualisation section for accurate visualisation."
                        else:
                            text = "Using Default Grid\n\nRecommendation: Load a Grid from Result Visualisation section for accurate visualisation."
                        bg_color = "background-color: #fff3cd; padding: 8px; border-radius: 4px; border-left: 4px solid #ffc107; color: #856404; font-weight: bold;"
                    
                    else:
                        # Fallback
                        if self._austal_grid_config:
                            text = f"Using Default Grid\n{_fmt(self._austal_grid_config)}\n\nRecommendation: Load a Grid from Result Visualisation section."
                        else:
                            text = "Using Default Grid\n\nRecommendation: Load a Grid from Result Visualisation section."
                        bg_color = "background-color: #fff3cd; padding: 8px; border-radius: 4px; border-left: 4px solid #ffc107; color: #856404; font-weight: bold;"
                
                # Priority 5: Results loaded from directory (no AUSTAL run)
                else:
                    gc = self.get_current_grid_config()
                    if gc and any(gc.get(k, 0) > 0 for k in ["x_cells", "y_cells"]):
                        text = f"Using Default Grid\n{_fmt(gc)}\n\nRecommendation: Load a Grid from Result Visualisation section for accurate visualisation."
                    else:
                        text = "No Grid loaded. Please load a grid from Result Visualisation section for accurate visualisation."
                    bg_color = "background-color: #fff3cd; padding: 8px; border-radius: 4px; border-left: 4px solid #ffc107; color: #856404; font-weight: bold;"
                
                self.ui.visualisationStatusLabel.setText(text)
                self.ui.visualisationStatusLabel.setStyleSheet(bg_color)
            
            self.ui.visualisationStatusLabel.repaint()
        
        except Exception as e:
            logger.error("Failed to update visualisation status label: %s", e, exc_info=True)
            self.ui.visualisationStatusLabel.setText("Error updating visualization status")
            self.ui.visualisationStatusLabel.repaint()

    def _update_grid_status_label(self) -> None:
        """Update the G1 grid status label (currentGridSummaryLabel).

        Colours:
        - Yellow:  No grid values set (all zero) or no file loaded.
        - Green:   Grid loaded from file and spinboxes still match.
        - Blue:    Grid was loaded from a file but spinbox values have been
                   modified → warn user to save / update the file.
        """
        x_cells = int(self.ui.xCellsSpinBox.value())
        y_cells = int(self.ui.yCellsSpinBox.value())
        z_cells = int(self.ui.zCellsSpinBox.value())
        x_res = float(self.ui.xResolutionSpinBox.value())
        y_res = float(self.ui.yResolutionSpinBox.value())
        z_res = float(self.ui.zResolutionSpinBox.value())
        ref_lat = float(self.ui.refLatSpinBox.value())
        ref_lon = float(self.ui.refLonSpinBox.value())
        ref_alt = float(self.ui.refAltSpinBox.value())
        
        # Update the in-memory grid configuration
        self._current_grid_config = {
            "x_cells": x_cells,
            "y_cells": y_cells,
            "z_cells": z_cells,
            "x_resolution": x_res,
            "y_resolution": y_res,
            "z_resolution": z_res,
            "reference_latitude": ref_lat,
            "reference_longitude": ref_lon,
            "reference_altitude": ref_alt,
        }
        
        params_text = (f"Grid: {x_cells}×{y_cells}×{z_cells} cells | "
                       f"Res: {x_res:.0f}×{y_res:.0f}×{z_res:.0f}m | "
                       f"Ref: ({ref_lat:.4f}°, {ref_lon:.4f}°, {ref_alt:.0f}m)")
        
        if self._g1_original_grid_config is not None:
            # A file was loaded – check if spinboxes still match
            modified = any(
                self._current_grid_config[k] != self._g1_original_grid_config.get(k)
                for k in self._current_grid_config
            )
            if modified:
                # Blue – modified since load
                fname = os.path.basename(self._g1_loaded_file_path) if self._g1_loaded_file_path else "file"
                status_text = (f"Grid modified since loading from {fname}.\n"
                               f"{params_text}\n"
                               f"Save the grid or update the file to keep your changes.")
                style = ("background-color: #cce5ff; padding: 8px; border-radius: 4px; "
                         "border-left: 4px solid #0c63e4; color: #084298; font-weight: bold;")
            else:
                # Green – loaded and unmodified
                fname = os.path.basename(self._g1_loaded_file_path) if self._g1_loaded_file_path else ""
                status_text = f"Grid loaded from {fname}\n{params_text}"
                style = ("background-color: #d4edda; padding: 8px; border-radius: 4px; "
                         "border-left: 4px solid #28a745; color: #155724; font-weight: bold;")
        else:
            # No file loaded – show default grid status (yellow)
            status_text = f"Default Grid Loaded\n{params_text}"
            style = ("background-color: #fff3cd; padding: 8px; border-radius: 4px; "
                     "border-left: 4px solid #ffc107; color: #856404; font-weight: bold;")
        
        self.ui.currentGridSummaryLabel.setText(status_text)
        self.ui.currentGridSummaryLabel.setStyleSheet(style)

    def get_current_grid_config(self) -> dict:
        """
        Get the current grid configuration from spinboxes.
        
        This includes any unsaved modifications and is used for calculations.
        Returns the configuration even if it hasn't been saved to a file.
        
        Returns:
            dict: Grid configuration with keys: x_cells, y_cells, z_cells, x_resolution, 
                  y_resolution, z_resolution, reference_latitude, reference_longitude, 
                  reference_altitude
        """
        if self._current_grid_config is None:
            # Initialize if not yet set
            self._update_grid_status_label()
        return self._current_grid_config

    def _on_grid_source_file_changed(self, grid_file: str) -> None:
        """Handle G1 (Grid Configuration from 'Generate AUSTAL Input Files from CSV') file selection.
        
        This is the gridSourceFilePath widget inside gridManagementGroupBox (CSV generation).
        It loads a grid file and populates the spinboxes + currentGridSummaryLabel.
        
        MUST NEVER touch _visualization_grid_config, _visualization_grid_file_path,
        visualisationStatusLabel, or _update_visualization_status_label().
        Those belong to G2 (alaqsGridGroupBox / alaqs_file_path in Result Visualisation).
        """
        logger.info("[G1] _on_grid_source_file_changed called with: %s", grid_file)
        
        if not grid_file or not os.path.isfile(grid_file):
            logger.info("[G1] File deselected or invalid")
            s = QgsSettings()
            s.setValue("OpenALAQS/last_grid_file_path", "")
            self._g1_original_grid_config = None
            self._g1_loaded_file_path = None
            self.ui.currentGridSummaryLabel.setText("No Grid selected")
            self.ui.currentGridSummaryLabel.setStyleSheet(
                "background-color: #fff3cd; padding: 8px; border-radius: 4px; "
                "border-left: 4px solid #ffc107; color: #856404; font-weight: bold;")
            return
        
        # Store the selected grid file path for next session
        s = QgsSettings()
        s.setValue("OpenALAQS/last_grid_file_path", grid_file)
        
        try:
            grid_config = None
            
            # Try to parse as OA file (.alaqs)
            if grid_file.endswith('.alaqs'):
                try:
                    conn = sqlite3.connect(grid_file)
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute(
                        'SELECT x_cells, y_cells, z_cells, '
                        'x_resolution, y_resolution, z_resolution, '
                        'reference_latitude, reference_longitude '
                        'FROM "grid_3d_definition"'
                    )
                    grid_row = cursor.fetchone()
                    cursor.execute('SELECT airport_elevation FROM "user_study_setup"')
                    alt_row = cursor.fetchone()
                    conn.close()

                    if grid_row is None:
                        raise ValueError("No grid_3d_definition found in database")

                    grid_config = {
                        "x_cells": int(grid_row["x_cells"]),
                        "y_cells": int(grid_row["y_cells"]),
                        "z_cells": int(grid_row["z_cells"]),
                        "x_resolution": float(grid_row["x_resolution"]),
                        "y_resolution": float(grid_row["y_resolution"]),
                        "z_resolution": float(grid_row["z_resolution"]),
                        "reference_latitude": float(grid_row["reference_latitude"]),
                        "reference_longitude": float(grid_row["reference_longitude"]),
                        "reference_altitude": float(alt_row["airport_elevation"]) if alt_row else 0.0,
                    }
                except Exception as e:
                    logger.warning(f"Could not extract grid from ALAQS file: {e}")
                    grid_config = None
            
            # Try to parse as CSV file
            elif grid_file.endswith('.csv'):
                try:
                    import csv
                    with open(grid_file, 'r') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            grid_config = {
                                "x_cells": int(row.get("x_cells", 50)),
                                "y_cells": int(row.get("y_cells", 50)),
                                "z_cells": int(row.get("z_cells", 1)),
                                "x_resolution": float(row.get("x_resolution", 100)),
                                "y_resolution": float(row.get("y_resolution", 100)),
                                "z_resolution": float(row.get("z_resolution", 50)),
                                "reference_latitude": float(row.get("reference_latitude", 0.0)),
                                "reference_longitude": float(row.get("reference_longitude", 0.0)),
                                "reference_altitude": float(row.get("reference_altitude", 0.0)),
                            }
                            break  # Use first row
                except Exception as e:
                    logger.warning(f"Could not extract grid from CSV file: {e}")
                    grid_config = None
            
            # If we successfully loaded grid config, populate the spin boxes
            if grid_config:

                # Snapshot the original loaded values for modification detection
                self._g1_original_grid_config = grid_config.copy()
                self._g1_loaded_file_path = grid_file
                # Populate spinboxes with loaded values
                self.ui.xCellsSpinBox.setValue(grid_config["x_cells"])
                self.ui.yCellsSpinBox.setValue(grid_config["y_cells"])
                self.ui.zCellsSpinBox.setValue(grid_config["z_cells"])
                self.ui.xResolutionSpinBox.setValue(grid_config["x_resolution"])
                self.ui.yResolutionSpinBox.setValue(grid_config["y_resolution"])
                self.ui.zResolutionSpinBox.setValue(grid_config["z_resolution"])
                self.ui.refLatSpinBox.setValue(grid_config["reference_latitude"])
                self.ui.refLonSpinBox.setValue(grid_config["reference_longitude"])
                self.ui.refAltSpinBox.setValue(grid_config["reference_altitude"])
                # valueChanged only fires when the value changes; call explicitly so
                # the status label always updates even when loaded values match defaults.
                self._update_grid_status_label()
            else:

                self.ui.currentGridSummaryLabel.setText(f"Error: Could not parse {os.path.basename(grid_file)}")
                self.ui.currentGridSummaryLabel.setStyleSheet(
                    "background-color: #f8d7da; padding: 8px; border-radius: 4px; "
                    "border-left: 4px solid #f5c6cb; color: #721c24; font-weight: bold;")
                
        except Exception as e:
            logger.error("Failed to load grid file: %s", e, exc_info=True)

    def _setup_external_csv_inputs(self, s: QgsSettings) -> None:
        """Setup the external CSV file input widgets and connections.
        
        The UI has two modes:
        - Use existing AUSTAL input files from a work directory
        - Generate input files from CSV (emissions + meteorology)
        """
        # Configure output directory widget for CSV generation
        self.ui.output_directory_path.setStorageMode(QgsFileWidget.GetDirectory)
        self.ui.output_directory_path.setDialogTitle("Select Output Directory for Generated Files")
        last_output_dir = s.value("OpenALAQS/last_csv_output_directory_path", "")
        self.ui.output_directory_path.setFilePath(last_output_dir)
        self.ui.output_directory_path.fileChanged.connect(self._on_output_directory_changed)

        # Configure emissions CSV file widget
        self.ui.emissions_csv_path.setFilter("CSV Files (*.csv)")
        self.ui.emissions_csv_path.setDialogTitle("Select Emissions CSV File")
        last_emissions_csv = s.value("OpenALAQS/last_emissions_csv_path", "")
        self.ui.emissions_csv_path.setFilePath(last_emissions_csv)
        self.ui.emissions_csv_path.fileChanged.connect(self._on_emissions_csv_changed)

        # Configure meteorology CSV file widget
        self.ui.meteo_csv_path.setFilter("CSV Files (*.csv)")
        self.ui.meteo_csv_path.setDialogTitle("Select Meteorology CSV File")
        last_meteo_csv = s.value("OpenALAQS/last_meteo_csv_path", "")
        self.ui.meteo_csv_path.setFilePath(last_meteo_csv)
        self.ui.meteo_csv_path.fileChanged.connect(self._on_meteo_csv_changed)

        # Configure ALAQS output file widget for direct ALAQS generation
        self.ui.alaqs_output_file_path.setFilter("OpenALAQS Files (*.alaqs)")
        self.ui.alaqs_output_file_path.setDialogTitle("Select OpenALAQS Output File")
        last_alaqs_output_file = s.value("OpenALAQS/last_alaqs_output_file_path", "")
        self.ui.alaqs_output_file_path.setFilePath(last_alaqs_output_file)
        self.ui.alaqs_output_file_path.fileChanged.connect(self._on_alaqs_output_file_changed)

        # Configure ALAQS output work directory widget
        self.ui.alaqs_output_work_dir_path.setStorageMode(QgsFileWidget.GetDirectory)
        self.ui.alaqs_output_work_dir_path.setDialogTitle("Select Output Work Directory for Generated Files")
        last_alaqs_output_dir = s.value("OpenALAQS/last_alaqs_output_directory_path", "")
        self.ui.alaqs_output_work_dir_path.setFilePath(last_alaqs_output_dir)
        self.ui.alaqs_output_work_dir_path.fileChanged.connect(self._on_alaqs_output_directory_changed)

        # Connect ALAQS pollutant checkboxes to validation
        self.ui.alaqs_pollutant_nox.stateChanged.connect(self._validate_alaqs_generation_files)
        self.ui.alaqs_pollutant_co.stateChanged.connect(self._validate_alaqs_generation_files)
        self.ui.alaqs_pollutant_hc.stateChanged.connect(self._validate_alaqs_generation_files)
        self.ui.alaqs_pollutant_pm10.stateChanged.connect(self._validate_alaqs_generation_files)
        self.ui.alaqs_pollutant_sox.stateChanged.connect(self._validate_alaqs_generation_files)
        self.ui.alaqs_pollutant_co2.stateChanged.connect(self._validate_alaqs_generation_files)

        # Connect CSV pollutant checkboxes to validation
        self.ui.pollutant_nox.stateChanged.connect(self._validate_external_csv_files)
        self.ui.pollutant_co.stateChanged.connect(self._validate_external_csv_files)
        self.ui.pollutant_hc.stateChanged.connect(self._validate_external_csv_files)
        self.ui.pollutant_pm10.stateChanged.connect(self._validate_external_csv_files)
        self.ui.pollutant_sox.stateChanged.connect(self._validate_external_csv_files)
        self.ui.pollutant_co2.stateChanged.connect(self._validate_external_csv_files)

        # Connect AUSTAL quality level and mixing height controls to status update
        self.ui.alaqs_quality_level_spinbox.valueChanged.connect(self._validate_alaqs_generation_files)
        self.ui.alaqs_mixing_height_checkbox.stateChanged.connect(self._validate_alaqs_generation_files)
        self.ui.csv_quality_level_spinbox.valueChanged.connect(self._validate_external_csv_files)
        self.ui.csv_mixing_height_checkbox.stateChanged.connect(self._validate_external_csv_files)

        # Connect radio buttons to toggle input modes
        self.ui.useExistingFilesRadio.toggled.connect(self._on_input_mode_changed)
        self.ui.generateFromAlaqsRadio.toggled.connect(self._on_input_mode_changed)
        self.ui.generateFromCsvRadio.toggled.connect(self._on_input_mode_changed)

        # Connect generate button
        self.ui.generateFromCsvBtn.clicked.connect(self._generate_austal_input_files)

        # Initial state
        self._on_input_mode_changed()

    def _get_austal_config_from_ui(self, mode: str = "alaqs") -> dict:
        """Get AUSTAL configuration from UI controls.

        Args:
            mode: "alaqs" or "csv" to determine which UI controls to read

        Returns:
            dict: AUSTAL dispersion module configuration
        """
        if mode == "alaqs":
            quality_level = int(self.ui.alaqs_quality_level_spinbox.value())
            mixing_height = self.ui.alaqs_mixing_height_checkbox.isChecked()
        else:  # csv mode
            quality_level = int(self.ui.csv_quality_level_spinbox.value())
            mixing_height = self.ui.csv_mixing_height_checkbox.isChecked()
        
        return {
            "is_enabled": True,
            "quality_level": quality_level,
            "options_string": "NOSTANDARD;SCINOTAT;Kmax=1",
            "roughness_length_m": 0.2,
            "displacement_height_m": 1.2,
            "anemometer_height_m": 11.2,
            "mixing_height_enabled": mixing_height,
        }

    def _generate_austal_input_files(self):
        """Generate AUSTAL input files from CSV files or OpenALAQS output file.
        
        This method:
        1. Determines which generation path to use (CSV or ALAQS)
        2. Creates a subdirectory "AUSTAL" in the output directory
        3. For ALAQS mode: processes the OpenALAQS file for selected pollutants
        4. For CSV mode: TODO - implement CSV generation with selected pollutants
        5. Marks files as generated and stores the work directory
        6. Enables the Run AUSTAL button
        """
        use_alaqs = self.ui.generateFromAlaqsRadio.isChecked()
        use_csv = self.ui.generateFromCsvRadio.isChecked()
        
        # Determine the base output directory
        if use_alaqs:
            base_dir = self.ui.alaqs_output_work_dir_path.filePath()
            selected_pollutants = self._get_selected_alaqs_pollutants()
        elif use_csv:
            base_dir = self.ui.output_directory_path.filePath()
            selected_pollutants = self._get_selected_pollutants()
        else:
            return
        
        # Create AUSTAL_inputs subdirectory path
        austal_inputs_dir = os.path.join(base_dir, "AUSTAL")
        
        # Check if directory exists and is not empty
        if os.path.exists(austal_inputs_dir) and os.path.isdir(austal_inputs_dir):

            # Check if directory has any files
            dir_contents = os.listdir(austal_inputs_dir)
            if dir_contents:  # Directory is not empty

                # Show warning dialog
                reply = QtWidgets.QMessageBox.warning(
                    self,
                    "Directory Not Empty",
                    f"All existing files in this directory will be overwritten.\n\n"
                    f"Do you want to continue?",
                    QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                    QtWidgets.QMessageBox.StandardButton.No  # Default to No for safety
                )
                
                if reply == QtWidgets.QMessageBox.StandardButton.No:
                    # User chose not to overwrite and shows the messsage to select a different directory
                    if use_alaqs:
                        self.ui.alaqsGenerationStatusLabel.setText(
                            "Generation cancelled. Please select a different output directory."
                        )
                        self.ui.alaqsGenerationStatusLabel.setStyleSheet(
                            "background-color: #fff3cd; padding: 8px; border-radius: 4px; "
                            "border-left: 4px solid #ffc107; color: #856404; font-weight: bold;"
                        )
                    else:
                        self.ui.external_files_feedback.setText(
                            "Generation cancelled. Please select a different output directory."
                        )
                        self.ui.external_files_feedback.setStyleSheet(
                            "background-color: #fff3cd; padding: 8px; border-radius: 4px; "
                            "border-left: 4px solid #ffc107; color: #856404; font-weight: bold;"
                        )
                    return
                
                # User chose Yes then proceed with the overwritting
                logger.info(f"User confirmed overwriting files in: {austal_inputs_dir}")

                shutil.rmtree(austal_inputs_dir)
            
            # Create the AUSTAL inputs directory
            try:
                os.makedirs(austal_inputs_dir, exist_ok=True)
            except Exception as e:
                error_msg = f"Failed to create AUSTAL inputs directory: {e}"
                if use_alaqs:
                    self.ui.alaqsGenerationStatusLabel.setText(error_msg)
                    self.ui.alaqsGenerationStatusLabel.setStyleSheet("background-color: #f8d7da; padding: 8px; border-radius: 4px; border-left: 4px solid #f5c6cb; color: #721c24; font-weight: bold;")
                else:
                    self.ui.external_files_feedback.setText(error_msg)
                    self.ui.external_files_feedback.setStyleSheet("background-color: #f8d7da; padding: 8px; border-radius: 4px; border-left: 4px solid #f5c6cb; color: #721c24; font-weight: bold;")
                return
        
        try:
            if use_alaqs:
                # Generate from OpenALAQS output file for selected pollutants
                alaqs_file = self.ui.alaqs_output_file_path.filePath()
                self._generate_from_alaqs_file(alaqs_file, austal_inputs_dir, selected_pollutants)
            elif use_csv:
                # Generate from CSV files for selected pollutants
                emissions_csv = self.ui.emissions_csv_path.filePath()
                meteo_csv = self.ui.meteo_csv_path.filePath()
                grid_config = self.get_current_grid_config()

                logger.info(f"Generating AUSTAL input files from CSV for pollutants: {', '.join(selected_pollutants)}")
                logger.info(f"Grid config: {grid_config}")

                austal_cfg = self._get_austal_config_from_ui(mode="csv")
                generate_austal_from_csv(
                    emissions_csv_path=emissions_csv,
                    meteo_csv_path=meteo_csv,
                    grid_config=grid_config,
                    austal_config=austal_cfg,
                    output_dir=austal_inputs_dir,
                    selected_pollutants=selected_pollutants,
                )
        except Exception as e:
            error_msg = f"Error generating AUSTAL input files: {e}"
            if use_alaqs:
                self.ui.alaqsGenerationStatusLabel.setText(error_msg)
                self.ui.alaqsGenerationStatusLabel.setStyleSheet("background-color: #f8d7da; padding: 8px; border-radius: 4px; border-left: 4px solid #f5c6cb; color: #721c24; font-weight: bold;")
            else:
                self.ui.external_files_feedback.setText(error_msg)
                self.ui.external_files_feedback.setStyleSheet("background-color: #f8d7da; padding: 8px; border-radius: 4px; border-left: 4px solid #f5c6cb; color: #721c24; font-weight: bold;")
            logger.error(error_msg, exc_info=True)
            return
        
        # Mark files as generated and store directory
        self._austal_input_files_generated = True
        self._generated_austal_work_dir = austal_inputs_dir
        
        # Enable Run AUSTAL button after successful generation
        self.ui.RunA2K.setEnabled(True)
        
        # Update status
        status_msg = f"AUSTAL input files generated successfully. Path: {austal_inputs_dir}"
        if use_alaqs:
            self.ui.alaqsGenerationStatusLabel.setText(status_msg)
            self.ui.alaqsGenerationStatusLabel.setStyleSheet("background-color: #d4edda; padding: 8px; border-radius: 4px; border-left: 4px solid #28a745; color: #155724; font-weight: bold;")
        else:
            self.ui.external_files_feedback.setText(status_msg)
            self.ui.external_files_feedback.setStyleSheet("background-color: #d4edda; padding: 8px; border-radius: 4px; border-left: 4px solid #28a745; color: #155724; font-weight: bold;")

    def _generate_from_alaqs_file(self, alaqs_file: str, output_dir: str, selected_pollutants: list) -> None:
        """Generate AUSTAL input files from an OpenALAQS output file.
        
        Uses EmissionCalculation directly with source modules and the AUSTAL
        dispersion module to generate input files (austal.txt, series.dmna,
        grid .dmna files) for each selected pollutant.
        
        The *_out.alaqs file contains all necessary input data (movements,
        geometries, meteorology, profiles) but not pre-calculated emissions,
        so source modules must still run to calculate them. The AUSTAL 
        dispersion module is attached to distribute emissions onto the grid.
        
        Args:
            alaqs_file: Path to the OpenALAQS output file (*_out.alaqs)
            output_dir: Output directory where AUSTAL input files will be written
            selected_pollutants: List of selected pollutants to generate files for
        """
        logger.info(f"Generating AUSTAL input files from {alaqs_file}")
        logger.info(f"Selected pollutants: {', '.join(selected_pollutants)}")
        logger.info(f"Output directory: {output_dir}")
        
        # Get quality level and mixing height settings for status message
        quality_level = int(self.ui.alaqs_quality_level_spinbox.value())
        mixing_height_enabled = self.ui.alaqs_mixing_height_checkbox.isChecked()
        mixing_height_status = "enabled" if mixing_height_enabled else "disabled"
        logger.info(f"AUSTAL parameters - Quality level: {quality_level}, Mixing height: {mixing_height_status}")
        
        # Get time series from the ALAQS output file
        timestamps = get_inventory_timestamps(alaqs_file)
        if len(timestamps) < 2:
            raise ValueError("OpenALAQS file does not contain enough time steps (need at least 2)")
        
        start_dt = timestamps[0]
        end_dt = timestamps[-1]
        time_interval = timestamps[1] - timestamps[0]
        
        logger.info(f"Time range: {start_dt} to {end_dt}, interval: {time_interval}")
        
        # Read grid configuration from the ALAQS file
        conn = sqlite3.connect(alaqs_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            'SELECT x_cells, y_cells, z_cells, x_resolution, y_resolution, '
            'z_resolution, reference_latitude, reference_longitude '
            'FROM "grid_3d_definition" LIMIT 1'
        )
        grid_row = cursor.fetchone()
        conn.close()
        
        if grid_row is None:
            raise ValueError("No grid_3d_definition found in OpenALAQS file")
        
        grid_config: GridConfig = {
            "x_cells": int(grid_row["x_cells"]),
            "y_cells": int(grid_row["y_cells"]),
            "z_cells": int(grid_row["z_cells"]),
            "x_resolution": float(grid_row["x_resolution"]),
            "y_resolution": float(grid_row["y_resolution"]),
            "z_resolution": float(grid_row["z_resolution"]),
            "reference_latitude": float(grid_row["reference_latitude"]),
            "reference_longitude": float(grid_row["reference_longitude"]),
            "reference_altitude": 0.0,
        }
        
        logger.info(f"Grid configuration: {grid_config}")
        
        # Initialize EmissionCalculation directly (bypasses EmissionCalculatorService)
        emission_calc = EmissionCalculation(
            db_path=alaqs_file,
            grid_config=grid_config,
            start_dt=start_dt,
            end_dt=end_dt,
            time_interval=time_interval,
        )
        
        # Add all source modules (movements, area sources, parking, etc.)
        source_module_names = SourceModuleRegistry().get_module_names()
        for module_name in source_module_names:
            emission_calc.add_source_module(
                module_name,
                {
                    "method": "bymode",
                    "should_apply_nox_corrections": False,
                    "source_dynamics": "none",
                    "reference_altitude": grid_config.get("reference_altitude", 0.0),
                    "show_progress": False,
                    "receptors": None,
                },
            )
            logger.info(f"Added source module: {module_name}")
        
        # Add AUSTAL dispersion module for the selected pollutants
        austal_config = self._get_austal_config_from_ui()
        austal_config.update({
            "output_path": output_dir,
            "pollutant": None,  # Will be set per pollutant below
            "pollutants_list": selected_pollutants,
            "title": "OpenALAQS AUSTAL generation",
            "grid": emission_calc.get3DGrid(),
            "receptors": gpd.GeoDataFrame(),
        })
        
        emission_calc.add_dispersion_modules(["AUSTAL"], austal_config)
        logger.info(f"Added AUSTAL dispersion module with config: Quality level={austal_config['quality_level']}, Mixing height enabled={austal_config['mixing_height_enabled']}")
        logger.debug(f"Full AUSTAL config: {austal_config}")
        
        # Run the calculation: source modules calculate emissions,
        # AUSTAL dispersion module writes input files
        logger.info("Running emission calculation with AUSTAL dispersion...")
        emission_calc.run(
            source_names=["all"],
            vertical_limit_m=914.4,
            show_progress=True,
        )
        emission_calc.sortEmissionsByTime()
        
        logger.info(f"AUSTAL input files generated for pollutants: {', '.join(selected_pollutants)}")

    def _on_input_mode_changed(self) -> None:
        """Handle switching between existing files, generate from OpenALAQS, and generate from CSV modes."""
        use_existing = self.ui.useExistingFilesRadio.isChecked()
        use_alaqs = self.ui.generateFromAlaqsRadio.isChecked()
        use_csv = self.ui.generateFromCsvRadio.isChecked()

        # Show/hide and enable/disable the frames based on selection
        self.ui.existingFilesFrame.setVisible(use_existing)
        self.ui.existingFilesFrame.setEnabled(use_existing)
        self.ui.generateFromAlaqsFrame.setVisible(use_alaqs)
        self.ui.generateFromAlaqsFrame.setEnabled(use_alaqs)
        self.ui.generateFromCsvFrame.setVisible(use_csv)
        self.ui.generateFromCsvFrame.setEnabled(use_csv)

        # Show/hide the generate button - only visible when generating from OpenALAQS output or CSV
        self.ui.generateFromCsvBtn.setVisible(use_alaqs or use_csv)
        
        # Reset generation state when mode changes - need to regenerate files
        self._austal_input_files_generated = False
        self._generated_austal_work_dir = None

        # Validate and update feedback based on selected mode
        if use_existing:
            self.ui.RunA2K.setEnabled(bool(self.ui.work_directory_path.filePath() and 
                                          os.path.isdir(self.ui.work_directory_path.filePath())))
        elif use_alaqs:
            self._validate_alaqs_generation_files()
        elif use_csv:
            self._validate_external_csv_files()
        else:
            self.ui.RunA2K.setEnabled(False)

    def _on_alaqs_output_file_changed(self, path: str) -> None:
        """Handle OpenALAQS output file selection."""
        if os.path.isfile(path):
            s = QgsSettings()
            s.setValue("OpenALAQS/last_alaqs_output_file_path", path)
        self._validate_alaqs_generation_files()

    def _on_alaqs_output_directory_changed(self, dirname: str) -> None:
        """Handle OpenALAQS output directory selection."""
        if os.path.isdir(dirname):
            s = QgsSettings()
            s.setValue("OpenALAQS/last_alaqs_output_directory_path", dirname)
        self._validate_alaqs_generation_files()

    def _validate_alaqs_generation_files(self) -> None:
        """Validate the selected OpenALAQS output file and working directory."""
        alaqs_file = self.ui.alaqs_output_file_path.filePath()
        output_dir = self.ui.alaqs_output_work_dir_path.filePath()
        pollutants = self._get_selected_alaqs_pollutants()

        # Collect missing items
        missing = []
        if not alaqs_file or not os.path.isfile(alaqs_file):
            missing.append("OpenALAQS Emission Inventory (*_out.alaqs)")
        if not output_dir or not os.path.isdir(output_dir):
            missing.append("output directory")
        if not pollutants:
            missing.append("at least one pollutant")

        # Check if ALAQS file has grid_3d_definition if provided
        has_valid_grid = False
        if alaqs_file and os.path.isfile(alaqs_file):
            try:
                conn = sqlite3.connect(alaqs_file)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT x_cells, y_cells, z_cells FROM "grid_3d_definition" LIMIT 1'
                )
                grid_row = cursor.fetchone()
                conn.close()
                has_valid_grid = grid_row is not None
            except Exception:
                has_valid_grid = False

        if missing:
            self.ui.alaqsGenerationStatusLabel.setText(f"Missing {', '.join(missing)}")
            self.ui.alaqsGenerationStatusLabel.setStyleSheet("background-color: #fff3cd; padding: 8px; border-radius: 4px; border-left: 4px solid #ffc107; color: #856404; font-weight: bold;")
            self.ui.generateFromCsvBtn.setEnabled(False)
            # Keep Run AUSTAL enabled if files have already been generated (user may have deselected pollutant by mistake)
            if not self._austal_input_files_generated:
                self.ui.RunA2K.setEnabled(False)
            return

        if alaqs_file and os.path.isfile(alaqs_file) and not has_valid_grid:
            self.ui.alaqsGenerationStatusLabel.setText("Selected OpenALAQS output file (emission inventory *_out.alaqs) is not valid")
            self.ui.alaqsGenerationStatusLabel.setStyleSheet("background-color: #f8d7da; padding: 8px; border-radius: 4px; border-left: 4px solid #f5c6cb; color: #721c24; font-weight: bold;")
            self.ui.generateFromCsvBtn.setEnabled(False)
            # Keep Run AUSTAL enabled if files have already been generated
            if not self._austal_input_files_generated:
                self.ui.RunA2K.setEnabled(False)
            return

        # All inputs valid - enable generate button, but Run AUSTAL only after generation succeeds
        selected_list = ", ".join(pollutants)
        # Get quality level and mixing height for status message
        quality_level = int(self.ui.alaqs_quality_level_spinbox.value())
        mixing_height_enabled = self.ui.alaqs_mixing_height_checkbox.isChecked()
        mixing_height_status = "enabled" if mixing_height_enabled else "disabled"
        status_text = f"Ready to generate AUSTAL input files. Pollutants: {selected_list} | Quality level: {quality_level}, Mixing height: {mixing_height_status}"
        self.ui.alaqsGenerationStatusLabel.setText(status_text)
        self.ui.alaqsGenerationStatusLabel.setStyleSheet("background-color: #d4edda; padding: 8px; border-radius: 4px; border-left: 4px solid #28a745; color: #155724; font-weight: bold;")
        self.ui.generateFromCsvBtn.setEnabled(True)
        # Only enable Run AUSTAL if files have been generated
        self.ui.RunA2K.setEnabled(self._austal_input_files_generated)

    def _on_output_directory_changed(self, dirname: str) -> None:
        """Handle output directory selection for CSV generation."""
        if os.path.isdir(dirname):
            s = QgsSettings()
            s.setValue("OpenALAQS/last_csv_output_directory_path", dirname)
        self._validate_external_csv_files()

    def _on_emissions_csv_changed(self, path: str) -> None:
        """Handle emissions CSV file selection."""
        if os.path.isfile(path):
            s = QgsSettings()
            s.setValue("OpenALAQS/last_emissions_csv_path", path)
        self._validate_external_csv_files()

    def _on_meteo_csv_changed(self, path: str) -> None:
        """Handle meteorology CSV file selection."""
        if os.path.isfile(path):
            s = QgsSettings()
            s.setValue("OpenALAQS/last_meteo_csv_path", path)
        self._validate_external_csv_files()

    def _validate_external_csv_files(self) -> None:
        """Validate the selected external CSV files, output directory, and grid configuration."""
        output_dir = self.ui.output_directory_path.filePath()
        emissions_path = self.ui.emissions_csv_path.filePath()
        meteo_path = self.ui.meteo_csv_path.filePath()
        selected_pollutants = self._get_selected_pollutants()
        grid_config = self.get_current_grid_config()

        # Collect missing items
        missing = []
        if not output_dir or not os.path.isdir(output_dir):
            missing.append("output directory")
        if not emissions_path or not os.path.isfile(emissions_path):
            missing.append("emissions CSV")
        if not meteo_path or not os.path.isfile(meteo_path):
            missing.append("meteo CSV")
        if not selected_pollutants:
            missing.append("at least one pollutant")
        if not grid_config:
            missing.append("grid configuration (load or define in Grid Management section)")

        if missing:
            self.ui.external_files_feedback.setText(f"Missing {', '.join(missing)}")
            self.ui.external_files_feedback.setStyleSheet("background-color: #fff3cd; padding: 8px; border-radius: 4px; border-left: 4px solid #ffc107; color: #856404; font-weight: bold;")
            self.ui.generateFromCsvBtn.setEnabled(False)
            # Keep Run AUSTAL enabled if files have already been generated (user may have deselected pollutant by mistake)
            if not self._austal_input_files_generated:
                self.ui.RunA2K.setEnabled(False)
            return

        # All inputs valid - enable generate button, but Run AUSTAL only after generation succeeds
        selected_list = ", ".join(selected_pollutants)
        # Get quality level and mixing height for status message
        quality_level = int(self.ui.csv_quality_level_spinbox.value())
        mixing_height_enabled = self.ui.csv_mixing_height_checkbox.isChecked()
        mixing_height_status = "enabled" if mixing_height_enabled else "disabled"

        self.ui.external_files_feedback.setText(f"Ready to generate AUSTAL input files. Pollutants: {selected_list} | Quality level: {quality_level}, Mixing height: {mixing_height_status}")
        self.ui.external_files_feedback.setStyleSheet("background-color: #d4edda; padding: 8px; border-radius: 4px; border-left: 4px solid #28a745; color: #155724; font-weight: bold;")
        self.ui.generateFromCsvBtn.setEnabled(True)
        # Only enable Run AUSTAL if files have been generated
        self.ui.RunA2K.setEnabled(self._austal_input_files_generated)

    # Display the text when the user presses the AUSTAL HELP buttton
    def show_austal_help(self):
        """
        Display AUSTAL setup instructions in a dialog
        """
        help_text = """
        <b>AUSTAL Setup Instructions</b><br><br>

        <b>Download AUSTAL:</b><br>
        Visit: <a href="https://www.umweltbundesamt.de/en/topics/air/air-quality-control-in-europe/download">
        AUSTAL Download Page</a><br><br>

        <b>Available Versions:</b><br>
        • Windows: AUSTAL_3.3.0.zip<br>
        • Linux: AUSTAL_3.3.0.zip<br><br>

        <b>Installation Steps:</b><br>
        1. Download the AUSTAL base package for your OS<br>
        2. Extract the package to your desired location<br>
        3. Replace austal.settings with the one provided here: <a href="https://github.com/eurocontrol-asu/open_alaqs/tree/main/documents/AUSTAL/austal.settings"> austal.settings </a> <br>
        4. Ensure the AUSTAL executable is in your system PATH<br>
        5. Select the austal.exe (or austal) file above<br><br>

        <b>Configuration Files:</b><br>
        • <a href="https://github.com/eurocontrol-asu/open_alaqs/tree/main/documents/AUSTAL/austal.settings">
        austal.settings</a> - Main AUSTAL configuration file<br>
        • AST_en and DIA_en - English language files (included in AUSTAL distribution)<br><br>

        <b>For More Information:</b><br>
        See <a href="https://github.com/eurocontrol-asu/open_alaqs/tree/main/documents/AUSTAL//AUSTAL.md">
        AUSTAL.md</a> in the OpenALAQS documentation folder.
        """

        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setWindowTitle("AUSTAL Setup Help")
        msg_box.setText(help_text)
        msg_box.setTextFormat(QtCore.Qt.TextFormat.RichText)
        msg_box.setIcon(QtWidgets.QMessageBox.Icon.Information)
        msg_box.exec()

    def _get_austal_work_directory(self) -> str:
        """Get the work directory for AUSTAL based on selected input mode.
        
        For generation modes (CSV/ALAQS), returns the directory where input files
        were generated. For existing files mode, returns the selected directory.
        """
        # If files have been generated, use the generated directory
        if self._austal_input_files_generated and self._generated_austal_work_dir:
            return self._generated_austal_work_dir
        
        # Otherwise, determine based on selected mode
        if self.ui.generateFromAlaqsRadio.isChecked():
            # Use the output directory from OpenALAQS generation
            return str(self.ui.alaqs_output_work_dir_path.filePath())
        elif self.ui.generateFromCsvRadio.isChecked():
            # Use the output directory from CSV generation
            return str(self.ui.output_directory_path.filePath())
        else:
            # Use the existing files work directory
            return str(self.ui.work_directory_path.filePath())

    def _get_selected_pollutants(self) -> list:
        """Get list of selected pollutants for CSV generation mode."""
        pollutants = []
        if self.ui.pollutant_nox.isChecked():
            pollutants.append("NOx")
        if self.ui.pollutant_co.isChecked():
            pollutants.append("CO")
        if self.ui.pollutant_hc.isChecked():
            pollutants.append("HC")
        if self.ui.pollutant_pm10.isChecked():
            pollutants.append("PM10")
        if self.ui.pollutant_sox.isChecked():
            pollutants.append("SOx")
        if self.ui.pollutant_co2.isChecked():
            pollutants.append("CO2")
        return pollutants

    def _get_selected_alaqs_pollutants(self) -> list:
        """Get list of selected pollutants for OpenALAQS generation mode."""
        pollutants = []
        if self.ui.alaqs_pollutant_nox.isChecked():
            pollutants.append("NOx")
        if self.ui.alaqs_pollutant_co.isChecked():
            pollutants.append("CO")
        if self.ui.alaqs_pollutant_hc.isChecked():
            pollutants.append("HC")
        if self.ui.alaqs_pollutant_pm10.isChecked():
            pollutants.append("PM10")
        if self.ui.alaqs_pollutant_sox.isChecked():
            pollutants.append("SOx")
        if self.ui.alaqs_pollutant_co2.isChecked():
            pollutants.append("CO2")
        return pollutants

    def _validate_austal_inputs(self) -> tuple[bool, str]:
        """Validate all required inputs for AUSTAL based on selected input mode.
        
        Returns:
            tuple: (is_valid, error_message)
        """
        # Check executable is selected
        if not self.ui.a2k_executable_path.filePath() or not os.path.isfile(self.ui.a2k_executable_path.filePath()):
            return False, "Please select a valid AUSTAL executable file (Section 1)"
        
        # Check mode-specific requirements
        if self.ui.useExistingFilesRadio.isChecked():
            work_dir = self.ui.work_directory_path.filePath()
            if not work_dir or not os.path.isdir(work_dir):
                return False, "Please select a valid work directory with AUSTAL input files"
        
        elif self.ui.generateFromAlaqsRadio.isChecked():
            alaqs_file = self.ui.alaqs_output_file_path.filePath()
            output_dir = self.ui.alaqs_output_work_dir_path.filePath()
            pollutants = self._get_selected_alaqs_pollutants()
            
            if not alaqs_file or not os.path.isfile(alaqs_file):
                return False, "Please select a valid OpenALAQS output file"
            if not output_dir or not os.path.isdir(output_dir):
                return False, "Please select a valid output work directory"
            if not pollutants:
                return False, "Please select at least one pollutant"
            
            # Check for grid_3d_definition
            try:
                conn = sqlite3.connect(alaqs_file)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT 1 FROM "grid_3d_definition" LIMIT 1')
                if cursor.fetchone() is None:
                    conn.close()
                    return False, "Selected OpenALAQS file does not have a valid grid_3d_definition"
                conn.close()
            except Exception as e:
                return False, f"Error reading OpenALAQS file: {e}"
        
        elif self.ui.generateFromCsvRadio.isChecked():
            output_dir = self.ui.output_directory_path.filePath()
            emissions_csv = self.ui.emissions_csv_path.filePath()
            meteo_csv = self.ui.meteo_csv_path.filePath()
            pollutants = self._get_selected_pollutants()
            
            if not output_dir or not os.path.isdir(output_dir):
                return False, "Please select a valid output directory"
            if not emissions_csv or not os.path.isfile(emissions_csv):
                return False, "Please select a valid emissions CSV file"
            if not meteo_csv or not os.path.isfile(meteo_csv):
                return False, "Please select a valid meteorology CSV file"
            if not pollutants:
                return False, "Please select at least one pollutant"
        
        return True, ""


    @catch_errors
    def run_austal(self, *args, **kwargs):
        from subprocess import PIPE, Popen

        try:
            # Validate all inputs before running
            is_valid, error_message = self._validate_austal_inputs()
            if not is_valid:
                self.ui.executionStatusLabel.setText(f"Status: Validation Failed: {error_message}")
                self.ui.executionStatusLabel.setStyleSheet("background-color: #fff3cd; padding: 8px; border-radius: 4px; border-left: 4px solid #ffc107; color: #856404; font-weight: bold;")
                QtWidgets.QMessageBox.warning(
                    self,
                    "Input Validation Failed",
                    f"Unable to run AUSTAL:\n\n{error_message}"
                )
                return

            # Update status to running
            self.ui.executionStatusLabel.setText("Status: Running AUSTAL...")
            self.ui.executionStatusLabel.setStyleSheet("background-color: #cce5ff; padding: 8px; border-radius: 4px; border-left: 4px solid #0c63e4; color: #084298; font-weight: bold;")
            QtWidgets.QApplication.processEvents()  # Update UI immediately
            
            austal_ = str(self.ui.a2k_executable_path.filePath())
            logger.info("AUSTAL directory:%s" % austal_)
            work_dir = self._get_austal_work_directory()
            logger.info("AUSTAL input files directory:%s" % work_dir)

            if not work_dir or not os.path.isdir(work_dir):
                self.ui.executionStatusLabel.setText("Status: Error - Invalid input directory")
                self.ui.executionStatusLabel.setStyleSheet("background-color: #f8d7da; padding: 8px; border-radius: 4px; border-left: 4px solid #f5c6cb; color: #721c24; font-weight: bold;")
                QtWidgets.QMessageBox.warning(
                    self,
                    "Warning",
                    "Please select a valid directory containing AUSTAL input files."
                )
                return

            if self.ui.erase_log.isChecked():
                opt_ = "D"
                logger.info(
                    "Running AUSTAL with -D option. Log file will be re-written"
                    " at the start of the calculation."
                )
                cmd = [austal_, "-%s" % (opt_), work_dir]
            else:
                cmd = [austal_, work_dir]

            p = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
            output, err = p.communicate()

            if p.returncode != 0:
                raise Austal2000RunError(output)

            # Update status to completed
            self.ui.executionStatusLabel.setText("Status: Completed successfully")
            self.ui.executionStatusLabel.setStyleSheet("background-color: #d4edda; padding: 8px; border-radius: 4px; border-left: 4px solid #28a745; color: #155724; font-weight: bold;")
            
            # Mark results as loaded and update visualisation status with grid details
            self._results_loaded = True
            self._austal_ran = True

            # Snapshot grid based on which input mode was used
            if self.ui.generateFromAlaqsRadio.isChecked():
                # Option B: Use grid from the ALAQS file
                alaqs_file = self.ui.alaqs_output_file_path.filePath()
                try:
                    conn = sqlite3.connect(alaqs_file)
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute(
                        'SELECT x_cells, y_cells, z_cells, x_resolution, y_resolution, '
                        'z_resolution, reference_latitude, reference_longitude '
                        'FROM "grid_3d_definition" LIMIT 1'
                    )
                    grid_row = cursor.fetchone()
                    cursor.execute('SELECT airport_elevation FROM "user_study_setup"')
                    alt_row = cursor.fetchone()
                    conn.close()
                    
                    if grid_row:
                        self._austal_grid_config = {
                            "x_cells": int(grid_row["x_cells"]),
                            "y_cells": int(grid_row["y_cells"]),
                            "z_cells": int(grid_row["z_cells"]),
                            "x_resolution": float(grid_row["x_resolution"]),
                            "y_resolution": float(grid_row["y_resolution"]),
                            "z_resolution": float(grid_row["z_resolution"]),
                            "reference_latitude": float(grid_row["reference_latitude"]),
                            "reference_longitude": float(grid_row["reference_longitude"]),
                            "reference_altitude": float(alt_row["airport_elevation"]) if alt_row else 0.0,
                        }
                except Exception as e:
                    logger.warning(f"Could not load grid from ALAQS file: {e}")
                    self._austal_grid_config = self.get_current_grid_config().copy() if self.get_current_grid_config() else None
            elif self.ui.generateFromCsvRadio.isChecked():
                # Option C: Use G1 grid from spinboxes
                self._austal_grid_config = self.get_current_grid_config().copy() if self.get_current_grid_config() else None
            else:
                # Option A: Use default/existing grid
                self._austal_grid_config = self.get_current_grid_config().copy() if self.get_current_grid_config() else None

            self._update_visualization_status_label()
            
            # Update result buttons - AUSTAL has run, so buttons should be enabled
            self._update_result_buttons_state()

            # Auto-detect and update pollutant/averaging options from work directory outputs
            try:
                self._detect_and_update_pollutants_and_averaging(work_dir)
            except Exception as _e:
                logger.warning("Auto-detection after AUSTAL run failed: %s", _e)
            
            QtWidgets.QMessageBox.information(
                self, "Success", "Dispersion simulation completed successfully"
            )
            logger.info("Dispersion simulation completed successfully")
        except Exception as exception:
            # Update status to error
            self.ui.executionStatusLabel.setText("Status: Failed")
            self.ui.executionStatusLabel.setStyleSheet("background-color: #f8d7da; padding: 8px; border-radius: 4px; border-left: 4px solid #f5c6cb; color: #721c24; font-weight: bold;")
            QtWidgets.QMessageBox.critical(
                self, "Error", "AUSTAL execution failed! See the log for details."
            )

            if isinstance(exception, Austal2000RunError):
                logger.error(
                    f"AUSTAL execution failed with the following output:\n{exception}"
                )
            else:
                logger.error(
                    f"AUSTAL execution failed with the following error: {exception}",
                    exc_info=exception,
                )

    def _detect_and_update_pollutants_and_averaging(self, results_dir: str) -> None:
        """Scan a directory for AUSTAL .dmna files and update pollutant/averaging comboboxes.

        This helper is also called after running AUSTAL so the UI reflects newly
        produced output files even when the user hasn't selected a separate
        results directory.
        """
        try:
            if not results_dir or not os.path.isdir(results_dir):
                return

            dmna_files = [f for f in os.listdir(results_dir) if f.lower().endswith('.dmna')]

            # Scan filenames for known pollutant tokens; skip 'series.dmna' and similar generic files
            # TODO: ALso map p1 and p2
            known_tokens = ['nox', 'co', 'hc', 'pm', 'sox', 'co2']
            found_codes = set()
            for fn in dmna_files:
                base = fn.lower()
                # Exclude generic series files.
                if base.startswith('series') or base == 'series.dmna':
                    continue
                # Match token as whole word to avoid false positives (e.g. 'coX' vs 'co').
                for token in known_tokens:
                    token_re = token.replace('.', r'\\.')
                    if re.search(r'(^|[^a-z0-9])' + token_re + r'([^a-z0-9]|$)', base):
                        found_codes.add(token)
                        break

            # Map internal codes to UI display labels.
            code_to_display = {
                'nox': 'NOx', 'co': 'CO', 'hc': 'HC', 'pm': 'PM10',
                'sox': 'SOx', 'co2': 'CO2'
            }

            # Populate pollutant combo; preserve previous selection if available.
            available_display = [code_to_display.get(c, c.upper()) for c in sorted(found_codes)]

            if hasattr(self.ui, 'resultPollutantCombo'):
                prev = self.ui.resultPollutantCombo.currentText()
                self.ui.resultPollutantCombo.clear()
                for disp in available_display:
                    self.ui.resultPollutantCombo.addItem(disp)
                # Restore previous selection or default to first option.
                if prev and self.ui.resultPollutantCombo.findText(prev) >= 0:
                    self.ui.resultPollutantCombo.setCurrentText(prev)
                elif available_display:
                    self.ui.resultPollutantCombo.setCurrentIndex(0)

            # TODO: Detect averaging periods from filename patterns and add the option to generate the files on an hourly basis
            # averaging_options = ['hourly', '8-hours mean', 'daily mean', 'annual mean']
            self._setup_averaging_options()
        except Exception as _e:
            logger.warning('Could not auto-detect pollutants/averaging from directory: %s', _e)


    def save_grid_as_csv(self) -> None:
        """
        Save the current grid configuration to a CSV file.
        
        The CSV will contain columns for:
        - x_cells, y_cells, z_cells (grid dimensions)
        - x_resolution, y_resolution, z_resolution (cell sizes)
        - reference_latitude, reference_longitude, reference_altitude (reference point)
        """
        try:
            # Open file save dialog
            file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Save Grid Configuration as CSV",
                "",
                "CSV Files (*.csv);;All Files (*)"
            )
            
            if not file_path:
                # User cancelled the dialog
                return
            
            # Ensure .csv extension
            if not file_path.endswith('.csv'):
                file_path += '.csv'
            
            # Get grid values from UI spinboxes
            grid_config = {
                "x_cells": int(self.ui.xCellsSpinBox.value()),
                "y_cells": int(self.ui.yCellsSpinBox.value()),
                "z_cells": int(self.ui.zCellsSpinBox.value()),
                "x_resolution": float(self.ui.xResolutionSpinBox.value()),
                "y_resolution": float(self.ui.yResolutionSpinBox.value()),
                "z_resolution": float(self.ui.zResolutionSpinBox.value()),
                "reference_latitude": float(self.ui.refLatSpinBox.value()),
                "reference_longitude": float(self.ui.refLonSpinBox.value()),
                "reference_altitude": float(self.ui.refAltSpinBox.value()),
            }
            
            # Write to CSV file
            with open(file_path, 'w', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=grid_config.keys())
                writer.writeheader()
                writer.writerow(grid_config)
            
            # Update tracking so the status label turns green
            self._g1_original_grid_config = grid_config.copy()
            self._g1_loaded_file_path = file_path

            # Show success message
            QtWidgets.QMessageBox.information(
                self,
                "Success",
                f"Grid configuration saved successfully to:\n{file_path}"
            )

            # Update status label to reflect saved state
            self._update_grid_status_label()
            
        except Exception as e:
            logger.error(f"Failed to save grid configuration: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Failed to save grid configuration:\n{str(e)}"
            )

    def update_file(self, file_path: str = None) -> None:
        """
        Update the grid file with the current grid configuration.
        
        If no file_path is provided, tries to get it from the gridSourceFilePath widget.
        If that's also empty, opens a file dialog for the user to select a file.
        
        Supports:
        - CSV files: Updates the grid configuration values
        - OpenALAQS files: Updates grid parameters in study_setup and grid_3d_definition tables
        
        Args:
            file_path (str, optional): Path to the grid file to update. If None, uses gridSourceFilePath widget.
        """
        try:
            # If no file_path provided, try to get it from the widget
            if not file_path:
                file_path = self.ui.gridSourceFilePath.filePath()
            
            # If still no file, open a dialog for the user to select one
            if not file_path:
                file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                    self,
                    "Select Grid File to Update (CSV or OpenALAQS)",
                    "",
                    "Grid Files (*.csv *.alaqs);;CSV Files (*.csv);;OpenALAQS Files (*.alaqs);;All Files (*)"
                )
                
                if not file_path:
                    # User cancelled the dialog
                    return
                
                # Update the gridSourceFilePath widget with the selected file
                self.ui.gridSourceFilePath.setFilePath(file_path)
            
            # Verify file exists
            if not os.path.isfile(file_path):
                QtWidgets.QMessageBox.warning(
                    self,
                    "File Not Found",
                    f"The selected file does not exist:\n{file_path}"
                )
                return
            
            # Get grid values from UI spinboxes
            grid_config = {
                "x_cells": int(self.ui.xCellsSpinBox.value()),
                "y_cells": int(self.ui.yCellsSpinBox.value()),
                "z_cells": int(self.ui.zCellsSpinBox.value()),
                "x_resolution": float(self.ui.xResolutionSpinBox.value()),
                "y_resolution": float(self.ui.yResolutionSpinBox.value()),
                "z_resolution": float(self.ui.zResolutionSpinBox.value()),
                "reference_latitude": float(self.ui.refLatSpinBox.value()),
                "reference_longitude": float(self.ui.refLonSpinBox.value()),
                "reference_altitude": float(self.ui.refAltSpinBox.value()),
            }
            
            # Determine file type and update accordingly
            if file_path.endswith('.csv'):
                # Update CSV file
                with open(file_path, 'w', newline='') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=grid_config.keys())
                    writer.writeheader()
                    writer.writerow(grid_config)

                # Update tracking so the status label turns green
                self._g1_original_grid_config = grid_config.copy()
                self._g1_loaded_file_path = file_path
                self._update_grid_status_label()

                QtWidgets.QMessageBox.information(
                    self,
                    "Success",
                    f"Grid configuration updated successfully in:\n{file_path}"
                )
            
            elif file_path.endswith('.alaqs'):
                # Update grid parameters directly in the OpenALAQS database
                try:
                    conn = sqlite3.connect(file_path)
                    cursor = conn.cursor()

                    cursor.execute(
                        "UPDATE user_study_setup SET airport_elevation = ?",
                        (grid_config["reference_altitude"],)
                    )

                    cursor.execute(
                        """UPDATE grid_3d_definition
                           SET x_cells = ?,
                               y_cells = ?,
                               z_cells = ?,
                               x_resolution = ?,
                               y_resolution = ?,
                               z_resolution = ?,
                               reference_latitude = ?,
                               reference_longitude = ?""",
                        (
                            grid_config["x_cells"],
                            grid_config["y_cells"],
                            grid_config["z_cells"],
                            grid_config["x_resolution"],
                            grid_config["y_resolution"],
                            grid_config["z_resolution"],
                            grid_config["reference_latitude"],
                            grid_config["reference_longitude"],
                        )
                    )

                    conn.commit()
                    conn.close()

                    # Update tracking so the status label turns green
                    self._g1_original_grid_config = grid_config.copy()
                    self._g1_loaded_file_path = file_path
                    self._update_grid_status_label()

                    QtWidgets.QMessageBox.information(
                        self,
                        "Success",
                        f"Grid parameters updated successfully in:\n{file_path}"
                    )

                except sqlite3.Error as db_err:
                    QtWidgets.QMessageBox.critical(
                        self,
                        "Database Error",
                        f"Failed to update OpenALAQS database file:\n{str(db_err)}"
                    )
                    return
            
            else:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Invalid File Type",
                    f"File must be either .csv or .alaqs format.\n"
                    f"Selected file: {os.path.basename(file_path)}"
                )
                return
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Failed to update grid configuration file:\n{str(e)}"
            )

    def resetConcentrationCalculationConfiguration(self, config=None):
        if config is None:
            config = {}

        # Note: Configuration stack widget not available in new simplified UI
        # The old stacked widget architecture has been replaced with direct controls
        # This method is kept for compatibility but doesn't do anything
        pass

    def getOutputModulesConfiguration(self):
        # Note: Output modules tab widget not available in new simplified UI
        return {}

    def ShowNotice(self):
        QtWidgets.QMessageBox.information(self, "Notice", "Feature not ready")

    def runOutputModule(self, name):

        try:
            # select output file to load - use the same path as AUSTAL uses
            concentration_path = str(self._get_austal_work_directory())
            if os.path.exists(concentration_path):

                if self._conc_calculation_.get3DGrid() is None:
                    raise Exception("No 3DGrid found.")

                OutputModule = OutputDispersionModuleRegistry().get_module(name)
                if OutputModule is None:
                    logger.error("Did not find module '%s'" % (name))
                    return

                gui_modules_config_ = self.getOutputModulesConfiguration()

                # Read UI values (ensure QDateTime transforms to python datetime)
                if hasattr(self.ui, 'startDtEdit'):
                    qdt = self.ui.startDtEdit.dateTime()
                    start_dt = datetime(
                        qdt.date().year(), qdt.date().month(), qdt.date().day(),
                        qdt.time().hour(), qdt.time().minute(), qdt.time().second()
                    )
                else:
                    start_dt = datetime(2023, 3, 1, 0, 0)

                if hasattr(self.ui, 'endDtEdit'):
                    qdt = self.ui.endDtEdit.dateTime()
                    end_dt = datetime(
                        qdt.date().year(), qdt.date().month(), qdt.date().day(),
                        qdt.time().hour(), qdt.time().minute(), qdt.time().second()
                    )
                else:
                    end_dt = datetime(2023, 3, 1, 23, 0)

                # Extract pollutant from UI and normalize to internal code.
                # Display label -> internal code (e.g. 'PM2.5' -> 'p2').
                pollutant_text = (
                    self.ui.resultPollutantCombo.currentText()
                    if hasattr(self.ui, 'resultPollutantCombo')
                    else None
                )
                # UI display string to internal pollutant code mapping.
                pollutant_map = {
                    "NOx": "nox",
                    "CO": "co",
                    "HC": "hc",
                    "PM10": "pm10",
                    "SOx": "sox",
                    "CO2": "co2",
                }
                pollutant = None
                if pollutant_text:
                    pollutant = pollutant_map.get(pollutant_text, pollutant_text.lower())
                is_uncertainty = self.ui.uncertaintyCheckBox.isChecked() if hasattr(self.ui, 'uncertaintyCheckBox') else False
                averaging = self.ui.averagingCombo.currentText() if hasattr(self.ui, 'averagingCombo') else None

                # Initialize widget with UI values for consistent config parsing.
                self._concentration_visualization_widget.init_values({
                    "start_dt_inclusive": start_dt,
                    "end_dt_inclusive": end_dt,
                    "averaging": averaging,
                    "pollutant": pollutant,
                    "is_uncertainty_enabled": is_uncertainty,
                })

                # Read final configuration from widget after initialization.
                conc_configuration = self._concentration_visualization_widget.get_values()
                pollutant_ = conc_configuration.get("pollutant", pollutant)
                averaging_period_ = conc_configuration.get("averaging", averaging)
                check_std = conc_configuration.get("is_uncertainty_enabled", is_uncertainty)

                # Use the visualization grid from Grid Management if one has
                # been loaded; otherwise fall back to the default grid stored
                # in the concentration calculation object.
                if self._visualization_grid_config:
                    active_grid = Grid3D(
                        db_path=self._conc_calculation_.getDatabasePath(),
                        grid_config=self._visualization_grid_config,
                        deserialize=False,
                    )
                else:
                    active_grid = self._conc_calculation_.get3DGrid()

                # Build output module config from UI values and widget configuration.
                config = {
                    "parent": self,
                    "pollutant": pollutant_,
                    "title": "Mean concentration of '%s'" % pollutant_,
                    "ytitle": "%s" % pollutant_,
                    "grid": active_grid,
                    "database_path": self._conc_calculation_.getDatabasePath(),
                    "concentration_path": concentration_path,
                    "averaging_period": averaging_period_,
                    "timeseries": self.getTimeSeries(self._conc_calculation_.getDatabasePath()),


                    # Disable optional module features by default.
                    "is_plotting_daily_max_enabled": False,
                    "is_csv_output_enabled": False,
                    "is_daily_maximum_enabled": False,
                    "use_centroid_symbol": False,
                    "should_add_labels": False,
                    "should_add_title": False,
                    "3DVisualization": False,
                    "name_suffix": "",
                    "threshold": 0.0001,
                    "check_uncertainty": check_std,
                }

                config.update(conc_configuration)

                # Force Python datetime objects into config
                # ModuleConfigurationWidget returns QDateTime as ISO strings and override to prevent type mismatch in module comparisons
                try:
                    config["start_dt_inclusive"] = start_dt
                    config["end_dt_inclusive"] = end_dt
                except Exception:
                    # fallback: leave whatever was provided
                    pass

                if OutputModule.getModuleDisplayName() in gui_modules_config_:
                    config.update(
                        gui_modules_config_[OutputModule.getModuleDisplayName()]
                    )

                output_module = OutputModule(values_dict=config)

                # Execute the output module
                output_module.beginJob()
                output_module.process()
                res = output_module.endJob()

                if isinstance(res, QtWidgets.QDialog):
                    res.show()
                elif isinstance(res, QgsMapLayer):
                    # Replace existing layers with same name...
                    for layer in self._iface.mapCanvas().layers():
                        if layer.name() == res.name():
                            QgsProject.instance().removeMapLayers([layer.id()])
                    # and add the vector layer to the existing QGIS layers
                    QgsProject.instance().addMapLayers([res])
                    # automatically zoom to new layer
                    self._iface.mapCanvas().setExtent(res.extent())

                    # add coordinate-references system
                    if res.crs() is not None:
                        self._iface.mapCanvas().mapSettings().setDestinationCrs(
                            res.crs()
                        )

                    if name == "ConcentrationsQGISVectorLayerOutputModule":
                        # add text to graphics renderer
                        addTitleToLayer = gui_modules_config_.get("Add title", False)

                        if addTitleToLayer:
                            textItem = QgsTextAnnotation(self._iface.mapCanvas())
                            textItem.setHasFixedMapPosition(False)

                            concentration = output_module.getTotalConcentration()

                            text = QtGui.QTextDocument(
                                "%s Concentration (%.1f kg)\n%s - %s"
                                % (
                                    str(output_module.getPollutant()),
                                    round(concentration, 1),
                                    str(output_module.getTimeStart()),
                                    str(output_module.getTimeEnd()),
                                )
                            )

                            text.setDefaultFont(QtGui.QFont("Arial", 12))
                            textItem.setDocument(text)
                            textItem.setFrameSize(QtCore.QSizeF(500, 48))
                            textItem.setFrameOffsetFromReferencePoint(
                                QtCore.QPointF(20, 75)
                            )
                            # textItem.setFrameBorderWidth(0.0)
                            # textItem.setFrameColor(QColor("white"))

                            self._iface.mapCanvas().scene().addItem(textItem)

            else:
                logger.error("Path not found <%s>" % (concentration_path))

        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Error",
                "Could not execute runOutputModule: %s (error: %s)" % (name, e),
            )
            raise e
        
    def _setup_averaging_options(self):
        """Disable all averaging options except 'annual mean' to indicate future functionality."""
        try:
            # Get the averaging combo from the UI directly
            averaging_combo = self.ui.averagingCombo if hasattr(self.ui, 'averagingCombo') else None
            
            if averaging_combo and isinstance(averaging_combo, QtWidgets.QComboBox):
                model = averaging_combo.model()
                
                for i in range(averaging_combo.count()):
                    item_text = averaging_combo.itemText(i)
                    if item_text != "annual mean":
                        item = model.item(i)
                        if item:
                            # Disable the item
                            item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
                            # Set gray color to make it visually clear it's disabled
                            item.setForeground(QtGui.QColor(150, 150, 150))
                            # Optional: Add a tooltip explaining why it's disabled
                            item.setToolTip("This averaging option is not yet available. Coming soon!")
                
                # Ensure "annual mean" is selected
                annual_mean_index = averaging_combo.findText("annual mean")
                if annual_mean_index >= 0:
                    averaging_combo.setCurrentIndex(annual_mean_index)
                    
                logger.debug("Successfully disabled averaging options except 'annual mean'")
            else:
                logger.warning("Could not find averagingCombo in UI")
                
        except Exception as e:
            logger.warning(f"Could not setup averaging options: {e}", exc_info=True)


class OpenAlaqsEnabledMacros(QtWidgets.QDialog):
    """
    This class provides a dialogue that informs the user that macros have been
    enabled.
    """

    def __init__(self, iface):
        """
        Initialises QDialog that informs the user of the change to the enable
        macros setting
        """
        main_window = iface.mainWindow() if iface is not None else None
        QtWidgets.QDialog.__init__(self, main_window)

        Ui_DialogEnabledMacros, _ = loadUiType(
            os.path.join(os.path.dirname(__file__), "ui", "ui_macros_enabled.ui")
        )
        self.ui = Ui_DialogEnabledMacros()
        self.ui.setupUi(self)
        self.iface = iface
        self.ui.pushButton.clicked.connect(self.close)


class OpenAlaqsOsmImport(QtWidgets.QDialog):
    def __init__(self):
        QtWidgets.QDialog.__init__(self)

        # Build the UI
        Ui_FormProfiles, _ = loadUiType(
            os.path.join(os.path.dirname(__file__), "ui", "ui_import_osm.ui")
        )
        self.ui = Ui_FormProfiles()
        self.ui.setupUi(self)

        processing_registry = QgsApplication.processingRegistry()
        if not processing_registry.algorithmById("quickosm:downloadosmdatarawquery"):
            self.ui.infoLabel.setEnabled(False)
            self.ui.selectLayersGroupBox.setEnabled(False)
            self.ui.importCheckBox.setEnabled(False)
            self.ui.buttonBox.button(
                QtWidgets.QDialogButtonBox.StandardButton.Yes
            ).setEnabled(False)

            self.ui.errorLabel.setVisible(True)

        self.ui.buttonBox.button(
            QtWidgets.QDialogButtonBox.StandardButton.Yes
        ).clicked.connect(self.download)
        self.ui.buttonBox.button(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        ).clicked.connect(self.close)

        self.project = QgsProject.instance()

    def download(self):
        self.setEnabled(False)

        with OverrideCursor(Qt.CursorShape.WaitCursor):
            self._download()

        self.setEnabled(True)

        self.close()

    def _download(self):
        study_setup = alaqs.load_study_setup()

        if not study_setup:
            logger.debug("Cannot download any data if no study setup is loaded.")
            return

        if (
            study_setup["airport_latitude"] is None
            or study_setup["airport_longitude"] is None
        ):
            logger.debug(
                "Cannot download any data if the study setup does not have coordinates set."
            )
            return

        layer_types = self._get_layer_types_to_download()

        if not layer_types:
            logger.debug(
                "No ALAQS layers types have been selected to be download, skipping download."
            )
            return

        points, lines, polygons = download_osm_airport_data(
            layer_types,
            (study_setup["airport_latitude"], study_setup["airport_longitude"]),
            study_setup["airport_code"],
        )
        osm_layers_by_geometry_type = {
            Qgis.GeometryType.Point: points,
            Qgis.GeometryType.Line: lines,
            Qgis.GeometryType.Polygon: polygons,
        }

        tree_root = self.project.layerTreeRoot()
        osm_group = tree_root.findGroup("OpenStreetMap Layers")
        basemaps_group = next(
            filter(
                lambda n: n[1].name() == "Basemaps", enumerate(tree_root.children())
            ),
            None,
        )
        basemaps_group_idx = basemaps_group[0] if basemaps_group else -1

        if osm_group:
            osm_group.removeAllChildren()
        else:
            osm_group = tree_root.insertGroup(
                basemaps_group_idx, "OpenStreetMap Layers"
            )

        points.setName("OSM Points")
        lines.setName("OSM Lines")
        polygons.setName("OSM Polygons")

        self.project.addMapLayer(points, False)
        self.project.addMapLayer(lines, False)
        self.project.addMapLayer(polygons, False)

        osm_group.addLayer(points)
        osm_group.addLayer(lines)
        osm_group.addLayer(polygons)

        if self.ui.importCheckBox.isChecked():
            self._import_osm_data(osm_layers_by_geometry_type)

    def _import_osm_data(
        self, osm_layers_by_geometry_type: dict[Qgis.GeometryType, QgsVectorLayer]
    ) -> None:
        for layer_type, layer_config in LAYERS_CONFIG.items():
            alaqs_layer = oautk.get_alaqs_layer(layer_type)

            if not alaqs_layer:
                logger.error(f"Unable to find the ALAQS layer for {layer_type=}")
                return

            if "osm_filters" not in layer_config:
                logger.debug(
                    f"Skipping layer {layer_type}, it has no OSM tags configuration..."
                )
                continue

            osm_layer = osm_layers_by_geometry_type[alaqs_layer.geometryType()]

            tmp_or_expressions = []
            for osm_filters in layer_config["osm_filters"]:
                tmp_and_expressions = []

                for osm_tag, osm_value in osm_filters["tags"].items():
                    if osm_value is None:
                        tmp_and_expressions.append(
                            f"{QgsExpression.quotedColumnRef(osm_tag)} IS NOT NULL"
                        )
                    else:
                        tmp_and_expressions.append(
                            f"{QgsExpression.quotedColumnRef(osm_tag)} = {QgsExpression.quotedValue(osm_value)}"
                        )

                tmp_or_expressions.append(" AND ".join(tmp_and_expressions))

            expression = QgsExpression(" OR ".join(tmp_or_expressions))
            osm_features = osm_layer.getFeatures(QgsFeatureRequest(expression))
            alaqs_features = []

            for osm_f in osm_features:  # type: ignore
                alaqs_f_attrs = {}
                alaqs_fields = alaqs_layer.fields()

                for osm_attr_name, alaqs_attr_name in layer_config.get(
                    "osm_attribute_mapping", {}
                ).items():
                    value = osm_f.attributeMap().get(osm_attr_name)

                    if value is None:
                        continue

                    alaqs_attr_idx = alaqs_fields.indexFromName(alaqs_attr_name)
                    alaqs_f_attrs[alaqs_attr_idx] = value

                for alaqs_attr_name, alaqs_attr_value in layer_config.get(
                    "osm_import_default_values", {}
                ).items():
                    alaqs_attr_idx = alaqs_fields.indexFromName(alaqs_attr_name)

                    if alaqs_f_attrs.get(alaqs_attr_idx) is None:
                        alaqs_f_attrs[alaqs_attr_idx] = alaqs_attr_value

                alaqs_f = QgsVectorLayerUtils.createFeature(
                    alaqs_layer,
                    osm_f.geometry(),
                    alaqs_f_attrs,
                )

                if not alaqs_f.isValid():
                    logger.warning(
                        f'Invalid new feature in layer "{layer_config["name"]}" from OSM: {osm_f["full_id"]}'
                    )

                alaqs_features.append(alaqs_f)

            if not alaqs_features:
                logger.info(
                    f'No OSM features found to be added to layer "{layer_config["name"]}"'
                )
                continue

            with edit(alaqs_layer):
                if not alaqs_layer.addFeatures(alaqs_features):
                    logger.warning(
                        f'Failed to add new OSM features to layer "{layer_config["name"]}"!'
                    )

    def _get_layer_types_to_download(self) -> list[AlaqsLayerType]:
        """Returns a list of ALAQS layer types to be downloaded based on the UI checkbox selection.

        Returns:
            list[AlaqsLayerType]: list of ALAQS layer types
        """
        layer_types: list[AlaqsLayerType] = []

        if self.ui.selectLayersGroupBox.isChecked():
            if self.ui.buildingsCheckBox.isChecked():
                layer_types.append(AlaqsLayerType.BUILDING)

            if self.ui.gatesCheckBox.isChecked():
                layer_types.append(AlaqsLayerType.GATE)

            if self.ui.parkingsCheckBox.isChecked():
                layer_types.append(AlaqsLayerType.PARKING)

            if self.ui.pointSourcesCheckBox.isChecked():
                layer_types.append(AlaqsLayerType.POINT_SOURCE)

            if self.ui.roadwaysCheckBox.isChecked():
                layer_types.append(AlaqsLayerType.ROADWAY)

            if self.ui.taxiwaysCheckBox.isChecked():
                layer_types.append(AlaqsLayerType.TAXIWAY)

            if self.ui.runwaysCheckBox.isChecked():
                layer_types.append(AlaqsLayerType.RUNWAY)
        else:
            layer_types = list(LAYERS_CONFIG.keys())

        return layer_types
