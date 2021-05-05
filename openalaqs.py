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
from __future__ import absolute_import
from builtins import str
from builtins import object
# Import OS for finding files
import os, sys
# sys.path.append("..") # Adds higher directory to python modules path.

# Import the PyQt and QGIS libraries
from qgis.core import *
from qgis.gui import *
from qgis.PyQt import QtCore, QtGui, QtWidgets

from . openalaqsdialog import *
from . import openalaqsuitoolkit

logger = alaqslogging.logging.getLogger(__name__)
logger.setLevel('DEBUG')
file_handler = alaqslogging.logging.FileHandler(alaqslogging.LOG_FILE_PATH)
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
formatter = alaqslogging.logging.Formatter(log_format)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Import the code for the dialog
# from .openalaqsdialog import *
# A single dot means that the module or package referenced is in the same directory as the current location.
# from . import openalaqsuitoolkit
#
# # Import ALAQS
# alaqs_core_dir = os.path.dirname(os.path.abspath(__file__)) + "\\alaqs_core"
# if alaqs_core_dir not in sys.path:
#     sys.path.append(alaqs_core_dir)
#
# toos_dir = os.path.dirname(os.path.abspath(__file__)) + "\\alaqs_core\\tools"
# if toos_dir not in sys.path:
#     sys.path.append(toos_dir)
#
# interfaces_dir = os.path.dirname(os.path.abspath(__file__)) + "\\alaqs_core\\interfaces"
# if interfaces_dir not in sys.path:
#     sys.path.append(interfaces_dir)
#
# modules_dir = os.path.dirname(os.path.abspath(__file__)) + "\\alaqs_core\\modules"
# if modules_dir not in sys.path:
#     sys.path.append(modules_dir)
#
# ui_dir = os.path.dirname(os.path.abspath(__file__)) + "\\ui"
# if ui_dir not in sys.path:
#     sys.path.append(ui_dir)

