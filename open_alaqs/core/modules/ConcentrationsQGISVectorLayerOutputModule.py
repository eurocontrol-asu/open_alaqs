import os
from collections import OrderedDict
from datetime import datetime, timedelta

import geopandas as gpd
import numpy as np
import pandas as pd
from qgis.gui import QgsDoubleSpinBox
from qgis.PyQt import QtWidgets
from shapely.geometry import Polygon

from open_alaqs.alaqs_config import DEFAULT_CONCENTRATION_GRID_FACTOR
from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.OutputModule import OutputModule
from open_alaqs.core.plotting.ContourPlotVectorLayer import \
    ContourPlotVectorLayer
from open_alaqs.core.tools import conversion, sql_interface

logger = get_logger(__name__)


class QGISVectorLayerDispersionModule(OutputModule):
    """
    Module to that returns a QGIS vector layer with representation of
     concentrations.
    """

    settings_schema = {
        "projection": {
            "label": "Projection",
            "widget_type": QtWidgets.QLabel,
            "initial_value": "EPSG:3857",
        },
        "threshold": {
            "label": "Threshold",
            "widget_type": QgsDoubleSpinBox,
            "initial_value": 0.0001,
            "widget_config": {
                "minimum": 0,
                "maximum": 999.9999,
                "decimals": 10,
            },
        },
        "use_centroid_symbol": {
            "label": "Show Centroid Symbols Instead of Polygons",
            "widget_type": QtWidgets.QCheckBox,
            "initial_value": False,
        },
        "should_add_labels": {
            "label": "Add Labels with Values to Cell Boxes",
            "widget_type": QtWidgets.QCheckBox,
            "initial_value": False,
        },
        "should_add_title": {
            "label": "Add Title",
            "widget_type": QtWidgets.QCheckBox,
            "initial_value": True,
        },
    }

    @staticmethod
    def getModuleName():
        return "QGISVectorLayerDispersionModule"

    @staticmethod
    def getModuleDisplayName():
        return "Vector Layer"

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        OutputModule.__init__(self, values_dict)

        # Layer configuration
        self._options = values_dict["options"] if "options" in values_dict else ""

        # Results analysis
        self._averaging_period = (
            values_dict["averaging_period"]
            if "averaging_period" in values_dict
            else "annual mean"
        )
        self._pollutant: str | None = (
            values_dict["pollutant"] if "pollutant" in values_dict else None
        )

        self._check_uncertainty = (
            values_dict["check_uncertainty"]
            if "check_uncertainty" in values_dict
            else False
        )

        self._time_start = values_dict["start_dt_inclusive"]
        self._time_end = values_dict["end_dt_inclusive"]

        self._timeseries = (
            values_dict["timeseries"] if "timeseries" in values_dict else None
        )

        self._concentration_database = (
            values_dict["concentration_path"]
            if "concentration_path" in values_dict
            else None
        )

        self._layer_name = ContourPlotVectorLayer.LAYER_NAME
        self._layer_name_suffix = (
            values_dict["name_suffix"] if "name_suffix" in values_dict else ""
        )
        self._use_centroid_symbol = values_dict["use_centroid_symbol"]
        self._enable_labels = values_dict.get("should_add_labels", False)
        self._3DVisualization = (
            values_dict["3DVisualization"]
            if "3DVisualization" in values_dict
            else False
        )

        self._contour_layer = None
        self._total_concentration = 0.0
        self._threshold_to_create_a_data_point = conversion.convertToFloat(
            values_dict.get("threshold", 0.0001)
        )
        self._grid = values_dict["grid"] if "grid" in values_dict else None

    def getGrid(self):
        return self._grid

    def setGrid(self, var):
        self._grid = var

    def getMinHeight(self):
        return self._min_height_in_m

    def setMinHeight(self, var, inFeet=False):
        if inFeet:
            self._min_height_in_m = conversion.convertFeetToMeters(var)
        else:
            self._min_height_in_m = var

    def getMaxHeight(self):
        return self._max_height_in_m

    def setMaxHeight(self, var, inFeet=False):
        if inFeet:
            self._max_height_in_m = conversion.convertFeetToMeters(var)
        else:
            self._max_height_in_m = var

    def getThresholdToCreateDataPoint(self):
        return self._threshold_to_create_a_data_point

    def setThresholdToCreateDataPoint(self, var):
        self._threshold_to_create_a_data_point = var

    def getTimeStart(self):
        return self._time_start

    def getTimeEnd(self):
        return self._time_end

    def getPollutant(self):
        return self._pollutant

    def getContourLayer(self):
        return self._contour_layer

    def getTotalConcentration(self):
        return self._total_concentration

    def addToTotalConcentration(self, var):
        self._total_concentration += var

    def getDataPoint(self, x_, y_, z_, isPolygon, grid_):
        data_point_ = {"coordinates": {"x": x_, "y": y_, "z": z_}}
        if isPolygon:
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

    def polygonize_bbox(self, box_):
        return Polygon(
            [
                (box_["x_min"], box_["y_min"]),
                (box_["x_max"], box_["y_min"]),
                (box_["x_max"], box_["y_max"]),
                (box_["x_min"], box_["y_max"]),
            ]
        )

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
            # Convert the ARP into EPSG 3857
            sql_text = (
                "SELECT X(ST_Transform(ST_PointFromText('%s', 4326), 3857)), Y(ST_Transform(ST_PointFromText('%s', 4326), 3857));"
                % (reference_point_wkt, reference_point_wkt)
            )
            result = sql_interface.query_text(self._grid._db_path, sql_text)
            if result is None:
                raise Exception(
                    "AUSTAL: Could not reset reference point as coordinates could not be transformed. The query was\n'%s'"
                    % (sql_text)
                )
                return None

            self._reference_x = conversion.convertToFloat(result[0][0])
            self._reference_y = conversion.convertToFloat(result[0][1])
            self._reference_z = self._grid._reference_altitude

            # Calculate the coordinates of the bottom left of the grid
            grid_origin_x = float(self._reference_x) - (
                float(self._grid._x_cells) / 2.0
            ) * float(self._grid._x_resolution)
            grid_origin_y = float(self._reference_y) - (
                float(self._grid._y_cells) / 2.0
            ) * float(self._grid._y_resolution)

            self._x_left_border_grid = float(
                grid_origin_x
            ) - DEFAULT_CONCENTRATION_GRID_FACTOR * float(self._grid._x_resolution)
            self._y_left_border_grid = float(
                grid_origin_y
            ) - DEFAULT_CONCENTRATION_GRID_FACTOR * float(self._grid._y_resolution)

            return True
        except Exception as e:
            logger.error(
                "ConcentrationsQGISVectorLayerOutputModule: Could not reset 3D grid origin from reference point: %s"
                % e
            )
            return False

    def getCellBox(self, x_, y_, z_, grid_):
        cell_bbox = {
            "x_min": x_ - grid_.getResolutionX() / 2.0,
            "x_max": x_ + grid_.getResolutionX() / 2.0,
            "y_min": y_ - grid_.getResolutionY() / 2.0,
            "y_max": y_ + grid_.getResolutionY() / 2.0,
            "z_min": z_ - grid_.getResolutionZ() / 2.0,
            "z_max": z_ + grid_.getResolutionZ() / 2.0,
        }
        return cell_bbox

    def assure_time_interval(self, output_data):
        try:  # convert t1, t2 to dates and check timedelta
            t1, t2, t0 = (
                output_data["t1"][0],
                output_data["t2"][0],
                output_data["rdat"][0],
            )

            # reconstruct actual date
            start_date = datetime.strptime(t0, "%Y-%m-%d.%H:%M:%S")

            t1_day = conversion.convertToInt(t1.split(".")[0]) if ("." in t1) else 0
            t2_day = conversion.convertToInt(t2.split(".")[0]) if ("." in t2) else 0

            t1_hour = (
                datetime.strptime(t1.split(".")[1], "%H:%M:%S").replace(
                    year=start_date.year
                )
                if ("." in t1)
                else datetime.strptime(t1, "%H:%M:%S").replace(year=start_date.year)
            )

            t2_hour = (
                datetime.strptime(t2.split(".")[1], "%H:%M:%S").replace(
                    year=start_date.year
                )
                if ("." in t2)
                else datetime.strptime(t2, "%H:%M:%S").replace(year=start_date.year)
            )

            if self._averaging_period == "daily mean":
                start_time = start_date + timedelta(days=t1_day)
                end_time = start_date + timedelta(days=t2_day)
                tdelta = end_time - start_time

                if tdelta.total_seconds() == 86400.0:
                    return True
                else:
                    logger.debug(
                        "Error in timedelta for daily mean: (start: %s, end:%s, timedelta: %s)"
                        % (t1, t2, tdelta)
                    )
                return False

            if (
                self._averaging_period == "hourly"
                or self._averaging_period == "8-hours mean"
            ):
                # timedelta should be 1h
                tdelta = t2_hour - t1_hour
                if tdelta.total_seconds() == 3600.0:
                    return True
                else:
                    logger.debug(
                        "Error in timedelta for hourly mean: (start: %s, end:%s, timedelta: %s)"
                        % (start_time, end_time, tdelta)
                    )
                return False

        except Exception:
            logger.debug("Error in timedelta: (t1: %s, t2:%s, t0: %s)" % (t1, t2, t0))
            return False

    # def assert_validity(self, avg_period="annual mean"):
    #     required_proportion = 0.90 if avg_period == "annual mean" else 0.75
    #     if np.count_nonzero(self._data_y) < required_proportion * len(self._data_y) :
    #         logger.error("Required proportion of valid data is not enough!")

    def readA2Koutput(self, datapath):
        if not os.path.isfile(datapath):
            QtWidgets.QMessageBox.warning(
                None,
                "File not found",
                "File '%s' not found. Choose another pollutant ? " % (datapath),
            )
        try:
            # latin-1 read the units ug/m3, utf-8 reads u/g
            # with open(datapath, encoding="utf-8", errors="ignore") as f:
            with open(datapath, encoding="latin-1", errors="ignore") as f:
                raw_output_data = [
                    x.rstrip("\n").lstrip().replace('"', "") for x in f.readlines()
                ]

            output_data = OrderedDict()
            cnt = 0
            for content in raw_output_data:
                cnt += +1
                if content.split() and "*" not in content.split()[0]:
                    output_data[content.split()[0]] = content.split()[1:]
                elif content.split() and "*" in content.split()[0]:
                    break

            index_ = raw_output_data.index("*")
            # concentration_matrix = np.loadtxt(datapath, comments="*", skiprows=index_)
            concentration_matrix = np.loadtxt(
                raw_output_data, comments="*", skiprows=index_
            )

            return output_data, index_, concentration_matrix

        except Exception as exc_:
            logger.error(exc_)
            return OrderedDict(), None, None

    def getA2KData(self):

        try:
            if self._averaging_period == "annual mean":
                output_file = (
                    os.path.join(
                        self._concentration_database,
                        "%s-y00a.dmna" % self._pollutant.lower(),
                    )
                    if not self._check_uncertainty
                    else os.path.join(
                        self._concentration_database,
                        "%s-y00s.dmna" % self._pollutant.lower(),
                    )
                )
                return self.readA2Koutput(output_file)

            else:
                conc = OrderedDict()
                time_counter = 0
                # Ensure that the user defined time period is within limits
                if (self._time_start < self._timeseries[0]) or (
                    self._time_end > self._timeseries[-1]
                ):
                    QtWidgets.QMessageBox.warning(
                        None,
                        "Error in time period",
                        "Please select a time period between %s and %s"
                        % (self._timeseries[0], self._timeseries[-1]),
                    )

                # Select the appropriate files according to self._time_start, self._time_end (e.g. co-001a.dmna to co-007a.dmna)
                # timedelta_from_start = (self._timeseries[0] - self._timeseries[0].replace(month=1, day=1, hour=0, minute=0, second=0))
                dt_from_time_start = self._time_start - self._timeseries[0]
                dt_from_time_end = self._time_end - self._timeseries[0]

                if self._averaging_period == "daily mean":
                    # while time_counter < (self._time_end - self._time_start).days:
                    for time_counter in range(
                        dt_from_time_start.days, dt_from_time_end.days + 1
                    ):
                        time_counter += +1

                        output_file = (
                            os.path.join(
                                self._concentration_database,
                                "%s-%sa.dmna"
                                % (self._pollutant.lower(), str(time_counter).zfill(3)),
                            )
                            if not self._check_uncertainty
                            else os.path.join(
                                self._concentration_database,
                                "%s-%ss.dmna"
                                % (self._pollutant.lower(), str(time_counter).zfill(3)),
                            )
                        )

                        output_data, index_, concentration_matrix = self.readA2Koutput(
                            output_file
                        )
                        if not self.assure_time_interval(output_data):
                            raise Exception(
                                "Error in timedelta. Choose another averaging period for time interval (%s, %s)"
                                % (output_data["t1"], output_data["t2"])
                            )
                        conc[str(time_counter).zfill(3)] = concentration_matrix
                    return (
                        output_data,
                        index_,
                        np.array(list(conc.values())).mean(axis=0),
                    )
                    # ToDo: Add max ?

                else:  # hourly (1h, 8h, whatever ..)
                    if self._averaging_period == "hourly":
                        for time_counter in range(
                            int(dt_from_time_start.total_seconds() / 3600),
                            int(dt_from_time_end.total_seconds() / 3600),
                        ):
                            time_counter += +1

                            output_file = (
                                os.path.join(
                                    self._concentration_database,
                                    "%s-%sa.dmna"
                                    % (
                                        self._pollutant.lower(),
                                        str(time_counter).zfill(3),
                                    ),
                                )
                                if not self._check_uncertainty
                                else os.path.join(
                                    self._concentration_database,
                                    "%s-%ss.dmna"
                                    % (
                                        self._pollutant.lower(),
                                        str(time_counter).zfill(3),
                                    ),
                                )
                            )
                            if not os.path.isfile(output_file):
                                logger.warning("File %s doesn't exist!" % output_file)
                                continue
                            else:
                                (
                                    output_data,
                                    index_,
                                    concentration_matrix,
                                ) = self.readA2Koutput(output_file)
                                if not self.assure_time_interval(output_data):
                                    raise Exception(
                                        "Error in timedelta. Choose another averaging period for time interval (%s, %s)"
                                        % (output_data["t1"], output_data["t2"])
                                    )
                                conc[str(time_counter).zfill(3)] = concentration_matrix

                    elif self._averaging_period == "8-hours mean":
                        QtWidgets.QMessageBox.information(
                            None,
                            "8-hours mean",
                            "For time interval: %s (+8h)" % (self._time_start),
                        )

                        for time_counter in range(
                            int(dt_from_time_start.total_seconds() / 3600),
                            int(dt_from_time_start.total_seconds() / 3600) + 8,
                        ):
                            time_counter += +1

                            output_file = (
                                os.path.join(
                                    self._concentration_database,
                                    "%s-%sa.dmna"
                                    % (
                                        self._pollutant.lower(),
                                        str(time_counter).zfill(3),
                                    ),
                                )
                                if not self._check_uncertainty
                                else os.path.join(
                                    self._concentration_database,
                                    "%s-%ss.dmna"
                                    % (
                                        self._pollutant.lower(),
                                        str(time_counter).zfill(3),
                                    ),
                                )
                            )
                            if not os.path.isfile(output_file):
                                logger.warning("File %s doesn't exist!" % output_file)
                                continue
                            else:
                                (
                                    output_data,
                                    index_,
                                    concentration_matrix,
                                ) = self.readA2Koutput(output_file)
                                if not self.assure_time_interval(output_data):
                                    raise Exception(
                                        "Error in timedelta. Choose another averaging period for time interval (%s, %s)"
                                        % (output_data["t1"], output_data["t2"])
                                    )
                                conc[str(time_counter).zfill(3)] = concentration_matrix

                    return (
                        output_data,
                        index_,
                        np.array(list(conc.values())).mean(axis=0),
                    )

        except Exception as e:
            logger.error("A2K OutputModule: Cannot fetch data: %s" % e)
            # Ensure it always return a 3-tuple to avoid unpacking errors in callers
            try:
                empty_matrix = np.array([])
            except Exception:
                empty_matrix = []
            return OrderedDict(), None, empty_matrix

    def beginJob(self):
        if self._pollutant.startswith("PM"):
            self._pollutant = "PM"

        # prepare the attributes of each point of the vector layer
        self._data = {}

        self._total_concentration = 0.0

        # Read y00a (header + matrix) FIRST. The data_cells frame is
        # then constructed from the y00a header so that polygons are
        # exactly aligned with the AUSTAL output grid, regardless of
        # how the .alaqs DB grid is configured. This avoids the
        # one-row spatial offset that occurs when the writer's calc
        # grid origin (e.g. standalone with x0=-9375) differs from
        # the reader's assumed origin (QGIS plugin convention with
        # halo: x0=-9875).
        output_data, index_, concentration_matrix = self.getA2KData()

        self._xmin = (
            conversion.convertToFloat(output_data["xmin"][0])
            if ("xmin" in output_data and len(output_data["xmin"]) > 0)
            else None
        )
        self._ymin = (
            conversion.convertToFloat(output_data["ymin"][0])
            if ("ymin" in output_data and len(output_data["ymin"]) > 0)
            else None
        )
        self._delta = (
            conversion.convertToFloat(output_data["delta"][0])
            if ("delta" in output_data and len(output_data["delta"]) > 0)
            else None
        )
        self._sk = (
            output_data["sk"]
            if ("sk" in output_data and len(output_data["sk"]) > 0)
            else None
        )

        self._units = (
            output_data["unit"][0]
            if ("unit" in output_data and len(output_data["unit"]) > 0)
            else None
        )

        self._index_i = (
            conversion.convertToInt(output_data["hghb"][0])
            if ("hghb" in output_data and len(output_data["hghb"]) > 0)
            else None
        )  # columns (i, x)
        self._index_j = (
            conversion.convertToInt(output_data["hghb"][1])
            if ("hghb" in output_data and len(output_data["hghb"]) > 0)
            else None
        )  # rows (j, y)
        self._index_k = (
            conversion.convertToInt(output_data["hghb"][2])
            if ("hghb" in output_data and len(output_data["hghb"]) > 0)
            else None
        )  # z

        if not (
            self._index_k
            and self._index_i
            and self._index_j
            and len(concentration_matrix) > 0
        ):
            raise Exception(
                "Error in reshaping concentration matrix: (%s, %s, %s)"
                % (self._index_k, self._index_i, self._index_j)
            )

        # Build data_cells in UTM, aligned with the y00a grid. This
        # replaces the prior approach of building from .alaqs DB grid
        # (centered, no halo) and projecting to EPSG:3857 with raw
        # 250 m steps. Working in UTM throughout means each data_cell
        # corresponds 1:1 to one y00a cell, and direct array
        # assignment in process() is exact.
        utm_epsg = self._grid.getUtmEpsg()
        ref_lon = float(self._grid._reference_longitude)
        ref_lat = float(self._grid._reference_latitude)
        ref_wkt = "POINT (%s %s)" % (ref_lon, ref_lat)
        sql_text = (
            "SELECT X(ST_Transform(ST_PointFromText('%s', 4326), %d)), "
            "Y(ST_Transform(ST_PointFromText('%s', 4326), %d));"
            % (ref_wkt, utm_epsg, ref_wkt, utm_epsg)
        )
        ref_result = sql_interface.query_text(self._grid._db_path, sql_text)
        if ref_result is None:
            raise Exception(
                "AUSTAL: Could not transform reference point to UTM "
                "for data_cells construction."
            )
        self._reference_x = conversion.convertToFloat(ref_result[0][0])
        self._reference_y = conversion.convertToFloat(ref_result[0][1])

        # Absolute UTM SW corner of the y00a calc grid.
        self._x_left_border_grid = self._reference_x + self._xmin
        self._y_left_border_grid = self._reference_y + self._ymin

        rows = []
        for x_idx in range(self._index_i):
            x_min_cell = self._x_left_border_grid + x_idx * self._delta
            x_max_cell = x_min_cell + self._delta
            for y_idx in range(self._index_j):
                y_min_cell = self._y_left_border_grid + y_idx * self._delta
                y_max_cell = y_min_cell + self._delta
                rows.append(
                    {
                        "x_idx": x_idx,
                        "y_idx": y_idx,
                        "geometry": Polygon(
                            [
                                (x_min_cell, y_min_cell),
                                (x_min_cell, y_max_cell),
                                (x_max_cell, y_max_cell),
                                (x_max_cell, y_min_cell),
                            ]
                        ),
                    }
                )

        self._data_cells = gpd.GeoDataFrame(
            rows, geometry="geometry", crs=f"EPSG:{utm_epsg}"
        )
        self._data_cells = self._data_cells.assign(
            Q=pd.Series(0, index=self._data_cells.index)
        )
        # Initialize the pollutant column to 0 so process() can do
        # `self._data_cells.loc[..., col] = value` without KeyError.
        self._data_cells[f"{self._pollutant}_kg"] = 0.0

        concentration_matrix_reshaped = np.reshape(
            concentration_matrix, (self._index_k, self._index_j, self._index_i)
        )

        # By default, show the height interval 0m to 3m (the lowest layer)
        # The result files contain the layers k=1...Kmax
        if self._check_uncertainty:  # take only first level for uncertainty
            self._concentration_matrix = concentration_matrix_reshaped[
                0, :, :
            ].squeeze()
        else:
            # take the concentration up to Kmax: <c> = c1*H1/(H1+H2+H3+...) + ...
            total_column_concentration = np.zeros(shape=(self._index_j, self._index_i))
            for z_ in range(1, self._index_k + 1):
                total_column_concentration += (
                    conversion.convertToFloat(output_data["sk"][z_])
                    * concentration_matrix_reshaped[z_ - 1, :, :].squeeze()
                ) / conversion.convertToFloat(output_data["sk"][self._index_k])
            self._concentration_matrix = total_column_concentration

        return True

    def process(self, **kwargs):
        if self.getGrid() is None:
            raise Exception("No 3DGrid found.")

        # Direct array assignment, in UTM index space.
        #
        # The data_cells frame was constructed in beginJob() so that
        # row k = x_idx * n_y + y_idx corresponds to the polygon
        # at AUSTAL grid index (x_idx, y_idx). y_idx = 0 is the
        # south-most cell. The y00a matrix is laid out per the DMNA
        # k+,j-,i+ convention: matrix row 0 is j_phys = J_max
        # (north-most), matrix row n_y - 1 is j_phys = 1 (south-most).
        # For y_idx (south-counted) we therefore read matrix row
        # n_y - 1 - y_idx.
        #
        # No Point geometry, no contains() check, no aggregation:
        # one y00a value goes into exactly one data_cell.
        col = f"{self._pollutant}_kg"
        conc_value_counter = 0.0
        n_y = self._index_j
        n_x = self._index_i

        for x_idx in range(n_x):
            base = x_idx * n_y
            for y_idx in range(n_y):
                conc_value = self._concentration_matrix[n_y - 1 - y_idx, x_idx]
                self.addToTotalConcentration(conc_value)

                if conc_value >= self._threshold_to_create_a_data_point:
                    conc_value_counter += conc_value
                    self._data_cells.at[base + y_idx, col] = conc_value

        if round(conc_value_counter, 3) < round(self._total_concentration, 3):
            logger.warning(
                "A2K: Sum of all grid cells is < %s > rather than expected (%s)"
                "The grid is most probably too small."
                % (conc_value_counter, self._total_concentration)
            )

    def endJob(self):
        if not self._data_cells.empty:
            # data_cells is built in UTM. Keep it in UTM for the output
            # layer so cells render as true 250 m squares (no cos(lat)
            # distortion) and overlay exactly with the emissions raster
            # which is also output in UTM.
            utm_epsg = self._grid.getUtmEpsg()

            # create a new instance of a ContourPlotLayer
            contour_layer = ContourPlotVectorLayer(
                layer_name="Concentration [in {}] {}".format(
                    self._units, self._layer_name_suffix
                ),
                enable_labels=self._enable_labels,
                field_name=self._pollutant,
                use_centroid_symbol=self._use_centroid_symbol,
                epsg=utm_epsg,
            )

            contour_layer.addData(self._data_cells)
            contour_layer.setColorGradientRenderer(classes_count=7)

            self._contour_layer = contour_layer

            return self._contour_layer.layer

        logger.warning("Could not complete endJob for QGISVectorLayerDispersionModule")
        return None
