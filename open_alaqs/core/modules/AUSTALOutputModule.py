import itertools
import os
import re
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple, Union

import geopandas as gpd
import numpy as np
import pandas as pd
from dateutil import rrule
from pyproj import Transformer as _ProjTransformer
from qgis.gui import QgsDoubleSpinBox, QgsSpinBox
from qgis.PyQt import QtWidgets
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon
from shapely.ops import transform as _shapely_transform
from shapely.validation import make_valid as _make_valid

from open_alaqs.alaqs_config import DEFAULT_CONCENTRATION_GRID_FACTOR
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.AmbientCondition import AmbientCondition
from open_alaqs.core.interfaces.DispersionModule import DispersionModule
from open_alaqs.core.interfaces.Emissions import Emission
from open_alaqs.core.interfaces.Movement import Movement
from open_alaqs.core.interfaces.Source import Source
from open_alaqs.core.tools import conversion, spatial, sql_interface
from open_alaqs.core.tools.Grid3D import Grid3D

logger = get_logger(__name__)

# AUSTAL's built-in default vertical grid (heights above ground in m).
# When austal.txt omits the 'sk' line, AUSTAL uses this progressive grid
# internally.  The per-source grid files (e000N.dmna) must declare an
# 'sk' that is consistent with the computation grid.  Using a coarser
# uniform grid (e.g. 50 m spacing) artificially dilutes ground-level
# emissions over a thick layer, producing unrealistically low surface
# concentrations.
# 20 boundaries -> 19 vertical cells; first cell spans 0-3 m.
AUSTAL_DEFAULT_SK = (
    0,
    3,
    6,
    10,
    16,
    25,
    40,
    65,
    100,
    150,
    200,
    300,
    400,
    500,
    600,
    700,
    800,
    1000,
    1200,
    1500,
)


def log_time(func):
    def inner(*args, **kwargs):
        start = datetime.now()
        result = func(*args, **kwargs)
        finish = datetime.now()
        logger.debug(f"Time elapsed {func.__name__}: {finish - start}")
        return result

    return inner