class Open_Alaqs(object):
    """
    This is the main entry point for QGIS into Open ALAQS and initializes the tool bar and directs all interactions
    from there on in to the appropriate functions.
    """

    def __init__(self, iface):
        """
        Generic QGIS initialisation functions that initialise OpenALAQS as a plugin.
        """

        # Save reference to the QGIS interface
        self.iface = iface
        self.canvas = self.iface.mapCanvas()

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # initialize locale
        locale_path = ""
        locale = str(QtCore.QSettings().value("locale/userLocale"))[0:2]

        if QtCore.QFileInfo(self.plugin_dir).exists():
            locale_path = self.plugin_dir + "/i18n/openalaqs_" + locale + ".qm"

        if QtCore.QFileInfo(locale_path).exists():
            self.translator = QtCore.QTranslator()
            self.translator.load(locale_path)

            if QtCore.qVersion() > '4.3.3':
                QtCore.QCoreApplication.installTranslator(self.translator)

        # QGIS3: setMapUnits() was removed. The map units are dictated by the units for the destination CRS.
        # We set the maps units to meters (0:meters, 1:feet, 2:degrees)
        # This is needed, especially if we're using network maps
        # self.iface.mapCanvas().setMapUnits(0)

        # Create some of the variables that we will use throughout the class
        self.action_about = None
        self.action_project_create = None
        self.action_project_load = None
        self.action_project_save = None
        self.action_project_close = None
        self.action_study_setup = None
        self.action_build_inventory = None
        self.action_calculate_dispersion = None
        self.action_profiles_edit = None
        self.action_upload_movements = None
        self.action_view_results_analysis = None
        self.action_taxi_routes = None
        self.action_logfile = None
        self.open_alaqs_toolbar = None
        self.dlg_about = None
        self.dlg_create_project = None
        self.dlg_open_project = None
        self.dlg_study_setup = None
        self.dlg_profiles = None
        self.dlg_movements = None
        self.dlg_taxi_routes = None
        self.dlg_inventory = None
        self.dlg_results = None
        self.dlg_logfile = None

    def initGui(self):
        """
        Plugin initialisation function. Builds toolbar and binds to calls for various UI classes.
        """

        # Create action that will show the About dialog
        self.action_about = QtWidgets.QAction(
            QtGui.QIcon(os.path.dirname(__file__) + "/alaqs_core/icons/about.png"),
            u"About Open ALAQS", self.iface.mainWindow())
        # connect the action to the run method
        self.action_about.triggered.connect(self.run_about)

        # Create action that will show the Create dialog
        self.action_project_create = QtWidgets.QAction(
            QtGui.QIcon(os.path.dirname(__file__) + "/alaqs_core/icons/project-create.png"),
            u"Create an Open ALAQS project", self.iface.mainWindow())
        # connect the action to the run method
        self.action_project_create.triggered.connect(self.run_project_create)

        # Create action that will show the Load dialog
        self.action_project_load = QtWidgets.QAction(
            QtGui.QIcon(os.path.dirname(__file__) + "/alaqs_core/icons/project-load.png"),
            u"Load an Open ALAQS project", self.iface.mainWindow())
        # connect the action to the run method
        self.action_project_load.triggered.connect(self.run_project_load)

        # Create action that will show the Close dialog
        self.action_project_close = QtWidgets.QAction(
            QtGui.QIcon(os.path.dirname(__file__) + "/alaqs_core/icons/project-close.png"),
            u"Close all Open ALAQS projects", self.iface.mainWindow())
        # connect the action to the run method
        self.action_project_close.triggered.connect(self.run_project_close)

        # Create action that will show the Study Setup dialog
        self.action_study_setup = QtWidgets.QAction(
            QtGui.QIcon(os.path.dirname(__file__) + "/alaqs_core/icons/study-setup.png"),
            u"Airport Study Setup", self.iface.mainWindow())
        # connect the action to the run method
        self.action_study_setup.triggered.connect(self.run_study_setup)

        # Create action that will show the Profile Edit dialog
        self.action_profiles_edit = QtWidgets.QAction(
            QtGui.QIcon(os.path.dirname(__file__) + "/alaqs_core/icons/profiles.png"),
            u"Edit profiles", self.iface.mainWindow())
        # connect the action to the run method
        self.action_profiles_edit.triggered.connect(self.run_profiles_edit)

        # Create action that will show the Profile Edit dialog
        self.action_taxi_routes = QtWidgets.QAction(
            QtGui.QIcon(os.path.dirname(__file__) + "/alaqs_core/icons/taxi-routes.png"),
            u"Define taxi routes", self.iface.mainWindow())
        # connect the action to the run method
        self.action_taxi_routes.triggered.connect(self.run_taxi_routes)

        # Create action that will show the calculate emissions inventory dialog
        self.action_build_inventory = QtWidgets.QAction(
            QtGui.QIcon(os.path.dirname(__file__) + "/alaqs_core/icons/calculate.png"),
            u"Calculate Emissions Inventory", self.iface.mainWindow())
        # connect the action to the run method
        self.action_build_inventory.triggered.connect(self.run_build_inventory)

        self.action_view_results_analysis = QtWidgets.QAction(
            QtGui.QIcon(os.path.dirname(__file__) + "/alaqs_core/icons/grids.png"),
            u"Visualize Emission Calculation", self.iface.mainWindow())
        # connect the action to the run method
        self.action_view_results_analysis.triggered.connect(self.run_results_analysis)

        # Create action that will show the calculate emissions dispersion dialog
        self.action_calculate_dispersion = QtWidgets.QAction(
            QtGui.QIcon(os.path.dirname(__file__) + "/alaqs_core/icons/dispersion_model.png"),
            u"Calculate Dispersion", self.iface.mainWindow())
        # ToDo:
        # connect the action to the run method
        self.action_calculate_dispersion.triggered.connect(self.run_dispersion_analysis)

        # Create action that will show the Settings dialog
        self.action_logfile = QtWidgets.QAction(
            QtGui.QIcon(os.path.dirname(__file__) + "/alaqs_core/icons/text-log.png"),
            u"Review Open ALAQS logs", self.iface.mainWindow())
        # connect the action to the run method
        self.action_logfile.triggered.connect(self.run_view_logfile)

        # Add buttons to toolbar
        self.open_alaqs_toolbar = self.iface.addToolBar("OpenALAQS ToolBar")
        self.open_alaqs_toolbar.addAction(self.action_about)
        self.open_alaqs_toolbar.addSeparator()
        self.open_alaqs_toolbar.addAction(self.action_project_create)
        self.open_alaqs_toolbar.addAction(self.action_project_load)
        self.open_alaqs_toolbar.addAction(self.action_project_close)

        # Create new airport
        self.open_alaqs_toolbar.addSeparator()
        self.open_alaqs_toolbar.addAction(self.action_study_setup)
        self.open_alaqs_toolbar.addAction(self.action_profiles_edit)
        self.open_alaqs_toolbar.addAction(self.action_taxi_routes)
        self.open_alaqs_toolbar.addAction(self.action_build_inventory)

        self.open_alaqs_toolbar.addSeparator()
        self.open_alaqs_toolbar.addAction(self.action_view_results_analysis)
        self.open_alaqs_toolbar.addAction(self.action_calculate_dispersion)

        self.open_alaqs_toolbar.addSeparator()
        self.open_alaqs_toolbar.addAction(self.action_logfile)

        # Set some initially unavailable
        self.action_project_close.setEnabled(False)
        self.action_study_setup.setEnabled(False)
        self.action_profiles_edit.setEnabled(False)
        self.action_taxi_routes.setEnabled(False)
        self.action_build_inventory.setEnabled(False)
        # self.action_calculate_dispersion.setEnabled(False)

    def unload(self):
        """
        Unloads the Open ALAQS plugin from the QGIS canvas, removing the toolbar
        and any menu items from the UI.
        """
        #Close the current project
        self.run_project_close()

        # Delete the Open ALAQS toolbar
        del self.open_alaqs_toolbar

    def run_about(self):
        """
        Calls a class that displays the About OpenALAQS UI
        """
        self.dlg_about = OpenAlaqsAbout(self.iface)
        self.dlg_about.show()
        result = self.dlg_about.exec_()
        if result == 1:
            pass

    def run_project_create(self):
        """
        Opens a dialog to allow the user to create a new study database. This is
        a blank database and blank shape files with no shapes currently included.
        When completed, it opens the study setup window.
        """
        self.dlg_create_project = OpenAlaqsCreateDatabase(self.iface)
        result_code = self.dlg_create_project.exec_()
        if result_code == 0:
            database_path = self.dlg_create_project.get_values()
            if database_path is not None:
                openalaqsuitoolkit.load_layers(self.iface, database_path)
                openalaqsuitoolkit.set_default_zoom(self.canvas, 51.4775, -0.4614)
                self.dlg_create_project.close()
                self.action_study_setup.setEnabled(True)
                self.action_profiles_edit.setEnabled(True)
                self.action_taxi_routes.setEnabled(True)
                self.action_build_inventory.setEnabled(True)
                self.action_view_results_analysis.setEnabled(True)
                self.action_calculate_dispersion.setEnabled(True)
                self.action_project_load.setEnabled(False)
                self.action_project_create.setEnabled(False)
                self.action_project_close.setEnabled(True)
                self.run_study_setup()
        else:
            self.dlg_create_project.close()

    def run_project_load(self):
        """
        Opens a dialog to allow the user to open an existing study database. This
        tries to query some information from the database if possible to populate
        the study setup window, which it opens if successful.
        """
        self.dlg_open_project = OpenAlaqsOpenDatabase(self.iface)
        return_code = self.dlg_open_project.exec_()
        if return_code == 0:
            database_path = self.dlg_open_project.get_values()
            if (database_path is not None) and (database_path != ""):
                openalaqsuitoolkit.load_layers(self.iface, database_path)
                self.dlg_open_project.close()
                self.action_study_setup.setEnabled(True)
                self.action_profiles_edit.setEnabled(True)
                self.action_taxi_routes.setEnabled(True)
                self.action_build_inventory.setEnabled(True)
                self.action_view_results_analysis.setEnabled(True)
                self.action_calculate_dispersion.setEnabled(True)
                self.action_project_load.setEnabled(False)
                self.action_project_create.setEnabled(False)
                self.action_project_close.setEnabled(True)
                self.run_study_setup()
        else:
            self.dlg_open_project.close()

    def run_project_close(self):
        """
        This function ensures a smooth closing of an OpenALAQS project, removing
        associated layers from the UI, cleaning up the tool bar and disabling some
        features until a new project is created or loaded.
        """
        self.action_profiles_edit.setEnabled(False)
        openalaqsuitoolkit.delete_alaqs_layers(self.iface)

        self.action_project_close.setEnabled(False)
        self.action_study_setup.setEnabled(False)
        self.action_profiles_edit.setEnabled(False)
        self.action_taxi_routes.setEnabled(False)
        self.action_build_inventory.setEnabled(False)
        #self.action_view_results_analysis.setEnabled(False)
        self.action_calculate_dispersion.setEnabled(False)

        self.action_project_create.setEnabled(True)
        self.action_project_load.setEnabled(True)

    def run_study_setup(self):
        """
        Looks to see if there is an open database (the first combo box will be populated
        if it is) and presents details of the current study for review/update. If a database
        is not available, a warning message is shown.
        """
        try:
            self.dlg_study_setup = OpenAlaqsStudySetup(self.iface)
            self.dlg_study_setup.show()
            return_code = self.dlg_study_setup.exec_()
            if return_code == 0:
                try:
                    self.dlg_study_setup.get_values()
                    self.dlg_study_setup.close()
                    self.action_profiles_edit.setEnabled(True)
                except:
                    pass
            else:
                self.dlg_study_setup.close()
        except:
            QtWidgets.QMessageBox.warning(None, "Error", "No database loaded.\nEither create a new database or open an "
                                                     "existing study")

    def run_profiles_edit(self):
        """
        Opens the widget dialog for administering aircraft profiles.
        """
        self.dlg_profiles = OpenAlaqsProfiles(self.iface)
        self.dlg_profiles.show()
        result = self.dlg_profiles.exec_()
        if result == 1:
            pass

    def run_taxi_routes(self):
        """
        Opens the widget dialog for administering aircraft taxi routes.
        """
        self.dlg_taxi_routes = OpenAlaqsTaxiRoutes(self.iface)
        self.dlg_taxi_routes.show()
        result = self.dlg_taxi_routes.exec_()
        if result == 1:
            pass

    def run_build_inventory(self):
        """
        Opens the widget dialog for administering the generation of an OpenALAQS emission inventory based on the
        current sources.
        """
        self.dlg_inventory = OpenAlaqsInventory()
        self.dlg_inventory.show()
        result = self.dlg_inventory.exec_()
        if result == 1:
            pass

    def run_results_analysis(self):
        """
        Opens the widget dialog for analysing and visualising the results of an OpenALAQS emission inventory.
        """
        self.dlg_results = OpenAlaqsResultsAnalysis(self.iface)
        result = self.dlg_results.exec_()

        if not result:
            # return_values = self.dlg_results.get_values()
            # logger.info("Result '%s'."%(str(return_values)),"ContourPlot", 0)
            pass

    def run_dispersion_analysis(self):
        """
        Opens the widget dialog for calculating dispersion of the results of an OpenALAQS emission inventory.
        """
        self.dlg_results = OpenAlaqsDispersionAnalysis(self.iface)
        result = self.dlg_results.exec_()

        if not result:
            pass

    def run_view_logfile(self):
        """
        Opens the widget dialog for review of the Open ALAQSlog file.
        """
        self.dlg_logfile = OpenAlaqsLogfile()
        result = self.dlg_logfile.exec_()
        if result == 1:
            pass
