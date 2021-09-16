# -*- coding: utf-8 -*-
"""
/***************************************************************************
                        OpenALAQS -  A QGIS plugin
 An open source version of the ALAQS project - Airport Local Air Quality
 Studies. Ported from ArcGIS and significantly modified to make use of new
 best practices and data sources.
        begin                : 2013-02-05
        copyright            : (C) EUROCONTROL
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
from pathlib import Path

from qgis.PyQt import QtCore, QtGui, QtWidgets
from qgis.core import *
from qgis.gui import *

from open_alaqs import openalaqsuitoolkit
from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.openalaqsdialog import OpenAlaqsAbout, \
    OpenAlaqsCreateDatabase, OpenAlaqsOpenDatabase, OpenAlaqsStudySetup, \
    OpenAlaqsProfiles, OpenAlaqsTaxiRoutes, OpenAlaqsInventory, \
    OpenAlaqsResultsAnalysis, OpenAlaqsDispersionAnalysis, OpenAlaqsLogfile, \
    OpenAlaqsEnabledMacros

# Configure the logger
logger = get_logger(__name__)


class OpenALAQS:
    """
    This is the main entry point for QGIS into Open ALAQS and initializes the
    tool bar and directs all interactions from there on in to the appropriate
    functions.
    """

    def __init__(self, iface):
        """
        Generic QGIS initialisation functions that initialise OpenALAQS as a
        plugin.
        """

        # Save reference to the QGIS interface
        self.iface = iface
        self.canvas = self.iface.mapCanvas()

        # QGIS3: setMapUnits() was removed.
        # The map units are dictated by the units for the destination CRS.
        # We set the maps units to meters (0:meters, 1:feet, 2:degrees)
        # This is needed, especially if we're using network maps
        # self.iface.mapCanvas().setMapUnits(0)

        # Create some of the variables that we will use throughout the class
        self.open_alaqs_toolbar = None
        self.actions = {}
        self.dialogs = {}

    @staticmethod
    def create_connected_action(icon, description, location, run_action):
        """
        Helper function to create connected actions.
        """

        # Create the action
        action = QtWidgets.QAction(icon, description, location)

        # Connect the action to the run method
        action.triggered.connect(run_action)

        return action

    def initGui(self):
        """
        Plugin initialisation function. Builds toolbar and binds to calls for
        various UI classes.

        """

        # Set the path to the icons
        icons_path = Path(__file__).parent / 'icons'

        # Create action that will show the About dialog
        self.actions['about'] = self.create_connected_action(
            QtGui.QIcon(str(icons_path / "about.png")),
            u"About Open ALAQS",
            self.iface.mainWindow(),
            self.run_about)

        # Create action that will show the Create Project dialog
        self.actions['project_create'] = self.create_connected_action(
            QtGui.QIcon(str(icons_path / "project-create.png")),
            u"Create an Open ALAQS project",
            self.iface.mainWindow(),
            self.run_project_create)

        # Create action that will show the Load Project dialog
        self.actions['project_load'] = self.create_connected_action(
            QtGui.QIcon(str(icons_path / "project-load.png")),
            u"Load an Open ALAQS project",
            self.iface.mainWindow(),
            self.run_project_load)

        # Create action that will show the Close Project dialog
        self.actions['project_close'] = self.create_connected_action(
            QtGui.QIcon(str(icons_path / "project-close.png")),
            u"Close all Open ALAQS projects",
            self.iface.mainWindow(),
            self.run_project_close)

        # Create action that will show the Study Setup dialog
        self.actions['study_setup'] = self.create_connected_action(
            QtGui.QIcon(str(icons_path / "study-setup.png")),
            u"Airport Study Setup",
            self.iface.mainWindow(),
            self.run_study_setup)

        # Create action that will show the Profile Edit dialog
        self.actions['profiles_edit'] = self.create_connected_action(
            QtGui.QIcon(str(icons_path / "profiles.png")),
            u"Edit profiles",
            self.iface.mainWindow(),
            self.run_profiles_edit)

        # Create action that will show the Define Taxi Routes dialog
        self.actions['taxi_routes'] = self.create_connected_action(
            QtGui.QIcon(str(icons_path / "taxi-routes.png")),
            u"Define taxi routes",
            self.iface.mainWindow(),
            self.run_taxi_routes)

        # Create action that will show the Calculate Emissions Inventory dialog
        self.actions['build_inventory'] = self.create_connected_action(
            QtGui.QIcon(str(icons_path / "calculate.png")),
            u"Calculate Emissions Inventory",
            self.iface.mainWindow(),
            self.run_build_inventory)

        # Create action that will show the Visualize Emission Calculation dialog
        self.actions['view_results_analysis'] = self.create_connected_action(
            QtGui.QIcon(str(icons_path / "grids.png")),
            u"Visualize Emission Calculation",
            self.iface.mainWindow(),
            self.run_results_analysis)

        # Create action that will show the calculate emissions dispersion dialog
        self.actions['calculate_dispersion'] = self.create_connected_action(
            QtGui.QIcon(str(icons_path / "dispersion_model.png")),
            u"Calculate Dispersion",
            self.iface.mainWindow(),
            self.run_dispersion_analysis)

        # Create action that will show the Settings dialog
        self.actions['logfile'] = self.create_connected_action(
            QtGui.QIcon(str(icons_path / "text-log.png")),
            u"Review Open ALAQS logs",
            self.iface.mainWindow(),
            self.run_view_logfile)

        # Add buttons to toolbar
        self.open_alaqs_toolbar = self.iface.addToolBar("OpenALAQS ToolBar")
        self.open_alaqs_toolbar.addAction(self.actions['about'])
        self.open_alaqs_toolbar.addSeparator()
        self.open_alaqs_toolbar.addAction(self.actions['project_create'])
        self.open_alaqs_toolbar.addAction(self.actions['project_load'])
        self.open_alaqs_toolbar.addAction(self.actions['project_close'])

        # Create new airport
        self.open_alaqs_toolbar.addSeparator()
        self.open_alaqs_toolbar.addAction(self.actions['study_setup'])
        self.open_alaqs_toolbar.addAction(self.actions['profiles_edit'])
        self.open_alaqs_toolbar.addAction(self.actions['taxi_routes'])
        self.open_alaqs_toolbar.addAction(self.actions['build_inventory'])

        self.open_alaqs_toolbar.addSeparator()
        self.open_alaqs_toolbar.addAction(self.actions['view_results_analysis'])
        self.open_alaqs_toolbar.addAction(self.actions['calculate_dispersion'])

        self.open_alaqs_toolbar.addSeparator()
        self.open_alaqs_toolbar.addAction(self.actions['logfile'])

        # Set some initially unavailable
        self.actions['project_close'].setEnabled(False)
        self.actions['study_setup'].setEnabled(False)
        self.actions['profiles_edit'].setEnabled(False)
        self.actions['taxi_routes'].setEnabled(False)
        self.actions['build_inventory'].setEnabled(False)

    def unload(self):
        """
        Unloads the Open ALAQS plugin from the QGIS canvas, removing the toolbar
        and any menu items from the UI.
        """
        # Close the current project
        self.run_project_close()

        # Delete the Open ALAQS toolbar
        del self.open_alaqs_toolbar

    def run_about(self):
        """
        Calls a class that displays the About OpenALAQS UI
        """
        self.dialogs['about'] = OpenAlaqsAbout(self.iface)
        self.dialogs['about'].show()

    def run_project_create(self):
        """
        Opens a dialog to allow the user to create a new study database. This is
        a blank database and blank shape files with no shapes currently
        included. When completed, it opens the study setup window.
        """
        self.dialogs['create_project'] = OpenAlaqsCreateDatabase(self.iface)
        result_code = self.dialogs['create_project'].exec_()
        if result_code == 0:
            database_path = self.dialogs['create_project'].get_values()
            if database_path is not None:
                openalaqsuitoolkit.load_layers(self.iface, database_path)
                openalaqsuitoolkit.set_default_zoom(self.canvas, 51.4775,
                                                    -0.4614)
                self.dialogs['create_project'].close()
                self.actions['study_setup'].setEnabled(True)
                self.actions['profiles_edit'].setEnabled(True)
                self.actions['taxi_routes'].setEnabled(True)
                self.actions['build_inventory'].setEnabled(True)
                self.actions['view_results_analysis'].setEnabled(True)
                self.actions['calculate_dispersion'].setEnabled(True)
                self.actions['project_load'].setEnabled(False)
                self.actions['project_create'].setEnabled(False)
                self.actions['project_close'].setEnabled(True)
                self.run_study_setup()
        else:
            self.dialogs['create_project'].close()

        QgsSettings().setValue("/qgis/enableMacros", 'Always')
        self.run_macro_setting_warning()

    def run_project_load(self):
        """
        Opens a dialog to allow the user to open an existing study database.
        This tries to query some information from the database if possible to
        populate the study setup window, which it opens if successful.
        """
        self.dialogs['open_project'] = OpenAlaqsOpenDatabase(self.iface)
        return_code = self.dialogs['open_project'].exec_()
        if return_code == 0:

            # Get the database path
            database_path = self.dialogs['open_project'].get_values()

            # Continue if the path is valid
            if isinstance(database_path, str) and Path(database_path).exists():
                openalaqsuitoolkit.load_layers(self.iface, database_path)
                self.dialogs['open_project'].close()
                self.actions['study_setup'].setEnabled(True)
                self.actions['profiles_edit'].setEnabled(True)
                self.actions['taxi_routes'].setEnabled(True)
                self.actions['build_inventory'].setEnabled(True)
                self.actions['view_results_analysis'].setEnabled(True)
                self.actions['calculate_dispersion'].setEnabled(True)
                self.actions['project_load'].setEnabled(False)
                self.actions['project_create'].setEnabled(False)
                self.actions['project_close'].setEnabled(True)
                self.run_study_setup()
        else:
            self.dialogs['open_project'].close()

        QgsSettings().setValue("/qgis/enableMacros", 'Always')
        self.run_macro_setting_warning()

    def run_project_close(self):
        """
        This function ensures a smooth closing of an OpenALAQS project, removing
        associated layers from the UI, cleaning up the tool bar and disabling
        some features until a new project is created or loaded.
        """
        self.actions['profiles_edit'].setEnabled(False)
        openalaqsuitoolkit.delete_alaqs_layers(self.iface)

        self.actions['project_close'].setEnabled(False)
        self.actions['study_setup'].setEnabled(False)
        self.actions['profiles_edit'].setEnabled(False)
        self.actions['taxi_routes'].setEnabled(False)
        self.actions['build_inventory'].setEnabled(False)
        self.actions['calculate_dispersion'].setEnabled(False)

        self.actions['project_create'].setEnabled(True)
        self.actions['project_load'].setEnabled(True)

    def run_study_setup(self):
        """
        Looks to see if there is an open database (the first combo box will be
        populated if it is) and presents details of the current study for
        review/update. If a database is not available, a warning message is
        shown.
        """
        try:
            self.dialogs['study_setup'] = OpenAlaqsStudySetup(self.iface)
            self.dialogs['study_setup'].show()
            return_code = self.dialogs['study_setup'].exec_()
            if return_code == 0:
                try:
                    self.dialogs['study_setup'].get_values()
                    self.dialogs['study_setup'].close()
                    self.actions['profiles_edit'].setEnabled(True)
                except Exception:
                    pass
            else:
                self.dialogs['study_setup'].close()
        except Exception:
            QtWidgets.QMessageBox.warning(
                None,
                "Error",
                "No database loaded.\n"
                "Either create a new database or open an existing study")

    def run_profiles_edit(self):
        """
        Opens the widget dialog for administering aircraft profiles.
        """
        self.dialogs['profiles'] = OpenAlaqsProfiles(self.iface)
        self.dialogs['profiles'].show()
        self.dialogs['profiles'].exec_()

    def run_taxi_routes(self):
        """
        Opens the widget dialog for administering aircraft taxi routes.
        """
        self.dialogs['taxi_routes'] = OpenAlaqsTaxiRoutes(self.iface)
        self.dialogs['taxi_routes'].show()
        self.dialogs['taxi_routes'].exec_()

    def run_build_inventory(self):
        """
        Opens the widget dialog for administering the generation of an OpenALAQS
        emission inventory based on the current sources.
        """
        self.dialogs['inventory'] = OpenAlaqsInventory()
        self.dialogs['inventory'].show()
        self.dialogs['inventory'].exec_()

    def run_results_analysis(self):
        """
        Opens the widget dialog for analysing and visualising the results of an
        OpenALAQS emission inventory.
        """
        self.dialogs['results'] = OpenAlaqsResultsAnalysis(self.iface)
        self.dialogs['results'].exec_()

    def run_dispersion_analysis(self):
        """
        Opens the widget dialog for calculating dispersion of the results of an
        OpenALAQS emission inventory.
        """
        self.dialogs['results'] = OpenAlaqsDispersionAnalysis(self.iface)
        self.dialogs['results'].exec_()

    def run_view_logfile(self):
        """
        Opens the widget dialog for review of the Open ALAQSlog file.
        """
        self.dialogs['logfile'] = OpenAlaqsLogfile()
        self.dialogs['logfile'].exec_()

    def run_macro_setting_warning(self):
        """
        Opens the widget dialog informing the user of the change to the macro
        setting.
        """
        self.dialogs['enabled_macros'] = OpenAlaqsEnabledMacros(self.iface)
        self.dialogs['enabled_macros'].show()
