import itertools
import os
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple, Union

import geopandas as gpd
import numpy as np
import pandas as pd
from dateutil import rrule
from qgis.gui import QgsDoubleSpinBox, QgsSpinBox
from qgis.PyQt import QtWidgets
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.AmbientCondition import AmbientCondition
from open_alaqs.core.interfaces.DispersionModule import DispersionModule
from open_alaqs.core.interfaces.Emissions import Emission
from open_alaqs.core.interfaces.InventoryTimeSeries import InventoryTime
from open_alaqs.core.interfaces.Movement import Movement
from open_alaqs.core.interfaces.Source import Source
from open_alaqs.core.tools import conversion, spatial, sql_interface
from open_alaqs.core.tools.Grid3D import Grid3D

logger = get_logger(__name__)


def log_time(func):
    def inner(*args, **kwargs):
        start = datetime.now()
        result = func(*args, **kwargs)
        finish = datetime.now()
        logger.debug(f"Time elapsed {func.__name__}: {finish - start}")
        return result

    return inner


class AUSTAL2000DispersionModule(DispersionModule):
    """
    Module for the preparation of the input files needed for AUSTAL2000
    dispersion calculations.
    """

    @staticmethod
    def getModuleName():
        return "AUSTAL2000"

    @staticmethod
    def getModuleDisplayName():
        return "AUSTAL2000"

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        DispersionModule.__init__(self, values_dict)

        self._name = values_dict.get("name", "")
        self._model = "AUSTAL2000"
        self._pollutant = values_dict.get("pollutant", "NOx")
        self._receptors = values_dict.get("receptors", gpd.GeoDataFrame())
        self._output_path = values_dict.get("output_path")

        # Create the output directory if it does not exist
        if self._output_path is not None:
            # self._def_output_path = copy.deepcopy(self._output_path)
            if not os.path.isdir(self._output_path):
                os.mkdir(self._output_path)

        self._sequ = "k+,j-,i+"
        self._grid = values_dict.get("grid", "")

        self._pollutants_list = values_dict.get("pollutants_list")
        if self._pollutant:
            self._pollutants_list = [self._pollutant]

        self._enable = values_dict.get("Enabled", False)
        # "----------------- general parameters",
        # "ti\t'grid source'\t' title of the project",
        self._title = values_dict.get("Title", values_dict.get("add title"))
        if not self._title:
            self._title = "no title"
        # "qs\t1\t' quality level",
        self._quality_level = values_dict.get(
            "Quality Level", values_dict.get("quality level")
        )
        if not self._quality_level:
            self._quality_level = 1
        # for non-standard calculations
        self._options = values_dict.get(
            "Option String", values_dict.get("options string")
        )
        if not self._options:
            self._options = "SCINOTAT"

        # "----------------- meteorology",
        # ToDo: Modify AmbientCondition.py or derive z0, d0, and ha from main
        #  dialog (airport info)
        # "z\t0.2\t' roughness length (m)",
        self._roughness_level = values_dict.get(
            "Roughness Length", values_dict.get("roughness length (in m)")
        )
        self._roughness_level = (
            0.2 if not self._roughness_level else float(self._roughness_level)
        )
        # d0: default 6z0    # "d0\t1.2\t' displacement height (m)",
        self._displacement_height = values_dict.get(
            "Displacement Height",
            values_dict.get(
                "displacement height (in m)",
            ),
        )
        self._displacement_height = (
            6 * self._roughness_level
            if not self._displacement_height
            else float(self._displacement_height)
        )
        # 10 m + d0 (6z0)  # "ha\t11.2\t' anemometer height (m)",
        self._anemometer_height = values_dict.get(
            "Anemometer Height", values_dict.get("anemometer height (in m)")
        )
        self._anemometer_height = (
            10 + 6 * self._roughness_level
            if not self._anemometer_height
            else float(self._anemometer_height)
        )

        self._reference_x = None
        self._reference_y = None
        self._reference_z = None
        # receptor points
        self.xp_, self.yp_, self.zp_ = [], [], []

        # "----------------- concentration grid -----------------"
        self._x_left_border_calc_grid = None  # "x0\t-200\t' left border (m)",
        self._y_left_border_calc_grid = None  # "y0\t-200\t' lower border (m)",

        # general parameters set from Widget
        widget_parameters = OrderedDict(
            [
                ("Enabled", QtWidgets.QCheckBox),
                ("Title", QtWidgets.QLineEdit),
                ("Roughness Length", QgsDoubleSpinBox),
                ("Anemometer Height", QgsDoubleSpinBox),
                ("Displacement Height", QgsDoubleSpinBox),
                ("Options String", QtWidgets.QLineEdit),
                ("Quality Level", QgsSpinBox),
            ]
        )
        self.setConfigurationWidget(widget_parameters)

        # ToDo: QL Range between -4 and 4
        widget = self._configuration_widget.getSettings()["Roughness Length"]
        widget.setMinimum(0.0)
        widget.setMaximum(999999.9)
        widget.setSuffix(" m")
        widget = self._configuration_widget.getSettings()["Anemometer Height"]
        widget.setMinimum(0.0)
        widget.setMaximum(999999.9)
        widget.setSuffix(" m")
        widget = self._configuration_widget.getSettings()["Displacement Height"]
        widget.setMinimum(0.0)
        widget.setMaximum(999999.9)
        widget.setSuffix(" m")
        widget = self._configuration_widget.getSettings()["Quality Level"]
        widget.setMinimum(1)
        widget.setMaximum(10)
        widget.setToolTip("+1 doubles the number of simulation particles")

        self._configuration_widget.getSettings()["Options String"].setToolTip(
            "options must be defined successively and separated by a semicolon"
        )
        self._configuration_widget.getSettings()["Enabled"].setToolTip(
            "Enable to create AUSTAL2000 input files"
        )

        self.getConfigurationWidget().initValues(
            {
                "Roughness Length": 0.2,
                "Displacement Height": 1.2,
                "Anemometer Height": 11.2,
                "Title": "",
                "Quality Level": 1,
                "Enabled": False,
                "Options String": "NOSTANDARD;SCINOTAT;Kmax=1",
            }
        )

    # ToDo: Define the get set functions for all parameters
    def getTitle(self):
        return self._title

    def setTitle(self, var):
        self._title = var

    # Quality Level
    def getQualityLevel(self):
        return self._quality_level

    def setQualityLevel(self, var):
        self._quality_level = var

    # Roughness Length
    def getRoughnessLength(self):
        return self._roughness_level

    def setRoughnessLength(self, var):
        self._roughness_level = var

    def getGrid(self) -> Grid3D:
        return self._grid

    def setGrid(self, var):
        self._grid = var

    def isEnabled(self):
        return self._enable

    def getModel(self):
        return self._model

    def setModel(self, val):
        self._model = val

    def getSequ(self) -> str:
        """
        Index sequence in which the data values are listed (comma separated)
        (from AUSTAL2000 grid source example)

        :return:
        """
        return self._sequ

    def setOutputPath(self, val):
        self._output_path = val

    def getOutputPath(self):
        return self._output_path

    def getOutputPathAsPath(self):
        return Path(self._output_path)

    def getSortedResults(self):
        return OrderedDict(sorted(list(self._results.items()), key=lambda t: t[0]))

    def getSortedSeries(self):
        return OrderedDict(sorted(list(self._series.items()), key=lambda t: t[0]))

    def getDataPoint(
        self, x_: float, y_: float, z_: float, is_polygon: bool, grid_: Grid3D
    ) -> dict:
        data_point_ = {"coordinates": {"x": x_, "y": y_, "z": z_}}
        if is_polygon:
            data_point_.update(
                {
                    "coordinates": {
                        "x_min": x_ - grid_.getResolutionX() / 2.0,
                        "x_max": x_ + grid_.getResolutionX() / 2.0,
                        "y_min": y_ - grid_.getResolutionY() / 2.0,
                        "y_max": y_ + grid_.getResolutionY() / 2.0,
                        "z_min": z_ - grid_.getResolutionZ() / 2.0,
                        "z_max": z_ + grid_.getResolutionZ() / 2.0,
                    }
                }
            )
        return data_point_

    def getBoundingBox(self, geometry_wkt: str) -> Union[dict, None]:
        return spatial.getBoundingBox(geometry_wkt)

    def getCellBox(self, x_: float, y_: float, z_: float, grid_: Grid3D) -> dict:
        return {
            "x_min": x_ - grid_.getResolutionX() / 2.0,
            "x_max": x_ + grid_.getResolutionX() / 2.0,
            "y_min": y_ - grid_.getResolutionY() / 2.0,
            "y_max": y_ + grid_.getResolutionY() / 2.0,
            "z_min": z_ - grid_.getResolutionZ() / 2.0,
            "z_max": z_ + grid_.getResolutionZ() / 2.0,
        }

    def getEfficiencyXY(
        self,
        emissions_wkt: str,
        cell_bbox: dict,
        _is_point: bool,
        _is_line: bool,
        _is_polygon: bool,
        _is_multi_polygon: bool,
    ) -> float:
        """
        Get the efficiency of XY, with the efficiency being the relative area of
         geometry in the cell box

        """
        if _is_point or _is_polygon or _is_multi_polygon:
            return spatial.getRelativeAreaInBoundingBox(emissions_wkt, cell_bbox)
        elif _is_line:
            # get relative length (X,Y) in bounding box (assumes constant speed)
            return spatial.getRelativeLengthXYInBoundingBox(emissions_wkt, cell_bbox)
        return 0

    def getEfficiencyZ(
        self,
        z_min: float,
        z_max: float,
        cell_box: dict,
        _is_point: bool,
        _is_line: bool,
        _is_polygon: bool,
        _is_multi_polygon: bool,
    ) -> float:
        """
        Get the efficiency of Z, with the efficiency being the relative height
         of the geometry in the cell box

        """
        if _is_point:
            # points match each cell exactly once
            return spatial.getRelativeHeightInBoundingBox(z_min, z_max, cell_box)
        elif _is_polygon or _is_line or _is_multi_polygon:
            return spatial.getRelativeHeightInBoundingBox(z_min, z_max, cell_box)
        return 0

    @log_time
    def getGridXYFromReferencePoint(self):
        """
        This method gets the origin of the grid to the bottom-left corner.
        "Reference" coordinates need to be related to the center of the grid.
        """
        try:
            reference_point_wkt = "POINT (%s %s)" % (
                self._grid._reference_longitude,
                self._grid._reference_latitude,
            )
            logger.info("AUSTAL2000: Grid reference point: %s" % reference_point_wkt)

            # Convert the ARP into EPSG 3857
            sql_text = (
                "SELECT X(ST_Transform(ST_PointFromText('%s', 4326), 3857)), Y(ST_Transform(ST_PointFromText('%s', 4326), 3857));"
                % (reference_point_wkt, reference_point_wkt)
            )
            result = sql_interface.query_text(self._grid._db_path, sql_text)
            if result is None:
                raise Exception(
                    "AUSTAL2000: Could not reset reference point as coordinates could not be transformed. The query was\n'%s'"
                    % (sql_text)
                )

            self._reference_x = conversion.convertToFloat(result[0][0])
            self._reference_y = conversion.convertToFloat(result[0][1])
            self._reference_z = self._grid._reference_altitude
            # logger.info("self._reference_x: %s, self._reference_y: %s, self._reference_z: %s"%(self._reference_x, self._reference_y, self._reference_z))

            # Calculate the coordinates of the bottom left of the grid
            grid_origin_x = float(self._reference_x) - (
                float(self._grid._x_cells) / 2.0
            ) * float(self._grid._x_resolution)
            grid_origin_y = float(self._reference_y) - (
                float(self._grid._y_cells) / 2.0
            ) * float(self._grid._y_resolution)
            # logger.info("getGridXYFromReferencePoint: bottom left of the EMIS grid: x0=%.0f, y0=%.0f" % (grid_origin_x, grid_origin_y))

            # conc grid
            user_set_factor = (
                2.0  # ToDo: Enlarge Calculation Grid by Factor set by the user?
            )
            self._x_left_border_calc_grid = float(
                grid_origin_x
            ) - user_set_factor * float(self._grid._x_resolution)
            self._y_left_border_calc_grid = float(
                grid_origin_y
            ) - user_set_factor * float(self._grid._y_resolution)
            # logger.info("getGridXYFromReferencePoint: bottom left of the CONC grid: xq=%.0f, yq=%.0f" % (self._x_left_border_calc_grid, self._y_left_border_calc_grid))

            # emissions grid == coordinates of the bottom left of the grid
            self._x_left_border_em_grid = float(grid_origin_x)
            self._y_left_border_em_grid = float(grid_origin_y)
            # logger.info("emissions grid corner: (%s, %s)"%(self._x_left_border_em_grid, self._y_left_border_em_grid))

            try:
                if not self._receptors.empty:
                    for idp in self._receptors.index:
                        self._receptors.crs = {
                            "init": "epsg:%s" % self._receptors.loc[idp, "crs"]
                        }
                        rec_point = self._receptors.to_crs({"init": "epsg:3857"}).loc[
                            idp, "geometry"
                        ]
                        self.xp_.append(round(rec_point.x - self._reference_x, 2))
                        self.yp_.append(round(rec_point.y - self._reference_y, 2))
                        self.zp_.append(rec_point.z)
            except Exception as exc_:
                logger.warning(
                    "Couldn't add receptor points to dispersion study (%s)" % exc_
                )
            return True

        except Exception as e:
            logger.error(
                "AUSTAL2000: Could not reset 3D grid origin from reference point: %s"
                % e
            )
            return False

    def InitializeEmissionGridMatrix(self):
        if (self._grid is None) or (self._sequ is None):
            raise Exception(
                "Cannot initialize the emissions grid. No 3DGrid or" " Sequence found."
            )

        # Split the sequ once
        sequ_split = self.getSequ().split(",")

        # Check for each index which mesh to link
        indices = [None, None, None]
        for p, q in enumerate(sequ_split):
            if q.startswith("k"):
                indices[p] = self._z_meshes
            elif q.startswith("j"):
                indices[p] = self._y_meshes
            else:
                indices[p] = self._x_meshes
        index_i, index_j, index_k = indices

        # Set the emission grid matrix to zero
        self._emission_grid_matrix = np.zeros(shape=(index_i, index_j, index_k))

        return index_i, index_j, index_k

    @log_time
    def emptyOutputPath(self):
        import errno
        import shutil
        import stat

        def handleRemoveReadonly(func, path, exc):
            # If os.rmdir or os.remove fails due to permissions, change
            # permissions
            if func in (os.rmdir, os.remove) and exc[1].errno == errno.EACCES:

                # Change permissions of the file to 0777
                os.chmod(path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

                # Execute the original function
                func(path)
            else:
                raise Exception("handleRemoveReadonly error")

        # Get the output path
        output_path = self.getOutputPathAsPath()

        # Get files in the output path
        output_path_children = list(output_path.iterdir())

        if len(output_path_children) > 0:

            # Ask for permission to delete the files
            answer = QtWidgets.QMessageBox.question(
                None,
                "Warning",
                "AUSTAL destionation folder is not empty!\nDelete existing files?",
                QtWidgets.QMessageBox.Yes,
                QtWidgets.QMessageBox.No,
            )

            if answer == QtWidgets.QMessageBox.Yes:
                for child in output_path_children:
                    try:
                        if child.is_dir():
                            shutil.rmtree(
                                child, ignore_errors=False, onerror=handleRemoveReadonly
                            )
                        elif child.is_file():
                            child.unlink()
                    except Exception:
                        logger.error("Could not delete %s", child)
            else:
                logger.warning(
                    "Previous AUSTAL files were not deleted, verify output in %s",
                    output_path,
                )

    @log_time
    def checkTimeIntervalinResults(self):
        if not (
            list(self.getSortedResults().keys()) == list(self.getSortedSeries().keys())
        ):
            logger.debug(
                "AUSTAL2000 Error: Contradictory data for series.dmna and austal.txt files"
            )
            return False
        else:
            return True

    @log_time
    def checkHoursinResults(self):
        # Set the date format
        date_fmt = "%Y-%m-%d.%H:%M:%S"

        # Get the sorted results and sorted series
        sorted_results = self.getSortedResults()
        sorted_series = self.getSortedSeries()

        # Get the keys of the sorted results
        sorted_results_keys = list(sorted_results.keys())

        # Get the first and last key of the sorted results and series
        if len(sorted_results_keys) == 1:
            first_key = sorted_results_keys[0]
            last_key = sorted_results_keys[0]
        else:
            first_key, last_key = sorted_results_keys[:: len(sorted_results_keys) - 1]
        first_key_series = next(iter(sorted_series))

        # Get the associated dates
        start_date = datetime.strptime(first_key, date_fmt)
        end_date = datetime.strptime(last_key, date_fmt)
        start_date_series = datetime.strptime(first_key_series, date_fmt)

        # Check if the study starts at time 01
        if start_date.hour != 1 or start_date_series.hour != 1:
            logger.warning(
                "AUSTAL2000 Warning: The time series must start at "
                "time 01 (found %s)" % first_key
            )

        # Make sure that the study spans at least one full day
        if (end_date - start_date).total_seconds() < 86400:
            logger.warning(
                "A2K warning: The time series must cover at least "
                "one day. End date will be changed from %s to %s",
                end_date,
                start_date + timedelta(hours=24),
            )
            end_date = start_date + timedelta(hours=23)

        # Create a new list to store the hours that were added by this method
        missed_hours = []

        # Go over all hours in the relevant timerange
        for _day_ in rrule.rrule(rrule.DAILY, dtstart=start_date, until=end_date):

            # Determine the end of the day
            _day_end = _day_ + timedelta(days=+1, hours=-1)

            for hour_ in rrule.rrule(rrule.HOURLY, dtstart=_day_, until=_day_end):

                # Get the timestamp as string
                hour_str = hour_.strftime(date_fmt)

                # If the hour is relevant and not present in the results yet,
                # add default results
                if hour_str not in sorted_results and hour_ <= end_date:

                    # Log the hour that is added by this method
                    missed_hours.append(hour_str)

                    # Set empty OrderedDicts as default values
                    self._results.setdefault(hour_str, OrderedDict())
                    self._series.setdefault(hour_str, OrderedDict())

                    # Update the values
                    self._series[hour_str].update(
                        {
                            "WindDirection": 999,
                            "WindSpeed": 0.7,
                            # ambient_conditions.getObukhovLength()
                            "ObukhovLength": 99999.0,
                        }
                    )
                    self._results[hour_str].update(
                        {
                            "01": {
                                "timeID": 1,
                                "source": "",
                                "pollutant": "",
                                "emission_rate": 0.0,
                            }
                        }
                    )

        return missed_hours

    @log_time
    def set_normalized_date(self, start_time: InventoryTime, end_time: InventoryTime):
        """
        AUSTAL requires the calculation to start from yyyy-01-01.01.00.00.
         Therefore the dates should be normalized.

        :param start_time:
        :param end_time:
        """

        # Convert to a datetime
        t_start = start_time.getTimeAsDateTime()

        # Check if the date has already been set
        if self._first_start_time is None:

            # Determine the timedelta
            t_delta = t_start - t_start.replace(
                month=1, day=1, hour=0, minute=0, second=0
            )

            logger.info(
                f"Normalize start date to ensure that AUSTAL starts "
                f"from yyyy-01-01.01.00.00 with the following time "
                f"delta: {t_delta}"
            )

            # Set the timestamps for the current period
            self._start_time = t_start - t_delta
            self._end_time = end_time.getTimeAsDateTime() - t_delta

            # Set the first start time
            self._first_start_time = self._start_time

        else:
            # Increment the timestamps to get the current period
            self._start_time += timedelta(hours=+1)
            self._end_time += timedelta(hours=+1)

        # Add the timestamps to the dates
        if t_start not in self._dates:
            self._dates[t_start] = [self._start_time, self._end_time]

        return self._start_time, self._end_time

    def CalculateCellHashEfficiency(
        self,
        source_wkt: str,
        bbox: dict,
        cells_matched: list,
        _is_point_element: bool,
        _is_line_element: bool,
        _is_polygon_element: bool,
        _is_multipolygon_element: bool,
    ):
        """
        Get the efficiency for each cell hash

        """

        # Get the grid
        grid = self.getGrid()

        # Get z_min and z_max
        z_min = bbox["z_min"]
        z_max = bbox["z_max"]

        # Create an empty dict for the cell efficiency
        cell_efficiency = OrderedDict()

        # Process all matched cells
        for xy_rect in cells_matched:
            if not xy_rect:
                logger.info(
                    "No matched_cells (%s) for Bbox: %s (Geo: %s) ? ",
                    xy_rect,
                    bbox,
                    source_wkt,
                )
                continue

            # Set the x,y-efficiency to zero
            efficiency_xy_ = 0.0
            for index_height_level, cell_hash in enumerate(xy_rect):

                # Get the x, y, z coordinates
                x_, y_, z_ = grid.convertCellHashListToCenterGridCellCoordinates(
                    [cell_hash]
                )[cell_hash]

                # Get the cell box
                cell_bbox = self.getCellBox(x_, y_, z_, grid)

                # calculate the efficiency once for each x,y pair and reuse it
                #  for all z levels
                if index_height_level == 0:
                    efficiency_xy_ = self.getEfficiencyXY(
                        source_wkt,
                        cell_bbox,
                        _is_point=_is_point_element,
                        _is_line=_is_line_element,
                        _is_polygon=_is_polygon_element,
                        _is_multi_polygon=_is_multipolygon_element,
                    )

                # get relative height (Z) in bbox
                efficiency_z_ = self.getEfficiencyZ(
                    z_min,
                    z_max,
                    cell_bbox,
                    _is_point=_is_point_element,
                    _is_line=_is_line_element,
                    _is_polygon=_is_polygon_element,
                    _is_multi_polygon=_is_multipolygon_element,
                )

                # combine the (x,y) and (z) efficiency
                cell_efficiency[cell_hash] = efficiency_xy_ * efficiency_z_

        return cell_efficiency

    def getGridFilePath(self, source: Union[int, str], index: int) -> Path:
        # Get the output path (as Path)
        output_path = self.getOutputPathAsPath()

        # Get the source name
        if isinstance(source, int):
            source = str(source).zfill(2)

        # Get the file stem
        file_stem = "e" + str(index).zfill(4)

        # Get the file path
        return (output_path / source / file_stem).with_suffix(".dmna")

    @log_time
    def writeGridFile(
        self,
        source: Union[int, str],
        index: int,
        dd_,
        sk_,
        mode_,
        form_,
        vldf_,
        artp_,
        dims_,
        axes_,
    ):
        """
        Create an AUSTAL grid file conform specifications.

        Source path, timestamps and data are taken from the attributes of the
         main class, other values may be specified as input parameters to this
         method.

        :param source: the identifier of the source
        :param index: the identifier of the grid file
        :param dd_: vertical grid (h0 h1 h2 ...), heights above ground in m
        :param sk_: vertical grid, heights above ground in m
        :param mode_: mode of the data part (text or binary)
        :param form_: format of a data element (e.g. Eq%5.1f or Eq%12.5e)
        :param vldf_: type of value (for post-processing, here V for volume
         value)
        :param artp_: array type description (should be set to M)
        :param dims_: dimension of the data part (for post-processing, must be
         set to 3)
        :param axes_: type of indices (for post-processing, must be set to xyz)
        """

        # Get the file path
        file_path = self.getGridFilePath(source, index)

        if file_path.exists():
            raise FileExistsError(file_path)

        # Get the (normalized) first time, current start time and end time
        _first = self._first_start_time
        _start = self._start_time
        _end = self._end_time

        # Get the number of days to the start/end since the start
        delta_f_start_days = (_start - _first).days
        delta_f_end_days = (_end - _first).days

        # Format the timestamps
        start_ = f"{delta_f_start_days}.{_start.strftime('%H:%M:%S')}"
        end_ = f"{delta_f_end_days}.{_end.strftime('%H:%M:%S')}"

        # Get the emissions grid dimensions
        x_dim, y_dim, z_dim = self._emission_grid_matrix.shape

        # Start writing to file
        with file_path.open("w") as text_file:

            # Write header: grid information
            text_file.write("t1\t%s\n" % start_)
            text_file.write("t2\t%s\n" % end_)
            text_file.write("dd\t%s\n" % dd_)
            text_file.write("sk\t%s\n" % sk_)

            # Add separator
            text_file.write("-\n")

            # Write header: data information
            text_file.write("mode\t%s\n" % mode_)
            text_file.write("form\t%s\n" % form_)
            text_file.write("vldf\t%s\n" % vldf_)
            text_file.write("artp\t%s\n" % artp_)
            text_file.write("dims\t%s\n" % dims_)
            text_file.write("axes\t%s\n" % axes_)
            text_file.write("sequ\t%s\n" % self.getSequ())

            # Add separator
            text_file.write("-\n")

            # Write header: data information
            text_file.write("lowb\t%s\n" % self._lowb)
            text_file.write("hghb\t%s\n" % self._hghb)

            # Add separator
            text_file.write("*\n")

            # Write data
            for x, y in itertools.product(*list(map(range, (x_dim, y_dim)))):
                text_file.write(
                    "%s\n"
                    % ("\t").join(
                        [
                            str(elem)
                            for elem in self._emission_grid_matrix[x, y].tolist()
                        ]
                    )
                )
                if y + 1 == y_dim:
                    text_file.write("\n")

            # Add terminator
            text_file.write("***\n")

    @log_time
    def writeInputFile(self):
        """
        Create an AUSTAL input file conform specifications.

        Parameters are taken from the attributes of the main class.
        """

        # Get the file path
        file_path = self.getOutputPathAsPath() / "austal.txt"

        if file_path.exists():
            raise FileExistsError(file_path)

        with file_path.open("w") as text_file:

            text_file.write("----------------- general parameters\n")
            text_file.write('ti\t"%s"\t\' title\n' % self._title)
            text_file.write("qs\t%s\t' quality level\n" % self._quality_level)
            text_file.write("----------------- meteorology\n")
            text_file.write("z0\t%s\t' roughness length (m)\n" % self._roughness_level)
            text_file.write(
                "d0\t%s\t' displacement height (m)\n" % self._displacement_height
            )
            text_file.write(
                "ha\t%s\t' anemometer height (m)\n" % self._anemometer_height
            )
            text_file.write("----------------- calculation grid\n")
            text_file.write("dd\t%s\t' mesh width\n" % self._mesh_width)
            text_file.write(
                "x0\t%s\t' left border (m)\n"
                % (self._x_left_border_calc_grid - self._reference_x)
            )
            text_file.write(
                "y0\t%s\t' lower border (m)\n"
                % (self._y_left_border_calc_grid - self._reference_y)
            )

            # Add receptor points
            if (
                (len(self.xp_) == len(self.yp_))
                and (len(self.xp_) == len(self.zp_))
                and (len(self.xp_) > 0)
            ):
                text_file.write(
                    "xp\t%s\t' x-receptor\n" % ("\t").join([str(rx) for rx in self.xp_])
                )
                text_file.write(
                    "yp\t%s\t' y-receptor\n" % ("\t").join([str(ry) for ry in self.yp_])
                )
                text_file.write(
                    "hp\t%s\t' z-receptor\n" % ("\t").join([str(rz) for rz in self.zp_])
                )

            text_file.write("nx\t%s\t' number of meshes\n" % self._x_meshes)
            text_file.write("ny\t%s\t' number of meshes\n" % self._y_meshes)
            text_file.write("----------------- source definitions\n")

            if self._options:
                text_file.write('os\t"%s"\n' % self._options)
            text_file.write(
                "iq\t%s\t' file index (set in series.dmna)\n"
                % ("\t").join(["?" for _iq_ in list(self._total_sources.keys())])
            )
            text_file.write(
                "hq\t%s\t' source height (ignored)\n"
                % ("\t").join(
                    [
                        str(self._source_height)
                        for _iq_ in list(self._total_sources.keys())
                    ]
                )
            )
            text_file.write(
                "xq\t%s\t' x-lower left (south-west) corner of the source\n"
                % ("\t").join(
                    [
                        str(self._x_left_border_em_grid - self._reference_x)
                        for _iq_ in list(self._total_sources.keys())
                    ]
                )
            )
            text_file.write(
                "yq\t%s\t' y-lower left (south-west) corner of the source\n"
                % ("\t").join(
                    [
                        str(self._y_left_border_em_grid - self._reference_y)
                        for _iq_ in list(self._total_sources.keys())
                    ]
                )
            )

            for poll in self._pollutants_list:
                if poll.startswith("PM"):
                    poll = "PM-2" if poll == "PM10" else "PM-1"
                text_file.write(
                    "%s\t%s\t' total %s (in g/s) (set in series.dmna)\n"
                    % (
                        poll.lower(),
                        ("\t").join(
                            [
                                "?" if poll in self._total_sources[src] else "0"
                                for iq, src in enumerate(self._total_sources.keys())
                            ]
                        ),
                        poll,
                    )
                )

    @log_time
    def writeTimeSeriesFile(self):
        """
        Create an AUSTAL time series file conform specifications.

        Parameters are taken from the attributes of the main class.
        """

        # Get the file path
        file_path = self.getOutputPathAsPath() / "series.dmna"

        if file_path.exists():
            raise FileExistsError(file_path)

        # Get the sorted results
        sorted_results = self.getSortedResults()

        form_line = ['"te%20lt"', '"ra%5.0f"', '"ua%5.1f"', '"lm%7.1f"']
        with file_path.open("w") as text_file:

            for iq_ in list(self._total_sources.keys()):
                form_line.append('"%s.iq%%3.0f"' % str(iq_))
            for iq_ in list(self._total_sources.keys()):
                for poll in self._total_sources[iq_]:
                    form_line.append('"%s.%s%%10.3e"' % (str(iq_), poll.lower()))

            text_file.write("form\t%s\n" % ("\t").join(form_line))
            text_file.write('mode\t"text"\n')
            text_file.write('sequ\t"i"\n')
            text_file.write("dims\t%s\n" % 1)
            text_file.write("lowb\t%s\n" % 1)
            text_file.write("hghb\t%s\n" % (len(list(sorted_results.keys()))))
            text_file.write("*\n")

            for dt in sorted_results:
                iqs = [
                    sorted_results[dt][iq]["timeID"]
                    if iq in list(sorted_results[dt].keys())
                    else 1
                    for iq in list(self._total_sources.keys())
                ]
                emission_rates = []
                for iq_ in list(self._total_sources.keys()):
                    for poll in self._total_sources[iq_]:
                        if (
                            iq_ in sorted_results[dt]
                            and poll in sorted_results[dt][iq_]
                        ):
                            emission_rates.append(
                                "{:10.3e}".format(sorted_results[dt][iq_][poll])
                            )
                        else:
                            emission_rates.append("{:10.3e}".format(0))

                text_file.write(
                    "%s\t%5.0f\t%5.1f\t%7.1f\t%s\t%s\n"
                    % (
                        dt,
                        self._series[dt]["WindDirection"],
                        self._series[dt]["WindSpeed"],
                        self._series[dt]["ObukhovLength"],
                        ("\t").join(["%3.0f" % (iq) for iq in iqs]),
                        ("\t").join([er for er in emission_rates]),
                    )
                )
            text_file.write("\n")
            text_file.write("***\n")

    @log_time
    def beginJob(self):
        if self.isEnabled():
            if self._grid is None:
                raise Exception(
                    "No 3DGrid found. Use parameter 'grid' to configure one on "
                    "AUSTAL2000OutputModule initialization (e.g. from "
                    "instantiated EmissionCalculation."
                )
            else:

                # Initialize the grid
                self.getGridXYFromReferencePoint()

                self._emission_grid_matrix = None

                self._x_meshes = self._grid._x_cells
                self._y_meshes = self._grid._y_cells
                self._z_meshes = self._grid._z_cells

                # AUSTAL2000 cannot take non square grid cells, choose finer
                # resolution (dd) for austal2000.txt
                self._mesh_width = min(
                    self._grid.getResolutionX(), self._grid.getResolutionY()
                )
                self._grid._x_resolution = self._mesh_width
                self._grid._y_resolution = self._mesh_width

                # Initialize the output path
                if not self._output_path:

                    # Ask for an output path
                    output_path = QtWidgets.QFileDialog.getExistingDirectory(
                        None, "AUSTAL2000: Select Output directory"
                    )

                    # Set the output path
                    self.setOutputPath(output_path)

                    if not self.getOutputPathAsPath().is_dir():
                        raise Exception(
                            "AUSTAL2000: Not a valid path for grid "
                            "source file %s'" % output_path
                        )
                    else:
                        self.emptyOutputPath()
                        self._grid_db_path = output_path

                # Initialize the results
                self._results = OrderedDict()
                self._series = OrderedDict()
                self._total_sources = OrderedDict()
                self._timeID_per_source = OrderedDict()
                self._dates = OrderedDict()
                self._source_geometries = OrderedDict()

                # Initialize the variables for the date normalization
                self._first_start_time = None
                self._start_time, self._end_time = None, None

    @log_time
    def process(
        self,
        start_time: InventoryTime,
        end_time: InventoryTime,
        result: List[Tuple[Union[Source, Movement], Emission]],
        ambient_conditions: AmbientCondition,
        **kwargs,
    ):
        """
        todo: rename result
        todo: add Source type

        Here we define the rest of the parameters for the austal2000.txt file
        (iq, xq, yq, hq, emission_rate). Moreover, we define the parameters for
        the grid source file (e????.dmna).

        The index can be specified as time dependent, hence an index running
         from 1 to 8760 for example (grid files e0001.dmna to e8760.dmna). This
         allows to specify a different relative spatial distribution of
         emissions for every hour of the year.

        Likewise, the overall emission rate of the grid can be specified as
         time-dependent with hourly means for every hour of the year. This
         combination provides a high flexibility.

        timeval: the actual date
        """

        # (i1 j1 k1, in this order)
        self._lowb = "1 1 1"

        # (i2 j2 k2, in this order)
        self._hghb = f"{self._x_meshes} {self._y_meshes} {self._z_meshes}"

        # Make sure that the calculation starts from yyyy-01-01.01.00.00
        _start_time, _end_time = self.set_normalized_date(start_time, end_time)
        _end_time_string = _end_time.strftime("%Y-%m-%d.%H:%M:%S")

        # Set results and series for this period if it has not been set
        self._results.setdefault(_end_time_string, OrderedDict())
        self._series.setdefault(_end_time_string, OrderedDict())

        # Add ambient conditions to the series
        self._series[_end_time_string].update(
            {
                "WindDirection": ambient_conditions.getWindDirection(),
                "WindSpeed": ambient_conditions.getWindSpeed(),
                "ObukhovLength": ambient_conditions.getObukhovLength(),
            }
        )

        # ToDo: how much finer/coarser is the emission dd ?
        # horizontal mesh width in m
        dd_ = self._mesh_width
        # vertical grid (h0 h1 h2 ...), heights above ground in m
        sk_ = " ".join(
            str(self._grid.getResolutionZ() * z) for z in range(self._z_meshes + 1)
        )

        # Loop over all emissions and append one data point for every cell to
        # total_emissions_per_cell_list for the specific result
        total_emissions_per_cell_list = []

        # Get the grid
        grid = self.getGrid()

        for (source_, emissions__) in result:

            self._source_height = 0
            if hasattr(source_, "getHeight") and source_.getHeight() > 0:
                self._source_height = source_.getHeight()

            for emissions_ in emissions__:

                # Get the geometry text
                e_wkt = emissions_.getGeometryText()
                if e_wkt is None:
                    logger.warning(
                        f"AUSTAL2000: Did not find geometry for "
                        f"source: {source_.getName()}"
                    )
                    continue

                # Get the geometry
                geom = emissions_.getGeometry()

                # Some convenience variables
                is_point_element_ = isinstance(geom, Point)
                is_line_element_ = isinstance(geom, LineString)
                is_multi_line_element_ = isinstance(geom, MultiLineString)
                is_polygon_element_ = isinstance(geom, Polygon)
                is_multi_polygon_element_ = isinstance(geom, MultiPolygon)

                # Convert the emissions to a series object
                e_series = pd.Series(emissions_.getObjects())

                if is_multi_polygon_element_ or is_multi_line_element_:

                    # Add the emissions for each geometry
                    for i, g in enumerate(geom):

                        # Get the WKT representation of the geometry
                        g_wkt = g.wkt

                        # Determine the emissions for this geometry based on
                        # area/length (depending on geometry type)
                        if isinstance(g, Polygon):
                            mpe_series = e_series * g.area / geom.area
                        elif isinstance(g, LineString):
                            mpe_series = e_series * g.length / geom.length
                        else:
                            raise TypeError(
                                f"Geometry of type {type(geom)} is not "
                                f"supported. It should be either a Polygon or "
                                f"a LineString"
                            )

                        # Get matched cell coefficients for this geometry
                        matched_cells_coeff = self.getMatchedCellCoeffs(
                            g_wkt,
                            emissions_,
                            grid,
                            is_point_element_,
                            is_line_element_,
                            is_polygon_element_,
                            is_multi_polygon_element_,
                        )

                        # Update the total emissions per cell
                        total_emissions_per_cell_list = self.updateEmissions(
                            total_emissions_per_cell_list,
                            mpe_series,
                            matched_cells_coeff,
                        )

                else:

                    # Get matched cell coefficients for this geometry
                    matched_cells_coeff = self.getMatchedCellCoeffs(
                        e_wkt,
                        emissions_,
                        grid,
                        is_point_element_,
                        is_line_element_,
                        is_polygon_element_,
                        is_multi_polygon_element_,
                    )

                    # Update the total emissions per cell
                    total_emissions_per_cell_list = self.updateEmissions(
                        total_emissions_per_cell_list, e_series, matched_cells_coeff
                    )

        # Create cumulative emissions per cell
        try:
            total_emissions_per_cell_df = (
                pd.concat(total_emissions_per_cell_list).groupby(level=0).sum()
            )
        except ValueError:

            # Create an empty dataframe with the right columns
            total_emissions_per_cell_df = pd.DataFrame(
                columns=[f"{p.lower()}_kg" for p in self._pollutants_list]
            )

        # Get the output path (as Path)
        output_path = self.getOutputPathAsPath()
        fill_results = OrderedDict()

        logger.debug(f"Pollutions list: {self._pollutants_list}")
        logger.debug(f"Emissions list: {total_emissions_per_cell_df.columns}")

        # Fill Emissions Matrix with emission rate (normalised to 1)
        for source_counter, _pollutant in enumerate(self._pollutants_list):

            # Start the counter at 1
            source_counter += 1

            # Create the source id
            source_id = str(source_counter).zfill(2)

            # Create the source directory if it doesn't exist
            source_dir = output_path / source_id
            if not source_dir.is_dir():
                source_dir.mkdir()

            # initialize emission matrix for each pollutant
            # (x_dim, y_dim, z_dim) = self.InitializeEmissionGridMatrix()

            # Get the emissions for this pollutant
            _pollutant_emissions = total_emissions_per_cell_df.filter(
                regex=f"^{_pollutant.lower()}_k?g$"
            )

            # Convert to kg (if only g is present)
            _columns = _pollutant_emissions.columns
            if _columns.str.endswith("_g").any():
                for _column in _columns[_columns.str.endswith("_g")]:
                    _pollutant_emissions[_column[:-1] + "kg"] = (
                        _pollutant_emissions[_column] / 1000
                    )

            # Get the total emissions in kg
            if len(_columns) != 1:
                raise ValueError(
                    f"The number of matching columns should be 1, " f"got {_columns}"
                )

            # Get the column name
            _column_name = _columns[0]

            # Get the emissions for this pollutant in kg
            _pollutant_emissions_kg = _pollutant_emissions[
                _column_name[:-1] + "kg"
                if _column_name.endswith("_g")
                else _column_name
            ]

            # Get the total emissions in kg
            hashed_emissions = _pollutant_emissions_kg.sum()

            # Initialize the emissions grid and get the dimensions
            dims = self.InitializeEmissionGridMatrix()
            # x_dim, y_dim, z_dim = dims

            # Split the sequ once
            sequ_split = self.getSequ().split(",")

            # Get the indices
            sequ_indices = [i[0] for i in sequ_split]

            # Get the signs
            sequ_signs = [i[1] for i in sequ_split]

            # Determine the transformation matrix
            _o = np.array(list("ijk"))
            _p = np.array(sequ_indices)
            _a = (_o == _p[:, np.newaxis]).astype(int)

            # Determine the constants
            _b = np.zeros((3, 1))

            # Modify the values based on the signs
            _sequ_signs = np.array(sequ_signs) == "-"
            _dims = np.array(dims)

            _b[_sequ_signs] = _dims[_sequ_signs] - 1
            _a[_sequ_signs] *= -1

            # Only perform these steps if there are emissions for this pollutant
            if hashed_emissions > 0:

                # logger.debug(_pollutant_emissions_kg)

                # # initialize emission matrix for each pollutant
                # # (x_dim, y_dim, z_dim) = self.InitializeEmissionGridMatrix()
                # for hash in total_emissions_per_cell_dict:

                # Get the non-zero emissions
                nz_emissions_kg = _pollutant_emissions_kg[_pollutant_emissions_kg > 0]

                for hash, hash_value in nz_emissions_kg.iteritems():

                    # Get the XYZ indices
                    vvv = self._grid.convertCellHashToXYZIndices(hash)

                    # Check if the indices are within the bounds
                    if (
                        (vvv[0] >= self._x_meshes)
                        or (vvv[1] >= self._y_meshes)
                        or (vvv[2] >= self._z_meshes)
                    ):
                        # logger.debug("AUSTAL2000 Error: Grid needs to be
                        # enlarged. Hash '%s' out of grid. Source:'%s'"%(hash,
                        # source_.getName()))
                        continue

                    # Convert the indices of the cell hash to the emission grid
                    ii, jj, kk = (
                        (_a @ np.array(vvv)[:, np.newaxis] + _b)
                        .T[0]
                        .astype(int)
                        .tolist()
                    )

                    # Update the values in the emissions grid
                    self._emission_grid_matrix[ii, jj, kk] += (
                        hash_value / hashed_emissions
                    )

            self._total_sources.setdefault(source_id, [])
            if _pollutant.startswith("PM"):
                _pollutant = "PM-2" if _pollutant == "PM10" else "PM-1"
            if _pollutant not in self._total_sources[source_id]:
                self._total_sources.setdefault(source_id, []).append(_pollutant)

            # Update the source id
            if source_id in self._timeID_per_source:
                time_id = self._timeID_per_source[source_id]
                self._timeID_per_source.update({source_id: time_id + 1})
            else:
                self._timeID_per_source.update({source_id: 1})

            # Emission rate in AUSTAL2000 is in g/s (kg x 1000/3600),
            # hashed_emissions are given in kg/h
            fill_results.setdefault(source_id, {})

            pollutant_dic = {
                _pollutant: hashed_emissions * (10.0 / 36.0),
                "timeID": self._timeID_per_source[source_id],
            }

            fill_results[source_id].update(pollutant_dic)

            self._results[_end_time_string].update(fill_results)

            # Start writing to file
            try:
                self.writeGridFile(
                    source_id,
                    self._timeID_per_source[source_id],
                    dd_,
                    sk_,
                    '"text"',
                    '"Eq%5.1f"',
                    '"V"',
                    '"M"',
                    3,
                    '"xyz"',
                )

            except Exception as exc_:
                logger.error(exc_)

    @log_time
    def endJob(self):
        if self.isEnabled():
            try:
                if not self.checkTimeIntervalinResults():
                    raise Exception("AUSTAL2000: Time Interval Error")

                try:
                    self.writeInputFile()
                except Exception as e:
                    logger.error("AUSTAL2000: Cannot write 'austal.txt' : %s" % e)
                    return False

                self.checkHoursinResults()

                try:
                    self.writeTimeSeriesFile()
                    return True
                except Exception as e:
                    logger.error("AUSTAL2000: Cannot write 'Series.dmna' %s", e)
                    return False

            except Exception as e:
                logger.error("AUSTAL2000: Cannot endJob: %s" % e)
                return False

    # Available Substances in AUSTAL2000
    # so2: Sulphur dioxide, SO2
    # no: Nitrogen monoxide, NO
    # no2: Nitrogen dioxide, NO2
    # nox: Nitrogen oxides, NOx (specified as NO2 )
    # bzl: Benzene
    # tce: Tetrachloroethylene
    # f: Hydrogen fluoride (specified as F)
    # nh3: Ammonia, NH3
    # hg: Mercury, Hg, according to TA Luft (vd =0.005 m/s) hg0 Elementary mercury, Hg(0) (vd =0.0003 m/s)
    # xx: Unspecified
    # odor: Unrated odorant
    # odor:_nnn Rated odorant with a rate factor resulting from the identifier nnn,
    # see Section 3.10. Possible values for nnn are: 050 (in the fed- eral state Baden-Württemberg: 040),
    # 075 (in the federal state Baden- Württemberg: 060), 100, 150

    @log_time
    def getMatchedCellCoeffs(
        self,
        wkt: str,
        emissions_: Emission,
        grid: Grid3D,
        is_point_element_: bool,
        is_line_element_: bool,
        is_polygon_element_: bool,
        is_multi_polygon_element_: bool,
    ):
        """
        Get matched cells for this coefficients

        """

        # Check if the matched cells are know for this geometry
        if wkt in self._source_geometries:

            # Get the matched cells for this geometry
            return self._source_geometries[wkt]["efficiency"]

        # Determine the bounding box
        bbox = self.getBoundingBox(wkt)

        # Get the vertical extent
        vertical_extent = emissions_.getVerticalExtent()

        # Take into account the effective vertical source extent and shift
        if "delta_z" in vertical_extent and vertical_extent["delta_z"] > 0:
            bbox["z_max"] = bbox["z_max"] + vertical_extent["delta_z"]

        # Get the matched cells for this geometry
        matched_cells = grid.matchBoundingBoxToCellHashList(bbox, z_as_list=True)
        matched_cells_coeff = self.CalculateCellHashEfficiency(
            wkt,
            bbox,
            matched_cells,
            is_point_element_,
            is_line_element_,
            is_polygon_element_,
            is_multi_polygon_element_,
        )

        # Store the matched cells for this geometry
        self._source_geometries[wkt] = {
            "bbox": bbox,
            "matched_cells": matched_cells,
            "efficiency": matched_cells_coeff,
        }

        return matched_cells_coeff

    @log_time
    def updateEmissions(
        self,
        cumulative_cell_emissions: list,
        emissions: pd.Series,
        cell_coefficients: dict,
    ):

        # Create a series from the cell-coefficients
        cell_coefficients_series = pd.Series(cell_coefficients)

        # Create a dataframe with all emissions for each cell
        cell_emissions = pd.DataFrame(
            emissions.values * cell_coefficients_series.values[:, np.newaxis],
            columns=emissions.index,
            index=cell_coefficients_series.index,
        )

        # Append the emissions to the list
        cumulative_cell_emissions.append(cell_emissions)

        # Return the list
        return cumulative_cell_emissions
