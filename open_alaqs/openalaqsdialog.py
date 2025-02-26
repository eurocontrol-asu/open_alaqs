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
from typing import Any, cast

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
from qgis.gui import QgsDoubleSpinBox, QgsFileWidget
from qgis.PyQt import QtCore, QtGui, QtWidgets
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.uic import loadUiType
from qgis.utils import OverrideCursor

from open_alaqs import openalaqsuitoolkit as oautk
from open_alaqs.alaqs_config import LAYERS_CONFIG
from open_alaqs.core import alaqs, alaqsutils
from open_alaqs.core.alaqsdblite import ProjectDatabase, delete_records
from open_alaqs.core.alaqslogging import get_logger, log_path
from open_alaqs.core.EmissionCalculation import EmissionCalculation, GridConfig
from open_alaqs.core.interfaces.Emissions import PollutantType
from open_alaqs.core.modules.ModuleConfigurationWidget import ModuleConfigurationWidget
from open_alaqs.core.modules.ModuleManager import (
    DispersionModuleRegistry,
    OutputAnalysisModuleRegistry,
    OutputDispersionModuleRegistry,
    SourceModuleRegistry,
)
from open_alaqs.core.tools import conversion, sql_interface
from open_alaqs.core.tools.csv_interface import (
    read_csv_to_dict,
    read_csv_to_geodataframe,
)
from open_alaqs.core.utils.osm import download_osm_airport_data
from open_alaqs.core.utils.qt import populate_combobox
from open_alaqs.enums import AlaqsLayerType

logger = get_logger(__name__)


INVENTORY_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


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


def get_inventory_timestamps(db_path: str) -> list[datetime]:
    time_series: list[datetime] = []

    if db_path:
        inventory_time_series = cast(
            list[dict[str, Any]],
            sql_interface.db_execute_sql(
                db_path,
                """
                    SELECT * FROM tbl_InvTime
                """,
                fetchone=False,
            ),
        )

        for t in inventory_time_series:
            time_series.append(datetime.strptime(t["time"], INVENTORY_DATE_FORMAT))

        time_series.sort()

    return time_series