class AUSTALDispersionModule(DispersionModule):
    """
    Module for the preparation of the input files needed for AUSTAL
    dispersion calculations.
    """

    settings_schema = {
        "is_enabled": {
            "label": "Is Enabled",
            "initial_value": False,
            "widget_type": QtWidgets.QCheckBox,
            "tooltip": "Enable to create AUSTAL input files",
        },
        "title": {
            "label": "Title",
            "initial_value": "",
            "widget_type": QtWidgets.QLineEdit,
        },
        "mixing_height_enabled": {
            "label": "Include Mixing Height",
            "initial_value": False,
            "widget_type": QtWidgets.QCheckBox,
            "tooltip": "Enable to include mixing height in AUSTAL input files",
        },
        "roughness_length_m": {
            "label": "Roughness Length",
            "initial_value": 0.2,
            "widget_type": QgsDoubleSpinBox,
            "widget_config": {
                "minimum": 0,
                "maximum": 999999.9,
                "suffix": "m",
            },
        },
        "displacement_height_m": {
            "label": "Displacement Height",
            "initial_value": 1.2,
            "widget_type": QgsDoubleSpinBox,
            "widget_config": {
                "minimum": 0,
                "maximum": 999999.9,
                "suffix": "m",
            },
        },
        "anemometer_height_m": {
            "label": "Anemometer Height",
            "initial_value": 11.2,
            "widget_type": QgsDoubleSpinBox,
            "widget_config": {
                "minimum": 0,
                "maximum": 999999.9,
                "suffix": "m",
            },
        },
        "quality_level": {
            "label": "Quality Level",
            "initial_value": 1,
            "widget_type": QgsSpinBox,
            "widget_config": {
                "minimum": 1,
                "maximum": 10,
            },
            "tooltip": "+1 doubles the number of simulation particles",
        },
        "options_string": {
            "label": "Options String",
            "initial_value": "NOSTANDARD;SCINOTAT;Kmax=1",
            "widget_type": QtWidgets.QLineEdit,
            "tooltip": "Options must be defined successively and separated by a semicolon",
        },
    }

    @staticmethod
    def getModuleName():
        return "AUSTAL"

    @staticmethod
    def getModuleDisplayName():
        return "AUSTAL"

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        DispersionModule.__init__(self, values_dict)

        self._name = values_dict.get("name", "")
        self._model = "AUSTAL"
        self._pollutant = values_dict.get("pollutant", "NOx")
        self._receptors = values_dict.get("receptors", gpd.GeoDataFrame())
        self._output_path = values_dict.get("output_path")

        # Create the output directory if it does not exist
        if self._output_path is not None:
            # self._def_output_path = copy.deepcopy(self._output_path)
            if not os.path.isdir(self._output_path):
                os.mkdir(self._output_path)

        self._sequ = "k+,j-,i+"
        self._grid: Grid3D = values_dict.get("grid", None)

        self._pollutants_list = values_dict.get("pollutants_list")

        if not self._pollutants_list and self._pollutant:
            self._pollutants_list = [self._pollutant]

        # ------------------------------------------------------------------
        # AUSTAL grid writer (time-indexed layout):
        # stationary sources (Source.time_invariant_geometry == True) get
        # per-hour identical eNNNN.dmna files under their own slot, with
        # iq=h_idx+1 in series.dmna. Non-stationary sources (movements /
        # gates / taxiways) keep the legacy per-hour layout under slot
        # 01/, with iq counting per-source. The hybrid series.dmna
        # combines both.
        #
        self._enable = values_dict.get("is_enabled", False)
        # "----------------- general parameters",
        self._mixing_height = values_dict.get("mixing_height_enabled", False)

        self._title = values_dict.get("title", "no title")
        self._quality_level = values_dict.get("quality_level", 1)
        # for non-standard calculations
        self._options = values_dict.get("options_string", "SCINOTAT")

        # "----------------- meteorology",
        # ToDo: Modify AmbientCondition.py or derive z0, d0, and ha from main
        #  dialog (airport info)
        # "z\t0.2\t' roughness length (m)",
        self._roughness_level = values_dict.get("roughness_length_m", 0.2)
        # d0: default 6z0    # "d0\t1.2\t' displacement height (m)",
        self._displacement_height = values_dict.get(
            "displacement_height_m", 6 * self._roughness_level
        )
        # 10 m + d0 (6z0)  # "ha\t11.2\t' anemometer height (m)",
        self._anemometer_height = values_dict.get(
            "anemometer_height_m", 10 + 6 * self._roughness_level
        )

        self._reference_x = None
        self._reference_y = None
        self._reference_z = None
        # receptor points
        self.xp_, self.yp_, self.zp_ = [], [], []

        # "----------------- concentration grid -----------------"
        self._x_left_border_calc_grid = None  # "x0\t-200\t' left border (m)",
        self._y_left_border_calc_grid = None  # "y0\t-200\t' lower border (m)",

    def isEnabled(self):
        return self._enable

    def MixingHeightIncluded(self):
        return self._mixing_height

    def getModel(self):
        return self._model

    def setModel(self, val):
        self._model = val

    def getSequ(self) -> str:
        """
        Index sequence in which the data values are listed (comma separated)
        (from AUSTAL grid source example)

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
        Computes the reference point and grid borders in the local UTM CRS
        (obtained from Grid3D.getUtmEpsg()).  All AUSTAL coordinate outputs
        (dd, x0, y0, xq, yq, xp, yp) are therefore in true metric metres —
        no post-hoc scale correction is required.
        """
        try:
            try:
                ref_lon = float(self._grid._reference_longitude)
                ref_lat = float(self._grid._reference_latitude)
            except (TypeError, ValueError) as e:
                raise ValueError(
                    f"AUSTAL: Invalid grid reference coordinates "
                    f"(longitude={self._grid._reference_longitude!r}, "
                    f"latitude={self._grid._reference_latitude!r}): {e}"
                )

            utm_epsg = self._grid.getUtmEpsg()
            reference_point_wkt = "POINT (%s %s)" % (ref_lon, ref_lat)
            logger.info(
                "AUSTAL: Grid reference point: %s (UTM EPSG:%d)",
                reference_point_wkt,
                utm_epsg,
            )

            sql_text = (
                "SELECT X(ST_Transform(ST_PointFromText('%s', 4326), %d)), Y(ST_Transform(ST_PointFromText('%s', 4326), %d));"
                % (reference_point_wkt, utm_epsg, reference_point_wkt, utm_epsg)
            )
            result = sql_interface.query_text(self._grid._db_path, sql_text)
            if result is None:
                raise Exception(
                    "AUSTAL: Could not reset reference point as coordinates could not be transformed. The query was\n'%s'"
                    % (sql_text)
                )

            self._reference_x = conversion.convertToFloat(result[0][0])
            self._reference_y = conversion.convertToFloat(result[0][1])
            self._reference_z = self._grid._reference_altitude

            # Grid3D._grid_origin_x/y is already in UTM — reuse it directly
            # instead of recomputing from the reference point.
            grid_origin_x = self._grid._grid_origin_x
            grid_origin_y = self._grid._grid_origin_y

            # Calc grid is offset 2 cells SW of the em grid so AUSTAL
            # sources placed at xq=grid_origin sit 2 cells inside the
            # calc grid SW corner (AUSTAL rejects sources at or outside
            # the calc grid border). The calc grid is also enlarged by
            # 2 cells on each side (4 cells total per axis) so that
            # the 40x40 em grid fits exactly in the centre of the
            # calc grid, giving symmetric halo and clean overlap of
            # the emissions and concentration QGIS layers.
            self._x_left_border_calc_grid = (
                grid_origin_x
                - DEFAULT_CONCENTRATION_GRID_FACTOR * float(self._grid._x_resolution)
            )
            self._y_left_border_calc_grid = (
                grid_origin_y
                - DEFAULT_CONCENTRATION_GRID_FACTOR * float(self._grid._y_resolution)
            )

            self._x_left_border_em_grid = grid_origin_x
            self._y_left_border_em_grid = grid_origin_y

            try:
                if not self._receptors.empty:
                    _AUSTAL_MAX_RECEPTORS = 20
                    _epsg_col = "EPSG" if "EPSG" in self._receptors.columns else "crs"

                    unique_epsg = self._receptors[_epsg_col].unique()
                    if len(unique_epsg) > 1:
                        raise ValueError(
                            f"Receptor points CSV contains mixed EPSG codes: "
                            f"{unique_epsg.tolist()}. All rows must use the same CRS."
                        )
                    _epsg_val = int(unique_epsg[0])

                    receptors = self._receptors
                    if (
                        "geometry" not in receptors.columns
                        or receptors.geometry.isna().all()
                    ):
                        if (
                            "longitude" not in receptors.columns
                            or "latitude" not in receptors.columns
                        ):
                            raise ValueError(
                                "Receptor points GeoDataFrame has no geometry column "
                                "and no 'longitude'/'latitude' columns to build one from."
                            )
                        import geopandas as _gpd

                        receptors = _gpd.GeoDataFrame(
                            receptors,
                            geometry=_gpd.points_from_xy(
                                receptors["longitude"], receptors["latitude"]
                            ),
                            crs=f"EPSG:{_epsg_val}",
                        )
                    else:
                        receptors = receptors.set_crs(
                            f"EPSG:{_epsg_val}", allow_override=True
                        )

                    # Project receptors into UTM — same CRS as the grid.
                    receptors_projected = receptors.to_crs(f"EPSG:{utm_epsg}")

                    if len(receptors_projected) > _AUSTAL_MAX_RECEPTORS:
                        logger.warning(
                            "AUSTAL supports at most %d receptor points; "
                            "%d provided — truncating to the first %d.",
                            _AUSTAL_MAX_RECEPTORS,
                            len(receptors_projected),
                            _AUSTAL_MAX_RECEPTORS,
                        )
                        receptors_projected = receptors_projected.iloc[
                            :_AUSTAL_MAX_RECEPTORS
                        ]

                    for idp in receptors_projected.index:
                        rec_point = receptors_projected.loc[idp, "geometry"]
                        self.xp_.append(round(rec_point.x - self._reference_x, 2))
                        self.yp_.append(round(rec_point.y - self._reference_y, 2))
                        z_val = rec_point.z if rec_point.has_z else 1.5
                        self.zp_.append(z_val)
            except Exception as exc_:
                logger.warning(
                    "Couldn't add receptor points to dispersion study (%s)" % exc_
                )
            return True

        except Exception as e:
            logger.error(
                "AUSTAL: Could not reset 3D grid origin from reference point: %s" % e
            )
            return False

    def InitializeEmissionGridMatrix(self):
        if (self._grid is None) or (self._sequ is None):
            raise Exception(
                "Cannot initialize the emissions grid. No 3DGrid or" " Sequence found."
            )

        # Split the sequ once
        sequ_split = self.getSequ().split(",")

        # Check for each index which mesh to link.
        # Use em grid sizes (the source/emission spatial pattern); the
        # calc grid (`_x_meshes`) is only used in austal.txt to declare
        # the larger dispersion domain.
        indices = [None, None, None]
        for p, q in enumerate(sequ_split):
            if q.startswith("k"):
                indices[p] = self._z_meshes
            elif q.startswith("j"):
                indices[p] = self._y_em_meshes
            else:
                indices[p] = self._x_em_meshes
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
                QtWidgets.QMessageBox.StandardButton.Yes,
                QtWidgets.QMessageBox.StandardButton.No,
            )

            if answer == QtWidgets.QMessageBox.StandardButton.Yes:
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
            logger.error(
                "AUSTAL Error: Contradictory data for series.dmna and austal.txt files"
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
                "AUSTAL Warning: The time series must start at "
                "time 01 (found %s)" % first_key
            )

        # Make sure that the study spans at least one full day
        if (end_date - start_date).total_seconds() < 86400:
            # AUSTAL convention: a "day" is 24 timestamps inclusive of
            # 01:00..00:00, so the last hour is start + 23h. The warning text
            # and the assignment must agree on +23h.
            new_end_date = start_date + timedelta(hours=23)
            logger.warning(
                "A2K warning: The time series must cover at least "
                "one day. End date will be changed from %s to %s",
                end_date,
                new_end_date,
            )
            end_date = new_end_date

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
                            "MixingHeight": 914.4,
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
    def set_normalized_date(self, start_dt: datetime, end_dt: datetime):
        """
        AUSTAL requires the calculation to start from yyyy-01-01.01.00.00.
         Therefore the dates should be normalized.

        :param start_time:
        :param end_time:
        """

        # Check if the date has already been set
        if self._first_start_time is None:

            # Determine the timedelta
            t_delta = start_dt - start_dt.replace(
                month=1, day=1, hour=0, minute=0, second=0
            )

            logger.info(
                f"Normalize start date to ensure that AUSTAL starts "
                f"from yyyy-01-01.01.00.00 with the following time "
                f"delta: {t_delta}"
            )

            # Set the timestamps for the current period
            self._start_time = start_dt - t_delta
            self._end_time = end_dt - t_delta

            # Set the first start time
            self._first_start_time = self._start_time

        else:
            # Increment the timestamps to get the current period
            self._start_time += timedelta(hours=+1)
            self._end_time += timedelta(hours=+1)

        # Add the timestamps to the dates
        if start_dt not in self._dates:
            self._dates[start_dt] = [self._start_time, self._end_time]

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
                x_, y_, z_ = self._grid.convertCellHashListToCenterGridCellCoordinates(
                    [cell_hash]
                )[cell_hash]

                # Get the cell box
                cell_bbox = self.getCellBox(x_, y_, z_, self._grid)

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
    def beginJob(self):
        if self.isEnabled():
            if self._grid is None:
                raise Exception(
                    "No 3DGrid found. Use parameter 'grid' to configure one on "
                    "AUSTALOutputModule initialization (e.g. from "
                    "instantiated EmissionCalculation."
                )
            else:

                # Initialize the grid
                self.getGridXYFromReferencePoint()

                self._emission_grid_matrix = None

                # Two grid sizes are tracked:
                #   _x_em_meshes / _y_em_meshes : the em (source) grid
                #     dimensions. eNNNN.dmna grid files and the
                #     internal _emission_grid_matrix are this size.
                #   _x_meshes / _y_meshes      : the calc (dispersion)
                #     grid dimensions. austal.txt writes these as nx/ny.
                # The calc grid is the em grid plus DEFAULT_CONCENTRATION_GRID_FACTOR
                # cells of halo on each side; AUSTAL requires the source
                # grid to sit entirely inside the calc grid.
                self._x_em_meshes = self._grid._x_cells
                self._y_em_meshes = self._grid._y_cells
                self._x_meshes = (
                    self._x_em_meshes + 2 * DEFAULT_CONCENTRATION_GRID_FACTOR
                )
                self._y_meshes = (
                    self._y_em_meshes + 2 * DEFAULT_CONCENTRATION_GRID_FACTOR
                )
                self._z_meshes = len(AUSTAL_DEFAULT_SK) - 1  # 19 levels

                # AUSTAL cannot take non square grid cells, choose finer
                # resolution (dd) for austal.txt
                self._mesh_width = min(
                    self._grid.getResolutionX(), self._grid.getResolutionY()
                )
                self._grid._x_resolution = self._mesh_width
                self._grid._y_resolution = self._mesh_width

                # Initialize the output path
                if not self._output_path:

                    # Ask for an output path
                    output_path = QtWidgets.QFileDialog.getExistingDirectory(
                        None, "AUSTAL: Select Output directory"
                    )

                    # Set the output path
                    self.setOutputPath(output_path)

                    if not self.getOutputPathAsPath().is_dir():
                        raise Exception(
                            "AUSTAL: Not a valid path for grid "
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

                # Build a reusable pyproj Transformer for WKT reprojection.
                # _transform_wkt_to_utm() is called on every cache miss; using
                # a pre-built Transformer avoids constructing a GeoDataFrame,
                # CRS object, and Transformer pipeline from scratch each time.
                utm_epsg = self._grid.getUtmEpsg()
                self._wkt_transformer = _ProjTransformer.from_crs(
                    "EPSG:3857", f"EPSG:{utm_epsg}", always_xy=True
                )

                # Initialize the variables for the date normalization
                self._first_start_time = None
                self._start_time, self._end_time = None, None

                # ----------------------------------------------------------
                # AUSTAL time-indexed path state.
                #
                # process() splits incoming `result` into stationary
                # sources (where source.time_invariant_geometry is True)
                # and non-stationary ones. Stationary contributions
                # accumulate into a per-source (n_hours, n_pollutants)
                # g/s ndarray; their cell weights are computed once on
                # first encounter via austal_helpers.compute_cell_weights
                # and cached. Non-stationary sources fall through to the
                # per-hour grid file path used for movements.
                #
                # endJob() aggregates the stationary ndarray by `<type>:`
                # prefix, writes per-hour identical eNNNN.dmna under each
                # group's directory, and emits a hybrid series.dmna with
                # mixed iq semantics.
                # ----------------------------------------------------------
                self._ti_grid_spec = None
                self._ti_rates_per_source = (
                    {}
                )  # source_id -> ndarray (n_hours, n_pollutants) g/s
                self._ti_cell_weights = (
                    {}
                )  # source_id -> CellWeights (cached, computed once)
                self._ti_year_start = None
                self._ti_n_hours_year = 0
                self._ti_pollutant_order = []
                self._ti_source_meta = {}  # source_id -> {height, type_label}
                self._ti_skipped_no_geometry = set()

                from open_alaqs.core.tools.austal_helpers import AustalGridSpec

                # Grid origin in ABSOLUTE UTM metres, matching the frame
                # returned by `_transform_wkt_to_utm` and the Grid3D cell
                # bounds used by the per-hour movement path. The
                # reference-point subtraction is only applied at the
                # austal.txt write stage (relative `x0`/`y0` values),
                # not here.
                # _ti_grid_spec describes the EM grid (origin and size
                # of the source/emission area). The CALC grid (used for
                # AUSTAL dispersion in austal.txt) is enlarged by
                # `halo` cells on each side. The grid file (eNNNN.dmna)
                # is em-sized; AUSTAL anchors it at xq = em origin.
                self._ti_grid_spec = AustalGridSpec(
                    dd=float(self._mesh_width),
                    nx=int(self._grid._x_cells),
                    ny=int(self._grid._y_cells),
                    x0=float(self._x_left_border_em_grid),
                    y0=float(self._y_left_border_em_grid),
                    sk=tuple(float(s) for s in AUSTAL_DEFAULT_SK),
                )
                # Pollutant axis is fixed by self._pollutants_list and
                # ordered as the user/UI provided it. Frozen here so
                # accumulation arrays have a stable column meaning for
                # the rest of the run.
                self._ti_pollutant_order = list(self._pollutants_list or [])
                logger.debug(
                    "AUSTAL time-indexed mode: grid %dx%dx%d dd=%g x0=%g y0=%g, pollutants=%s",
                    self._ti_grid_spec.nx,
                    self._ti_grid_spec.ny,
                    self._ti_grid_spec.n_layers,
                    self._ti_grid_spec.dd,
                    self._ti_grid_spec.x0,
                    self._ti_grid_spec.y0,
                    self._ti_pollutant_order,
                )

    @staticmethod
    def _iter_primitives(geom):
        """
        Yield individual sub-geometries together with their emission weight
        (fraction of the top-level emission to assign to each sub-geometry).

        - Simple geometry (LineString, Polygon, Point, …): yielded as-is with weight 1.0.
        - MultiLineString / MultiPolygon: each sub-geometry is yielded with a weight
          proportional to its length / area relative to the total.
        """
        if isinstance(geom, (MultiLineString, MultiPolygon)):
            total = geom.length if isinstance(geom, MultiLineString) else geom.area
            for g in geom.geoms:
                sub_total = g.length if isinstance(geom, MultiLineString) else g.area
                for primitive, weight in AUSTALDispersionModule._iter_primitives(g):
                    yield primitive, weight * (sub_total / total if total > 0 else 0)
        else:
            yield geom, 1.0

    @log_time
    def process(
        self,
        start_dt: datetime,
        end_dt: datetime,
        result: List[Tuple[Union[Source, Movement], Emission]],
        ambient_conditions: AmbientCondition,
        **kwargs,
    ):
        """
        todo: rename result
        todo: add Source type

        Here we define the rest of the parameters for the austal.txt file
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
        self._hghb = f"{self._x_em_meshes} {self._y_em_meshes} {self._z_meshes}"

        # Make sure that the calculation starts from yyyy-01-01.01.00.00
        _start_time, _end_time = self.set_normalized_date(start_dt, end_dt)
        _end_time_string = _end_time.strftime("%Y-%m-%d.%H:%M:%S")

        # ------------------------------------------------------------------
        # Peel stationary sources off `result` so the per-hour body
        # below sees only non-stationary sources. Stationary contributions
        # are accumulated into the per-source rate ndarray and their
        # cell weights are cached on first encounter.
        #
        # endJob() consumes _ti_rates_per_source and _ti_cell_weights
        # to write per-hour identical eNNNN.dmna files per group plus
        # the hybrid series.dmna.
        # ------------------------------------------------------------------
        result = self._ti_split_and_accumulate(start_dt, result)

        # Set results and series for this period if it has not been set
        self._results.setdefault(_end_time_string, OrderedDict())
        self._series.setdefault(_end_time_string, OrderedDict())

        # Add ambient conditions to the series
        self._series[_end_time_string].update(
            {
                "WindDirection": ambient_conditions.getWindDirection(),
                "WindSpeed": ambient_conditions.getWindSpeed(),
                "ObukhovLength": ambient_conditions.getObukhovLength(),
                "MixingHeight": ambient_conditions.getMixingHeight(),
            }
        )

        # ToDo: how much finer/coarser is the emission dd ?
        # horizontal mesh width in m
        dd_ = self._mesh_width
        # vertical grid (h0 h1 h2 ...), heights above ground in m.
        # Must match the AUSTAL computation grid (its built-in default)
        # so that the first cell is thin (0-3 m) rather than the coarse
        # uniform grid stored in Grid3D (e.g. 0-50 m).
        sk_ = " ".join(str(h) for h in AUSTAL_DEFAULT_SK)

        # Loop over all emissions and append one data point for every cell to
        # total_emissions_per_cell_list for the specific result
        total_emissions_per_cell_list = []

        # Get the grid
        for source_, emissions__ in result:

            self._source_height = 0
            if hasattr(source_, "getHeight") and source_.getHeight() > 0:
                self._source_height = source_.getHeight()

            _src_name = (
                source_.getName() if hasattr(source_, "getName") else str(source_)
            )

            for _em_idx, emissions_ in enumerate(emissions__):

                # Get the geometry text
                wkt_text = emissions_.getGeometryText()
                if wkt_text is None:
                    # Zero-valued placeholders are synthesised by EmissionCalculation for
                    # empty periods; skip silently. Only warn for the real-bug case where
                    # a non-zero emission reaches AUSTAL without geometry.
                    if not emissions_.isZero():
                        logger.warning(
                            "AUSTAL: Did not find geometry for source '%s' (emission %d/%d)",
                            _src_name,
                            _em_idx + 1,
                            len(emissions__),
                        )
                    continue

                # Get the geometry
                geom = emissions_.getGeometry()

                # Convert the emissions to a series object
                _em_objects = emissions_.getObjects()
                e_series = pd.Series(_em_objects)

                for primitive, weight in AUSTALDispersionModule._iter_primitives(geom):
                    p_is_point = isinstance(primitive, Point)
                    p_is_line = isinstance(primitive, LineString)
                    p_is_polygon = isinstance(primitive, Polygon)
                    p_is_multi_polygon = isinstance(primitive, MultiPolygon)

                    matched_cells_coeff = self.getMatchedCellCoeffs(
                        primitive.wkt,
                        emissions_,
                        self._grid,
                        p_is_point,
                        p_is_line,
                        p_is_polygon,
                        p_is_multi_polygon,
                    )

                    total_emissions_per_cell_list = self.updateEmissions(
                        total_emissions_per_cell_list,
                        e_series * weight,
                        matched_cells_coeff,
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

        if logger.isEnabledFor(10):
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

            # Initialise the matrix for each pollutant
            self.InitializeEmissionGridMatrix()

            # initialize emission matrix for each pollutant
            # (x_dim, y_dim, z_dim) = self.InitializeEmissionGridMatrix()

            # Get the emissions for this pollutant
            _pollutant_emissions = total_emissions_per_cell_df.filter(
                regex=f"(?i)^{re.escape(_pollutant)}_k?g$"
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
                (
                    _column_name[:-1] + "kg"
                    if _column_name.endswith("_g")
                    else _column_name
                )
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

                for hash, hash_value in nz_emissions_kg.items():

                    # Get the XYZ indices in Grid3D (em) frame.
                    vvv = self._grid.convertCellHashToXYZIndices(hash)

                    # Drop cells outside the em grid (Grid3D limits).
                    if (
                        (vvv[0] >= self._x_em_meshes)
                        or (vvv[1] >= self._y_em_meshes)
                        or (vvv[2] >= self._z_meshes)
                    ):
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

            # Emission rate in AUSTAL is in g/s (kg x 1000/3600),
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
                return self._ti_endJob()
            except Exception as e:
                logger.error("AUSTAL: Cannot endJob: %s" % e)
                return False

    # Available Substances in AUSTAL
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

    def _ti_split_and_accumulate(self, start_dt, result):
        """Time-indexed routing helper.

        Walks the period_emissions tuples, peels off entries whose
        source has `time_invariant_geometry == True`, accumulates
        their per-pollutant g/s contributions into
        `self._ti_rates_per_source`, caches their cell weights once
        on first encounter via austal_helpers.compute_cell_weights,
        and returns the residual (non-stationary) tuples for the
        per-hour grid file path below to handle.

        Source identity convention: the source's `getName()` (or its
        bare `_id`) is prefixed with `<type>:` to match the schema
        used by `core/tools/sources_df.py` and the helpers'
        `aggregate_sources_by_type`. The type label is derived from
        the source's class name (`RoadwaySources` -> `road`, etc.);
        unknown classes fall through with their bare id, which puts
        them into their own group at aggregation time.

        Returns the list of `(source, [emissions])` tuples that the
        per-hour grid file path should still process. In a pure-
        stationary period this is empty.
        """
        from open_alaqs.core.tools.austal_helpers import (
            KG_PER_HOUR_TO_G_PER_S,
            compute_cell_weights,
        )

        # Lazy: lock in the calendar year on first non-empty call.
        # The plugin's outer loop iterates over a contiguous span; we
        # fix n_hours from the first start_dt and ignore mid-run year
        # changes (multi-year runs already invalidate the per-source
        # activity-vector cache; the same coarse semantics apply here).
        # Run-relative indexing: the first start_dt seen anchors h_idx=0.
        # This avoids reconciliation with the date-normalisation done in
        # the legacy process() body (which shifts series.dmna timestamps
        # to yyyy-01-01.01:00:00 regardless of the actual run start).
        if self._ti_year_start is None:
            year = start_dt.year
            from open_alaqs.core.tools.profiles_vec import hours_in_year

            self._ti_year_start = datetime(year, 1, 1, 0, 0, 0)
            self._ti_n_hours_year = hours_in_year(year)
            self._ti_first_start_dt = start_dt

        h_idx = int((start_dt - self._ti_first_start_dt).total_seconds() // 3600)
        if h_idx < 0 or h_idx >= self._ti_n_hours_year:
            # Out of the indexed window. Fall back to legacy for
            # everything in this period.
            return result

        n_pol = len(self._ti_pollutant_order)
        residual = []

        for source_, emissions__ in result:
            is_stationary = bool(getattr(source_, "time_invariant_geometry", False))
            if not is_stationary:
                residual.append((source_, emissions__))
                continue

            # Build the typed source_id. `<type>:<bare_id>` so the
            # later `aggregate_sources_by_type` groups by class.
            type_label = self._ti_type_label_for(source_)
            bare_id = source_.getName() if hasattr(source_, "getName") else str(source_)
            source_id = f"{type_label}:{bare_id}" if type_label else str(bare_id)

            # Lazy-allocate the rates ndarray for this source.
            if source_id not in self._ti_rates_per_source:
                self._ti_rates_per_source[source_id] = np.zeros(
                    (self._ti_n_hours_year, n_pol), dtype=np.float64
                )
                self._ti_source_meta[source_id] = {
                    "height_m": float(
                        getattr(source_, "getHeight", lambda: 0.0)() or 0.0
                    ),
                    "type_label": type_label,
                }

            # Cache cell weights once per source.
            if (
                source_id not in self._ti_cell_weights
                and source_id not in self._ti_skipped_no_geometry
            ):
                wkt_geom = self._ti_pick_source_wkt(source_, emissions__)
                if wkt_geom:
                    wkt_utm = self._transform_wkt_to_utm(wkt_geom)
                    cw = compute_cell_weights(
                        wkt_utm,
                        self._ti_grid_spec,
                        height_m=self._ti_source_meta[source_id]["height_m"],
                        delta_z_m=0.0,
                    )
                    if cw is None:
                        # Geometry falls outside the grid; skip the
                        # source for this run (no spatial pattern means
                        # no AUSTAL contribution possible).
                        self._ti_skipped_no_geometry.add(source_id)
                    else:
                        self._ti_cell_weights[source_id] = cw

            # Accumulate g/s by pollutant for this hour. The plugin's
            # Emission keys are stored as `<pollutant_lc>_kg`
            # (e.g. 'nox_kg', 'pm10_kg' — kg per hour). Convert with
            # KG_PER_HOUR_TO_G_PER_S = 1000/3600.
            for emission_ in emissions__:
                if emission_ is None or emission_.isZero():
                    continue
                em_obj = emission_.getObjects()
                row = self._ti_rates_per_source[source_id][h_idx]
                for p_idx, pol_name in enumerate(self._ti_pollutant_order):
                    key = f"{pol_name.lower()}_kg"
                    val = em_obj.get(key)
                    if val is None or val == 0:
                        continue
                    row[p_idx] += float(val) * KG_PER_HOUR_TO_G_PER_S

        return residual

    @staticmethod
    def _ti_type_label_for(source_) -> str:
        """Map a Source instance to a short type label matching the
        `core/tools/sources_df.py` convention.

        Uses the class name to keep this independent of any per-source
        attribute. Unknown classes return an empty string; the caller
        treats that as "do not prefix" so the source falls into its
        own bucket at aggregation time.
        """
        cls_name = type(source_).__name__
        return {
            "RoadwaySources": "road",
            "ParkingSources": "parking",
            "PointSources": "point",
            "AreaSources": "area",
        }.get(cls_name, "")

    @staticmethod
    def _ti_pick_source_wkt(source_, emissions__) -> str:
        """Pick the WKT geometry for a stationary source, in the same
        order of preference the legacy process() uses:
        1. The first non-None geometry on the emission objects (these
           include grid-clipping in the Roadway path).
        2. Fall back to the source's own geometry.
        Returns "" when neither is available; the caller treats that
        as 'skip this source for the run'.
        """
        for em in emissions__:
            if em is None:
                continue
            wkt = em.getGeometryText()
            if wkt:
                return wkt
        return source_.getGeometryText() if hasattr(source_, "getGeometryText") else ""

    def _ti_aggregate_stationary(self):
        """Aggregate `_ti_rates_per_source` by `<type>:` prefix.

        Returns
        -------
        group_ids : List[str], sorted
        group_weights : Dict[str, CellWeights]
        group_rates : ndarray (n_hours, n_groups, n_pollutants) g/s

        Sources whose geometry was outside the grid (`_ti_skipped_no_geometry`)
        are excluded from both rates and weights.
        """
        from open_alaqs.core.tools.austal_helpers import aggregate_sources_by_type

        # Stable axis order: alphabetic by source_id. Skip those with no
        # cached weights — they had geometry outside the grid.
        source_ids = sorted(
            sid for sid in self._ti_rates_per_source if sid in self._ti_cell_weights
        )
        if not source_ids:
            n_pol = len(self._ti_pollutant_order)
            return [], {}, np.zeros((self._ti_n_hours_year, 0, n_pol))

        # Pack (n_hours, n_sources, n_pollutants) rates ndarray.
        rates_3d = np.stack(
            [self._ti_rates_per_source[sid] for sid in source_ids], axis=1
        )

        cell_weights = {sid: self._ti_cell_weights[sid] for sid in source_ids}

        return aggregate_sources_by_type(source_ids, cell_weights, rates_3d)

    def _ti_write_stationary_grids(
        self,
        group_ids,
        group_weights,
        dir_offset: int,
    ):
        """Write one eNNNN.dmna per stationary group per simulated
        hour under <output>/<NN>/. Returns dict {group_id:
        dir_index_1based}.

        Each hour's file contains the same time-invariant spatial
        pattern; only t1/t2 differ. AUSTAL 3.3 rejects single-file
        multi-day t1/t2 windows ("current grid source not valid after
        ..."), so we mirror the legacy per-hour layout. The iq column
        in series.dmna for stationary slots therefore counts h_idx+1
        from 1..n_hours (set by writeTimeSeriesFile), pointing at
        eNNNN.dmna identical to legacy non-stationary indexing.

        `dir_offset` is the number of non-stationary AUSTAL sources
        already occupying low-numbered directories; stationary groups
        take dir_offset+1 .. dir_offset+K.
        """
        from datetime import datetime as _dt

        from open_alaqs.core.tools.austal_helpers import (
            expand_to_dense,
            format_time_offset,
            grid_file_header_lines,
            serialise_dense_kji,
        )

        out_dir = self.getOutputPathAsPath()

        # Walk the normalised end-time strings in order; each gives the
        # END of the hour, with the START being one hour earlier.
        sorted_dts = list(self.getSortedResults().keys())
        if not sorted_dts:
            return {}

        # Pre-render the dense body for each group once; the same body
        # is written for every hour (time-invariant spatial pattern).
        # source_offset_cells=0 because _ti_grid_spec is already in
        # em-grid frame (origin = em SW corner). The calc grid halo is
        # only expressed in austal.txt (x0 / nx).
        dense_by_gid = {
            gid: serialise_dense_kji(
                expand_to_dense(
                    group_weights[gid],
                    self._ti_grid_spec,
                    source_offset_cells=0,
                )
            )
            for gid in group_ids
        }

        dir_map = {}
        for offset, gid in enumerate(group_ids, start=1):
            dir_idx = dir_offset + offset
            src_dir = out_dir / f"{dir_idx:02d}"
            src_dir.mkdir(parents=True, exist_ok=True)
            body_lines = dense_by_gid[gid]
            dir_map[gid] = dir_idx

            for h_idx, dt_str in enumerate(sorted_dts, start=1):
                end_dt = _dt.strptime(dt_str, "%Y-%m-%d.%H:%M:%S")
                start_dt = end_dt - timedelta(hours=1)
                ys = _dt(start_dt.year, 1, 1)
                t1 = format_time_offset(start_dt, ys)
                t2 = format_time_offset(end_dt, ys)
                header = grid_file_header_lines(t1, t2, self._ti_grid_spec)

                file_path = src_dir / f"e{h_idx:04d}.dmna"
                with file_path.open("w", newline="\n") as fh:
                    fh.write("\n".join(header) + "\n")
                    fh.write("\n".join(body_lines) + "\n")
                    fh.write("***\n")
        return dir_map

    def writeInputFile(
        self,
        group_ids,
        group_dir_map,
        group_rates,
    ):
        """Hybrid austal.txt: legacy non-stationary AUSTAL sources
        (already in `self._total_sources`) keep their numbering 01..M;
        stationary groups follow at M+1..M+K.

        Per-pollutant emission line has "?" for any AUSTAL source that
        emits that pollutant, "0" otherwise. Stationary group emits
        pollutant p iff group_rates[:, group_idx, p_idx].sum() > 0.
        """
        file_path = self.getOutputPathAsPath() / "austal.txt"
        if file_path.exists():
            raise FileExistsError(file_path)

        legacy_keys = list(self._total_sources.keys())
        n_legacy = len(legacy_keys)
        n_total = n_legacy + len(group_ids)

        # AUSTAL rejects sources with (xq, yq) coincident with (x0, y0).
        # The legacy writer used `x_left_border_em_grid` (no halo); we
        # mirror that for stationary entries too so AUSTAL sees a
        # consistent layout.
        xq = self._x_left_border_em_grid - self._reference_x
        yq = self._y_left_border_em_grid - self._reference_y

        # Per-pollutant active mask for stationary groups
        # (n_groups, n_pollutants): True where group total > 0.
        if group_rates.size > 0:
            stat_mask = group_rates.sum(axis=0) > 0  # (n_groups, n_pol)
        else:
            stat_mask = np.zeros((0, len(self._ti_pollutant_order)), dtype=bool)

        with file_path.open("w") as f:
            f.write("----------------- general parameters\n")
            f.write(f'ti\t"{self._title}"\t\' title\n')
            f.write(f"qs\t{self._quality_level}\t' quality level\n")
            f.write("----------------- meteorology\n")
            f.write(f"z0\t{self._roughness_level}\t' roughness length (m)\n")
            f.write(f"d0\t{self._displacement_height}\t' displacement height (m)\n")
            f.write(f"ha\t{self._anemometer_height}\t' anemometer height (m)\n")
            f.write("----------------- calculation grid\n")
            f.write(f"dd\t{self._mesh_width}\t' mesh width\n")
            f.write(
                f"x0\t{self._x_left_border_calc_grid - self._reference_x}"
                "\t' left border (m)\n"
            )
            f.write(
                f"y0\t{self._y_left_border_calc_grid - self._reference_y}"
                "\t' lower border (m)\n"
            )

            if len(self.xp_) == len(self.yp_) == len(self.zp_) and len(self.xp_) > 0:
                f.write(
                    "xp\t" + "\t".join(str(v) for v in self.xp_) + "\t' x-receptor\n"
                )
                f.write(
                    "yp\t" + "\t".join(str(v) for v in self.yp_) + "\t' y-receptor\n"
                )
                f.write(
                    "hp\t" + "\t".join(str(v) for v in self.zp_) + "\t' z-receptor\n"
                )

            f.write(f"nx\t{self._x_meshes}\t' number of meshes\n")
            f.write(f"ny\t{self._y_meshes}\t' number of meshes\n")
            f.write("----------------- source definitions\n")

            if self._options:
                f.write(f'os\t"{self._options}"\n')

            f.write(
                "iq\t"
                + "\t".join(["?"] * n_total)
                + "\t' file index (set in series.dmna)\n"
            )
            f.write(
                "hq\t"
                + "\t".join([str(self._source_height)] * n_total)
                + "\t' source height (ignored)\n"
            )
            f.write("xq\t" + "\t".join([str(xq)] * n_total) + "\t' x-lower left\n")
            f.write("yq\t" + "\t".join([str(yq)] * n_total) + "\t' y-lower left\n")

            # Per-pollutant lines
            for p_idx, poll in enumerate(self._pollutants_list):
                # Map plugin name to AUSTAL short code
                austal_name = poll
                if poll.startswith("PM"):
                    austal_name = "PM-2" if poll == "PM10" else "PM-1"

                # Legacy non-stationary entries: present iff
                # _total_sources[<NN>] contains this pollutant abbrev.
                legacy_marks = [
                    "?" if austal_name in self._total_sources[k] else "0"
                    for k in legacy_keys
                ]
                # Stationary groups: present iff stat_mask[g, p] is True
                stat_marks = [
                    "?" if (stat_mask.size and stat_mask[g_idx, p_idx]) else "0"
                    for g_idx in range(len(group_ids))
                ]
                f.write(
                    f"{austal_name.lower()}\t"
                    + "\t".join(legacy_marks + stat_marks)
                    + f"\t' total {poll} (in g/s) (set in series.dmna)\n"
                )

    def writeTimeSeriesFile(
        self,
        group_ids,
        group_dir_map,
        group_rates,
    ):
        """Hybrid series.dmna.

        Column layout (legacy non-stationary AUSTAL sources first, then
        stationary groups):
            te ra ua lm [hm]
            <01>.iq ... <NN>.iq        — iq per source per hour
            <01>.<pol> ... <NN>.<pol>  — emission rate per (source, pollutant)
                                         that the source emits

        iq semantics:
          - legacy non-stationary source: timeID counter from
            `_results[<dt>][<src>]['timeID']` (already 1..n_hours per
            the legacy process() path).
          - stationary group: 1 always (only e0001.dmna exists).

        `buff\\t1000000` is added to the header so AUSTAL's DMNA reader
        accepts the long form line that hybrid runs generate.
        """

        file_path = self.getOutputPathAsPath() / "series.dmna"
        if file_path.exists():
            raise FileExistsError(file_path)

        sorted_results = self.getSortedResults()
        sorted_dts = list(sorted_results.keys())

        legacy_keys = list(self._total_sources.keys())
        len(legacy_keys)

        # Total AUSTAL source slots in column order: legacy first, stationary after.
        # `slot_meta[i]` = (kind, key_or_gid, dir_label_str)
        slot_meta = []
        for k in legacy_keys:
            slot_meta.append(("legacy", k, k))  # k is already "01" etc.
        for gid in group_ids:
            slot_meta.append(("stationary", gid, f"{group_dir_map[gid]:02d}"))

        # Active (slot, pollutant) emitters: stationary slots emit
        # pollutant p iff group_rates[:, g_idx, p_idx].sum() > 0;
        # legacy slots emit pollutant p iff p (austal short name) in
        # _total_sources[<NN>].
        if group_rates.size > 0:
            stat_active = group_rates.sum(axis=0) > 0
        else:
            stat_active = np.zeros((0, len(self._ti_pollutant_order)), dtype=bool)

        active_pairs = []  # list of (slot_idx, pol_idx, kind)
        for slot_idx, (kind, key, _label) in enumerate(slot_meta):
            for p_idx, poll in enumerate(self._pollutants_list):
                austal_name = poll
                if poll.startswith("PM"):
                    austal_name = "PM-2" if poll == "PM10" else "PM-1"
                if kind == "legacy":
                    if austal_name in self._total_sources[key]:
                        active_pairs.append((slot_idx, p_idx, "legacy"))
                else:
                    g_idx = group_ids.index(key)
                    if stat_active.size and stat_active[g_idx, p_idx]:
                        active_pairs.append((slot_idx, p_idx, "stationary"))

        # Build form line
        form_parts = ['"te%20lt"', '"ra%5.0f"', '"ua%5.1f"', '"lm%7.1f"']
        if self.MixingHeightIncluded():
            form_parts.append('"hm%7.1f"')
        for kind, _key, label in slot_meta:
            form_parts.append(f'"{label}.iq%3.0f"')
        for slot_idx, p_idx, _kind in active_pairs:
            label = slot_meta[slot_idx][2]
            poll = self._pollutants_list[p_idx]
            austal_name = poll
            if poll.startswith("PM"):
                austal_name = "PM-2" if poll == "PM10" else "PM-1"
            form_parts.append(f'"{label}.{austal_name.lower()}%10.3e"')

        with file_path.open("w") as f:
            f.write("form\t" + "\t".join(form_parts) + "\n")
            f.write('mode\t"text"\n')
            f.write('sequ\t"i"\n')
            f.write("dims\t1\n")
            f.write("lowb\t1\n")
            f.write(f"hghb\t{len(sorted_dts)}\n")
            f.write("buff\t1000000\n")
            f.write("*\n")

            for h_idx, dt_str in enumerate(sorted_dts):
                row_parts = [dt_str]
                row_parts.append(f"{self._series[dt_str]['WindDirection']:5.0f}")
                row_parts.append(f"{self._series[dt_str]['WindSpeed']:5.1f}")
                row_parts.append(f"{self._series[dt_str]['ObukhovLength']:7.1f}")
                if self.MixingHeightIncluded():
                    row_parts.append(f"{self._series[dt_str]['MixingHeight']:7.1f}")

                # iq columns
                for kind, key, _label in slot_meta:
                    if kind == "legacy":
                        # Legacy timeID is already 1-based per source
                        # from the legacy process() path.
                        td = sorted_results[dt_str].get(key, {}).get("timeID", 1)
                        row_parts.append(f"{td:3d}")
                    else:
                        # Stationary slots now also have one e????.dmna
                        # per hour (identical content), so iq counts
                        # h_idx+1 from 1..n_hours, matching the legacy
                        # per-hour layout. AUSTAL 3.3 rejects multi-day
                        # single-file validity windows; this preserves
                        # correctness at the cost of the file-count
                        # optimisation.
                        row_parts.append(f"{h_idx + 1:3d}")

                # Emission columns. group_rates is indexed run-relative
                # (h_idx 0 == first start_dt seen by
                # _ti_split_and_accumulate), matching the loop's
                # enumerate index.
                for slot_idx, p_idx, kind in active_pairs:
                    if kind == "legacy":
                        key = slot_meta[slot_idx][1]
                        poll = self._pollutants_list[p_idx]
                        austal_name = poll
                        if poll.startswith("PM"):
                            austal_name = "PM-2" if poll == "PM10" else "PM-1"
                        val = sorted_results[dt_str].get(key, {}).get(austal_name, 0.0)
                    else:
                        gid = slot_meta[slot_idx][1]
                        g_idx = group_ids.index(gid)
                        if 0 <= h_idx < group_rates.shape[0]:
                            val = float(group_rates[h_idx, g_idx, p_idx])
                        else:
                            val = 0.0
                    row_parts.append(f"{val:10.3e}")

                f.write("\t".join(row_parts) + "\n")

            f.write("\n***\n")

    @log_time
    def _ti_endJob(self):
        """Time-indexed endJob orchestrator. Aggregates stationary
        contributions, writes their grid files, then writes the hybrid
        austal.txt + series.dmna. Per-hour non-stationary grid files
        are already on disk from process().
        """
        if not self.checkTimeIntervalinResults():
            raise Exception("AUSTAL: Time Interval Error")

        group_ids, group_weights, group_rates = self._ti_aggregate_stationary()
        n_legacy = len(self._total_sources)

        try:
            dir_map = self._ti_write_stationary_grids(
                group_ids,
                group_weights,
                dir_offset=n_legacy,
            )
        except Exception as e:
            logger.error("AUSTAL: cannot write stationary grid files: %s", e)
            return False

        try:
            self.writeInputFile(group_ids, dir_map, group_rates)
        except Exception as e:
            logger.error("AUSTAL: cannot write 'austal.txt' (hybrid): %s", e)
            return False

        self.checkHoursinResults()

        try:
            self.writeTimeSeriesFile(group_ids, dir_map, group_rates)
        except Exception as e:
            logger.error("AUSTAL: cannot write 'series.dmna' (hybrid): %s", e)
            return False

        logger.info(
            "AUSTAL time-indexed: %d stationary group(s) + %d non-stationary slot(s) written",
            len(group_ids),
            n_legacy,
        )
        return True

    @log_time
    def _transform_wkt_to_utm(self, wkt: str) -> str:
        """
        Re-project a WKT geometry from EPSG:3857 to the local UTM zone.

        Uses the pyproj Transformer built once in beginJob() via
        shapely.ops.transform instead of constructing a GeoDataFrame, CRS
        object, and full reprojection pipeline from scratch per call.
        """
        from shapely import wkt as shapely_wkt

        geom = _make_valid(shapely_wkt.loads(wkt))
        return _shapely_transform(self._wkt_transformer.transform, geom).wkt

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

        # Transform WKT from EPSG:3857 to UTM so that bbox and efficiency
        # calculations are in the same metric CRS as the Grid3D cell bounds.
        wkt_utm = self._transform_wkt_to_utm(wkt)

        # Determine the bounding box (now in UTM metres)
        bbox = self.getBoundingBox(wkt_utm)

        # Get the vertical extent
        vertical_extent = emissions_.getVerticalExtent()

        # Take into account the effective vertical source extent and shift
        if "delta_z" in vertical_extent and vertical_extent["delta_z"] > 0:
            bbox["z_max"] = bbox["z_max"] + vertical_extent["delta_z"]

        # Get the matched cells for this geometry
        matched_cells = grid.matchBoundingBoxToCellHashList(bbox, z_as_list=True)
        matched_cells_coeff = self.CalculateCellHashEfficiency(
            wkt_utm,  # UTM WKT matches cell bounds CRS
            bbox,
            matched_cells,
            is_point_element_,
            is_line_element_,
            is_polygon_element_,
            is_multi_polygon_element_,
        )

        # Cache by original EPSG:3857 WKT key (as supplied by the caller)
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