def get_min_max_timestamps(db_path: str) -> tuple[datetime, datetime]:
    time_series = get_inventory_timestamps(db_path)

    if len(time_series) < 2:
        time_series.append(
            datetime.strptime("2000-01-01 00:00:00", INVENTORY_DATE_FORMAT)
        )
        time_series.append(
            datetime.strptime("2000-01-02 00:00:00", INVENTORY_DATE_FORMAT)
        )

    return (time_series[0], time_series[-1])


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

                with OverrideCursor(Qt.WaitCursor):
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

        self.ui.buttonBox.button(QtWidgets.QDialogButtonBox.Save).clicked.connect(
            self.save_study_setup
        )
        self.ui.buttonBox.button(QtWidgets.QDialogButtonBox.Close).clicked.connect(
            self.close
        )

    def load_study_data(self):
        """
        This function loads an existing study from a Spatialite database into
        the QGIS environment.
        """
        result = alaqs.load_study_setup()
        if (result is not None) and (result is not []):
            # try and load stuff into the UI
            study_data = alaqs.load_study_setup()

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
        QtWidgets.QWidget.__init__(self, None, Qt.WindowStaysOnTopHint)

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
        self.ui.comboBoxHourlyName.currentIndexChanged["QString"].connect(
            self.change_hourly_profile
        )
        self.ui.pushButtonHourlyDelete.clicked.connect(self.delete_hourly_profile)
        self.ui.pushButtonHourlyNew.clicked.connect(self.new_hourly_profile)
        self.ui.pushButtonHourlySave.clicked.connect(self.save_hourly_profile)
        self.ui.pushButtonHourlyClear.clicked.connect(self.clear_hourly_profile)

        self.ui.comboBoxDailyName.currentIndexChanged["QString"].connect(
            self.change_daily_profile
        )
        self.ui.pushButtonDailyDelete.clicked.connect(self.delete_daily_profile)
        self.ui.pushButtonDailyNew.clicked.connect(self.new_daily_profile)
        self.ui.pushButtonDailySave.clicked.connect(self.save_daily_profile)
        self.ui.pushButtonDailyClear.clicked.connect(self.clear_daily_profile)

        self.ui.comboBoxMonthlyName.currentIndexChanged["QString"].connect(
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
        if (profiles is None) or (profiles is []):
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
        if (profiles is None) or (profiles is []):
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
        if (profiles is None) or (profiles is []):
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
            QtWidgets.QMessageBox.Yes,
            QtWidgets.QMessageBox.No,
        )
        return result != QtWidgets.QMessageBox.Yes

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
    def save_hourly_profile(self):
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
            QtWidgets.QMessageBox.Yes,
            QtWidgets.QMessageBox.No,
        )
        if answer == QtWidgets.QMessageBox.Yes:
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

    def save_daily_profile(self):
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
            QtWidgets.QMessageBox.Yes,
            QtWidgets.QMessageBox.No,
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

    def save_monthly_profile(self):
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
    def clear_hourly_profile(self):
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
    def clear_daily_profile(self):
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
    def clear_monthly_profile(self):
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
        self.canvas = self.iface.mapCanvas()

        self.populate_arr_dep()
        self.populate_runways()
        self.populate_gates()
        self.populate_routes()
        self.populate_aircraft_groups()
        self.populate_instance()
        self.visualize_route_name()

        self.ui.gate.currentIndexChanged["QString"].connect(self.visualize_route_name)
        self.ui.runway.currentIndexChanged["QString"].connect(self.visualize_route_name)
        self.ui.instance.currentIndexChanged["QString"].connect(
            self.visualize_route_name
        )
        self.ui.arrdep.currentIndexChanged["QString"].connect(self.visualize_route_name)

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
        if (gates is None) or (gates is []):
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
        if (runways is None) or (runways is []):
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
            # QGIS2
            # layer.setSelectedFeatures(to_select)
            # QGIS3
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
        self.ui.buttonBox.button(QtWidgets.QDialogButtonBox.Save).setText(
            "Create Inventory"
        )
        self.ui.buttonBox.button(QtWidgets.QDialogButtonBox.Save).clicked.connect(
            self.create_inventory
        )
        self.ui.buttonBox.button(QtWidgets.QDialogButtonBox.Close).clicked.connect(
            self.close
        )

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
                with OverrideCursor(Qt.WaitCursor):
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
                with OverrideCursor(Qt.WaitCursor):
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

            with OverrideCursor(Qt.WaitCursor):
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
            return ui_element.checkState() == Qt.Checked
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

        # initialize calculation
        self._emission_calculation_ = None
        self._emission_calculation_configuration_widget = None

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

        self.ui.pollutants_names.currentIndexChanged["QString"].connect(
            self.pollutant_changed
        )
        self.ui.source_names.currentIndexChanged["QString"].connect(
            self.source_name_changed
        )
        self.ui.source_types.currentIndexChanged["QString"].connect(
            self.source_type_changed
        )

        self.ui.ResultsTableButton.clicked.connect(
            lambda: self.runOutputModule("TableViewWidgetOutputModule")
        )
        self.ui.plot_time_series_vs_emissions.clicked.connect(
            lambda: self.runOutputModule("TimeSeriesWidgetOutputModule")
        )
        self.ui.add_contour.clicked.connect(
            lambda: self.runOutputModule("EmissionsQGISVectorLayerOutputModule")
        )

        s = QgsSettings()
        last_result_file_path = s.value("OpenALAQS/last_result_file_path", "")

        self.ui.result_file_path.setFilter("ALAQS (*.alaqs)")
        self.ui.result_file_path.setDialogTitle("Open Emission Inventory Data")
        self.ui.result_file_path.setFilePath(last_result_file_path)
        self.ui.result_file_path.fileChanged.connect(self.result_file_path_changed)

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
            scroll_widget.setFrameShape(QtWidgets.QFrame.NoFrame)
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
            scroll_widget.setFrameShape(QtWidgets.QFrame.NoFrame)
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

    def runOutputModule(self, name: str) -> None:
        OutputModule = OutputAnalysisModuleRegistry().get_module(name)

        if OutputModule is None:
            logger.error("Did not find module '%s'", name)
            return None

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
                # self._iface.mapCanvas().mapRenderer().setDestinationCrs(res.crs())
                self._iface.mapCanvas().mapSettings().setDestinationCrs(res.crs())

            if name == "EmissionsQGISVectorLayerOutputModule":
                # add text to graphics renderer
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
        if not os.path.isfile(path):
            raise Exception("File '%s' does not exist." % path)

        # Fill in the UI
        self.ui.source_names.clear()
        self.ui.source_types.clear()

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

    def isOutputFile(self, path):
        return sql_interface.hasTable(path, "grid_3d_definition")

    def update_emissions(self):

        inventory_path = self.ui.result_file_path.filePath()

        if not Path(inventory_path).exists() or not Path(inventory_path).is_file():
            logger.error(
                "Inventory path `%s` is not a file!",
                inventory_path,
            )
            return

        # Temporarily set the project database to extract the airport data
        project_database = ProjectDatabase()
        project_database_path = getattr(project_database, "path", None)
        project_database.path = inventory_path
        study_data = alaqs.load_study_setup()
        ref_latitude = study_data.get("airport_latitude", 0.0)
        ref_longitude = study_data.get("airport_longitude", 0.0)
        ref_altitude = study_data.get("airport_elevation", 0.0)
        if project_database_path is None:
            del project_database.path
        else:
            project_database.path = project_database_path

        grid_configuration = {
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

        em_config = self._emission_calculation_configuration_widget.get_values()

        self._emission_calculation_ = EmissionCalculation(
            db_path=inventory_path,
            grid_config=grid_configuration,
            start_dt=datetime.fromisoformat(em_config["start_dt_inclusive"]),
            end_dt=datetime.fromisoformat(em_config["end_dt_inclusive"]),
            time_interval=timedelta(seconds=int(em_config["time_interval"])),
        )

        em_config = self._emission_calculation_configuration_widget.get_values()
        em_config["reference_altitude"] = ref_altitude
        em_config["receptors"] = self._receptor_points

        if em_config["method"] == "BFFM2" and em_config["should_apply_nox_corrections"]:
            logger.warning(
                "Not possible to use both 'BFFM2' " "and 'Apply NOx correction'"
            )

        selected_module_name = self.ui.source_types.currentText()
        if selected_module_name.lower() == "all":
            module_names = SourceModuleRegistry().get_module_names()
        else:
            module_names = [selected_module_name]

        for module_name in module_names:
            self._emission_calculation_.add_source_module(module_name, em_config)

        # dispersion modules
        dm_module_configs = self.getDispersionModulesConfiguration()
        pollutant = self.ui.pollutants_names.currentText()

        # dm_name_ should be AUSTALOutputModule
        for dm_module_name, dm_module_config in dm_module_configs.items():
            if not dm_module_configs[dm_module_name].get("is_enabled", False):
                continue

            dm_module_config.update(
                {
                    "pollutants_list": self._pollutants_list,
                    "pollutant": pollutant,
                    "receptors": self._receptor_points,
                    "grid": self._emission_calculation_.get3DGrid(),
                }
            )

            self._emission_calculation_.add_dispersion_modules(
                [dm_module_name], dm_module_config
            )

        # Sources
        source_name = self.ui.source_names.currentText()
        source_names = [source_name if source_name is not None else "all"]
        self._emission_calculation_.run(
            source_names=source_names,
            vertical_limit_m=em_config["vertical_limit_m"],
        )
        self._emission_calculation_.sortEmissionsByTime()

    def get_values(self):
        """
        This function is used to pass data back to the main alaqs.py class when
         the UI exits.
        """
        return self._return_values


class OpenAlaqsDispersionAnalysis(QtWidgets.QDialog):
    """
    This class provides a dialog that launches the Dispersion Analysis
    """

    settings_schema = {
        "start_dt_inclusive": {
            "label": "Start (incl.)",
            "widget_type": QtWidgets.QDateTimeEdit,
            "initial_value": "2000-01-01 00:00:00",
        },
        "end_dt_inclusive": {
            "label": "End (incl.)",
            "widget_type": QtWidgets.QDateTimeEdit,
            "initial_value": "2000-01-02 00:00:00",
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
        self.ui.configuration_splitter.setSizes([80, 200])

        # initialize calculation
        self._conc_calculation_ = None
        self._concentration_visualization_widget = None
        self.resetConcentrationCalculationConfiguration()
        self.updateMinMaxGUI()

        self.ui.configuration_modules_list.setCurrentRow(0)
        self.ui.configuration_stack.setCurrentIndex(0)
        self.ui.configuration_modules_list.currentRowChanged.connect(
            self.configuration_modules_list_current_row_changed
        )
        self.ui.configuration_stack.currentChanged.connect(
            self.configuration_stack_current_changed
        )

        s = QgsSettings()
        last_alaqs_file_path = s.value("OpenALAQS/last_alaqs_file_path", "")
        last_work_directory_path = s.value("OpenALAQS/last_work_directory_path", "")
        self.ui.a2k_executable_path.setFilePath(
            s.value("open_alaqs/a2k_executable_path", "")
        )
        self.ui.a2k_executable_path.setFilter("AUSTAL Executable (austal.exe austal)")
        self.ui.a2k_executable_path.setDialogTitle("Select AUSTAL Executable File")
        self.ui.a2k_executable_path.fileChanged.connect(
            self.a2k_executable_path_file_changed
        )
        self.ui.work_directory_path.setStorageMode(QgsFileWidget.GetDirectory)
        self.ui.work_directory_path.setDialogTitle(
            "Select AUSTAL Input Files (.txt, .dmna, etc.) Directory"
        )
        self.ui.work_directory_path.setFilePath(last_work_directory_path)
        self.ui.work_directory_path.fileChanged.connect(
            self._on_work_directory_path_changed
        )
        self.ui.alaqs_file_path.setFilter("ALAQS (*.alaqs)")
        self.ui.alaqs_file_path.setDialogTitle("Select ALAQS Output File")
        self.ui.alaqs_file_path.setFilePath(last_alaqs_file_path)
        self.ui.alaqs_file_path.fileChanged.connect(self.load_alaqs_source_file)

        if os.path.isfile(last_alaqs_file_path):
            self.load_alaqs_source_file(last_alaqs_file_path)

        self.ui.RunA2K.clicked.connect(self.run_austal)

        self.ui.ResultsTable.clicked.connect(
            lambda: self.runOutputModule("TableViewDispersionModule")
        )
        self.ui.VisualiseResults.clicked.connect(
            lambda: self.runOutputModule("QGISVectorLayerDispersionModule")
        )
        self.ui.PlotTimeSeries.clicked.connect(
            lambda: self.runOutputModule("TimeSeriesDispersionModule")
        )

        self.resetModuleConfiguration(
            module_names=[
                "CSVDispersionModule",
                "TableViewDispersionModule",
                "TimeSeriesDispersionModule",
                "QGISVectorLayerDispersionModule",
            ]
        )

    def configuration_modules_list_current_row_changed(self, row):
        self.ui.configuration_stack.setCurrentIndex(row)

    def configuration_stack_current_changed(self, index):
        self.ui.configuration_modules_list.setCurrentRow(index)

    def updateMinMaxGUI(self, db_path_=""):
        (time_start_calc_, time_end_calc_) = get_min_max_timestamps(db_path_)
        self.resetConcentrationCalculationConfiguration(
            config={
                "start_dt_inclusive": time_start_calc_,
                "end_dt_inclusive": time_end_calc_,
            }
        )

    def getTimeSeries(self, db_path="") -> list[datetime]:
        from datetime import timedelta

        from dateutil import rrule

        if not db_path:
            return []

        try:
            time_series_ = get_inventory_timestamps(db_path)
        except Exception as e:
            logger.warning("Database error: '%s'" % (e))

            # TODO OPENGIS.ch: not very sure if this `except` block makes much sense,
            # since if `get_inventory_timestamp` fails, there is no point for `get_min_max_timestamps` to pass.
            # I would consider to remove this and simplify the function.
            (time_start_calc_, time_end_calc_) = get_min_max_timestamps(db_path)
            time_series_ = []
            for _day_ in rrule.rrule(
                rrule.DAILY, dtstart=time_start_calc_, until=time_end_calc_
            ):
                for hour_ in rrule.rrule(
                    rrule.HOURLY,
                    dtstart=_day_,
                    until=_day_ + timedelta(days=+1, hours=-1),
                ):
                    time_series_.append(hour_.strftime(INVENTORY_DATE_FORMAT))
            time_series_.sort()

        return time_series_

    def resetModuleConfiguration(self, module_names):
        self.ui.output_modules_tab_widget.clear()

        for module_name in OutputDispersionModuleRegistry().get_module_names():
            module = OutputDispersionModuleRegistry().get_module(module_name)
            config_widget = module.getConfigurationWidget2()

            if config_widget is None:
                continue

            scroll_widget = QtWidgets.QScrollArea(self)
            scroll_widget.setFrameShape(QtWidgets.QFrame.NoFrame)
            scroll_widget.setWidget(config_widget)
            scroll_widget.setWidgetResizable(True)
            self.ui.output_modules_tab_widget.addTab(
                scroll_widget, module.getModuleDisplayName()
            )

    def a2k_executable_path_file_changed(self, path):
        """
        Save the selected austal executable file path to restore on dialog
        opening
        """
        if os.path.exists(path):
            settings = QgsSettings()
            settings.setValue("open_alaqs/a2k_executable_path", path)

    def set_feedback(self, feedback: str, is_success: bool) -> None:
        self.ui.alaqs_file_path_feedback.setText(feedback)

        self.ui.VisualiseResults.setEnabled(is_success)
        self.ui.ResultsTable.setEnabled(is_success)
        self.ui.PlotTimeSeries.setEnabled(is_success)

    def load_alaqs_source_file(self, filename):
        """
        Open a file browse window for the user to be able to locate and load an
         ALAQS output file
        """
        path = Path(filename)
        if not filename or not path.is_file() or path.suffix != ".alaqs":
            self.set_feedback("Please select an existing *_out.alaqs file", False)
            return

        try:
            self.updateMinMaxGUI(filename)

            project_database = ProjectDatabase()
            project_database.path = filename

            study_data = alaqs.load_study_setup()

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
        except sqlite3.OperationalError as err:
            self.set_feedback(f"Could not open database file: {err}.", False)

    def _on_work_directory_path_changed(self, dirname: str) -> None:
        s = QgsSettings()

        if os.path.isdir(dirname):
            s.setValue("OpenALAQS/last_work_directory_path", dirname)

    @catch_errors
    def run_austal(self, *args, **kwargs):
        from subprocess import PIPE, Popen

        try:
            austal_ = str(self.ui.a2k_executable_path.filePath())
            logger.info("AUSTAL directory:%s" % austal_)
            work_dir = str(self.ui.work_directory_path.filePath())
            logger.info("AUSTAL input files directory:%s" % work_dir)

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

            QtWidgets.QMessageBox.information(
                self, "Success", "Dispersion simulation completed successfully"
            )
            logger.info("Dispersion simulation completed successfully")
        except Exception as exception:
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

    def resetConcentrationCalculationConfiguration(self, config=None):
        if config is None:
            config = {}

        if self._concentration_visualization_widget is None:
            self._concentration_visualization_widget = ModuleConfigurationWidget(
                self.settings_schema
            )
            self.ui.configuration_stack.insertWidget(
                0, self._concentration_visualization_widget
            )

        self._concentration_visualization_widget.init_values(config)
        self.update()

    def getOutputModulesConfiguration(self):
        tab = self.ui.output_modules_tab_widget
        return {
            tab.tabText(index): tab.widget(index).widget().get_values()
            for index in range(0, tab.count())
        }

    def ShowNotice(self):
        QtWidgets.QMessageBox.information(self, "Notice", "Feature not ready")

    def runOutputModule(self, name):

        try:
            # select output file to load
            concentration_path = str(self.ui.work_directory_path.filePath())
            if os.path.exists(concentration_path):

                if self._conc_calculation_.get3DGrid() is None:
                    raise Exception("No 3DGrid found.")

                OutputModule = OutputDispersionModuleRegistry().get_module(name)
                if OutputModule is None:
                    logger.error("Did not find module '%s'" % (name))
                    return

                gui_modules_config_ = self.getOutputModulesConfiguration()

                # Configuration of the conc. calculation
                # (from ConcentrationsQGISVectorLayerOutputModule)
                conc_configuration = (
                    self._concentration_visualization_widget.get_values()
                )
                pollutant_ = conc_configuration.get("pollutant", None)
                averaging_period_ = conc_configuration.get("averaging", None)
                check_std = conc_configuration.get("is_uncertainty_enabled", False)

                config = {
                    "parent": self,
                    "pollutant": pollutant_,
                    "title": "Mean concentration of '%s'" % pollutant_,
                    "ytitle": "%s" % pollutant_,
                    "grid": self._conc_calculation_.get3DGrid(),
                    "database_path": self._conc_calculation_.getDatabasePath(),
                    "concentration_path": concentration_path,
                    "averaging_period": averaging_period_,
                    "timeseries": self.getTimeSeries(
                        self._conc_calculation_.getDatabasePath()
                    ),
                    # "use_centroid_symbol": False,
                    "check_uncertainty": check_std,
                }

                config.update(conc_configuration)

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
            self.ui.buttonBox.button(QtWidgets.QDialogButtonBox.Yes).setEnabled(False)

            self.ui.errorLabel.setVisible(True)

        self.ui.buttonBox.button(QtWidgets.QDialogButtonBox.Yes).clicked.connect(
            self.download
        )
        self.ui.buttonBox.button(QtWidgets.QDialogButtonBox.Cancel).clicked.connect(
            self.close
        )

        self.project = QgsProject.instance()

    def download(self):
        self.setEnabled(False)

        with OverrideCursor(Qt.WaitCursor):
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
