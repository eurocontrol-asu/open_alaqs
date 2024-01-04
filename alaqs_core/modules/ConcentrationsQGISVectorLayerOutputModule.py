import itertools
import os
from collections import OrderedDict
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from PyQt5 import QtWidgets
from qgis.gui import QgsDoubleSpinBox
from shapely.geometry import Point, Polygon

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.interfaces.OutputModule import OutputModule
from open_alaqs.alaqs_core.plotting.ContourPlotVectorLayer import ContourPlotVectorLayer
from open_alaqs.alaqs_core.tools import conversion, sql_interface

logger = get_logger(__name__)


class QGISVectorLayerDispersionModule(OutputModule):
    """
    Module to that returns a QGIS vector layer with representation of
     concentrations.
    """

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
        self._pollutant = (
            values_dict["pollutant"] if "pollutant" in values_dict else None
        )

        self._check_uncertainty = (
            values_dict["check_uncertainty"]
            if "check_uncertainty" in values_dict
            else False
        )

        self._time_start = (
            conversion.convertStringToDateTime(values_dict["Start (incl.)"])
            if "Start (incl.)" in values_dict
            else ""
        )
        self._time_end = (
            conversion.convertStringToDateTime(values_dict["End (incl.)"])
            if "End (incl.)" in values_dict
            else ""
        )
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
        self._isPolygon = values_dict.get(
            "Use Polygons Instead of Points",
            values_dict.get("Shape of Marker: Polygons instead of Points", True),
        )
        self._enable_labels = values_dict.get(
            "Add Labels with Values to Cell Boxes",
            values_dict.get("Add labels with values to cell boxes", False),
        )
        self._3DVisualization = (
            values_dict["3DVisualization"]
            if "3DVisualization" in values_dict
            else False
        )

        self._contour_layer = None
        self._total_concentration = 0.0
        self._threshold_to_create_a_data_point = conversion.convertToFloat(
            values_dict.get("Threshold", values_dict.get("threshold", 0.0001))
        )
        self._grid = values_dict["grid"] if "grid" in values_dict else None

        self.setConfigurationWidget(
            OrderedDict(
                [
                    ("Projection", QtWidgets.QLabel),
                    ("Threshold", QgsDoubleSpinBox),
                    ("Use Polygons Instead of Points", QtWidgets.QCheckBox),
                    ("Add Labels with Values to Cell Boxes", QtWidgets.QCheckBox),
                    ("Add Title", QtWidgets.QCheckBox),
                ]
            )
        )

        widget = self._configuration_widget.getSettings()["Threshold"]
        widget.setDecimals(4)
        widget.setMinimum(0.0)
        widget.setMaximum(999.9999)

        self.getConfigurationWidget().initValues(
            {
                "Use Polygons Instead of Points": True,
                "Add Labels with Values to Cell Boxes": False,
                "Projection": "EPSG:3857",
                "Threshold": 0.0001,
                "Add Title": True,
            }
        )

        self._header = []

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

    def addDataPoint(self, grid, cell_hash, data_point):
        # strip z coordinates if 2D visualization, i.e. integrate over z axis
        if not self._3DVisualization:
            cell_hash = self.getGrid().stripZCoordinateFromCellHash(cell_hash)
        else:
            cell_hash = cell_hash[:]

        # skip data points if all emissions are smaller than threshold
        if not sum(
            [
                abs(data_point["attributes"][attribute])
                > self.getThresholdToCreateDataPoint()
                for attribute in data_point["attributes"]
            ]
        ):
            logger.info(
                "addDataPoint: Skip data point (%s) with value '%s' due to threshold (%s and of type '%s')."
                % (
                    str(data_point),
                    str(
                        sum(
                            [
                                abs(data_point["attributes"][attribute])
                                for attribute in data_point["attributes"]
                            ]
                        )
                    ),
                    str(self.getThresholdToCreateDataPoint()),
                    str(type(self.getThresholdToCreateDataPoint())),
                )
            )
            return

        # store each grid point only once, otherwise add cell contents
        if not cell_hash in self._data:
            self._data[cell_hash] = data_point
        else:
            for attribute in data_point["attributes"]:
                if attribute in self._data[cell_hash]["attributes"]:
                    # logger.debug("attribute '%s' already in data" % (data_point["attributes"][attribute]))
                    # self._data[cell_hash]["attributes"][attribute]+= data_point["attributes"][attribute]
                    pass
                else:
                    self._data[cell_hash]["attributes"][attribute] = data_point[
                        "attributes"
                    ][attribute]

    # def getBoundingBox(self, geometry_wkt):
    #     bbox = Spatial.getBoundingBox(geometry_wkt)
    #     return bbox

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
                    "AUSTAL2000: Could not reset reference point as coordinates could not be transformed. The query was\n'%s'"
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

            user_set_factor = (
                1.0  # ToDo: Enlarge Calculation Grid by Factor set by the user
            )
            self._x_left_border_grid = float(grid_origin_x) - user_set_factor * float(
                self._grid._x_resolution
            )
            self._y_left_border_grid = float(grid_origin_y) - user_set_factor * float(
                self._grid._y_resolution
            )

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

        except:
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
            with open(datapath, encoding="utf8", errors="ignore") as f:
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

    def beginJob(self):
        try:
            if self._pollutant.startswith("PM"):
                self._pollutant = "PM"

            # prepare the attributes of each point of the vector layer
            self._data = {}
            # ToDO: self._grid.get_df_from_3d_grid_cells() ?
            self._data_cells = self._grid.get_df_from_2d_grid_cells()
            self._data_cells = self._data_cells.assign(
                Q=pd.Series(0, index=self._data_cells.index)
            )

            self._total_concentration = 0.0

            output_data, index_, concentration_matrix = self.getA2KData()

            self._header = [(self._pollutant, "double")]

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

            # self._units = output_data['unit'][0].decode('latin-1') if ('unit' in output_data and len(output_data['unit']) > 0) else None
            self._units = (
                output_data["unit"][0]
                if ("unit" in output_data and len(output_data["unit"]) > 0)
                else None
            )

            self._index_i = (
                conversion.convertToInt(output_data["hghb"][0])
                if ("hghb" in output_data and len(output_data["hghb"]) > 0)
                else None
            )  # columns
            self._index_j = (
                conversion.convertToInt(output_data["hghb"][1])
                if ("hghb" in output_data and len(output_data["hghb"]) > 0)
                else None
            )  # rows
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
                logger.error(
                    "Error in reshaping concentration matrix: (%s, %s, %s)"
                    % (self._index_k, self._index_i, self._index_j)
                )
                return False

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
                # take the concentration up tp Kmax: <c> = c1*H1/(H1+H2+H3+...) + c2*H2/(H1+H2+H3+...) + c3*H3/(H1+H2+H3+...) + ...
                total_column_concentration = np.zeros(
                    shape=(self._index_j, self._index_i)
                )
                for z_ in range(1, self._index_k + 1):
                    total_column_concentration += (
                        conversion.convertToFloat(output_data["sk"][z_])
                        * concentration_matrix_reshaped[z_ - 1, :, :].squeeze()
                    ) / conversion.convertToFloat(output_data["sk"][self._index_k])
                self._concentration_matrix = total_column_concentration

            return True

        except Exception as e:
            logger.error(
                "ConcentrationsQGISVectorLayerOutputModule: Cannot complete beginJob: %s"
                % e
            )
            return False

    def process(self, **kwargs):
        # Details of the projection
        pass

        if self.getGrid() is None:
            raise Exception("No 3DGrid found.")

        self.getGridXYFromReferencePoint()
        x0 = self._x_left_border_grid
        y0 = self._y_left_border_grid
        # logger.debug("getGridXYFromReferencePoint(x0, y0): %s,%s"%(x0, y0))

        # ToDo: User defined vertical layer (Zmin, Zmax)?
        Zmax = 0
        # try:
        #     Zmax = conversion.convertToFloat(self._sk[self._index_k])
        #     logger.info("Maximum height: %s"%Zmax)
        # except:
        #     Zmax = 0

        conc_value_counter = 0
        for y, x in itertools.product(
            *list(map(range, (self._index_j, self._index_i)))
        ):
            # sequence is k+,j-,i+
            conc_value = self._concentration_matrix[self._index_j - (y + 1), x]

            # ToDo: take into account the z level: self._index_k ?
            bbox = {
                "y_min": y0 + (y) * self._delta,
                "y_max": y0 + (y) * self._delta,
                "x_min": x0 + (x) * self._delta,
                "x_max": x0 + (x) * self._delta,
                "z_max": Zmax,
                "z_min": 0,
            }

            # ToDo: convert bbox to geom object ?
            geom = Point(
                x0 + (x) * self._delta + self._delta * 1.0 / 2,
                y0 + (y) * self._delta + self._delta * 1.0 / 2,
            )
            # logger.info(geom)

            self.addToTotalConcentration(conc_value)

            if conc_value >= self._threshold_to_create_a_data_point:
                conc_value_counter += conc_value

                # include z limitations if any
                # bbox["z_min"] = self.getMinHeight()
                # bbox["z_max"] = self.getMaxHeight()

                # match bounding box to cell hashes
                # matched_cells = []

                # project all z components to zero, i.e. integrate over height
                # matched_cells = self.getGrid().matchBoundingBoxToCellHashList(bbox, z_as_list=True)
                # logger.info(matched_cells)

                matched_cells_2D = self._data_cells[
                    self._data_cells.contains(geom) == True
                ]

                # Calculate horizontal distribution
                # matched_cells_2D.loc[matched_cells_2D.index, "Concentration"] = \
                #     conc_value * matched_cells_2D.intersection(geom).area / geom.area
                self._data_cells.loc[matched_cells_2D.index, "Q"] += conc_value

                # # logger.info(matched_cells_2D.head())
                # # ToDo: Add conc to self._data_cells
                #
                # # z_min = bbox["z_min"]
                # # z_max = bbox["z_max"]
                #
                # for xy_rect in matched_cells:
                #     if not xy_rect:
                #         logger.info("No matched_cells (%s) for Bbox: %s ? "%(xy_rect, bbox))
                #         continue
                #
                #     z_count = 0
                #     for index_height_level, cell_hash in enumerate(xy_rect):
                #
                #         if z_count == 0:
                #             x_,y_,z_ = 0.,0.,0.
                #             (x_,y_,z_) = self.getGrid().convertCellHashListToCenterGridCellCoordinates([cell_hash])[cell_hash]
                #
                #             # cell_bbox = self.getCellBox(x_,y_,z_, self.getGrid())
                #             data_point_ = self.getDataPoint(x_, y_, z_, self._isPolygon, self.getGrid())
                #
                #             #write the emission values to the data point
                #             data_point_.update({"attributes":{self._pollutant: conc_value}})
                #
                #             #save the data point in memory
                #             self.addDataPoint(self.getGrid(), cell_hash, data_point_)
                #
                #             z_count = 1
                #         else:
                #             z_count = 0

        if round(conc_value_counter, 3) < round(self._total_concentration, 3):
            logger.warning(
                "A2K: Sum of all grid cells is < %s > rather than expected (%s)"
                "The grid is most probably too small."
                % (conc_value_counter, self._total_concentration)
            )

    def endJob(self):
        # create the layer
        # if self._header and self._data:
        # if self._header and not self._data.empty:
        if self._header and not self._data_cells.empty:

            # create a new instance of a ContourPlotLayer
            contour_layer = ContourPlotVectorLayer(
                {
                    "isPolygon": self._isPolygon,
                    "Label_enable": self._enable_labels,
                    "fieldname": self._pollutant,
                    "name": "Concentration [in %s]" % (self._units),
                    "name_suffix": self._layer_name_suffix,
                }
            )
            contour_layer.addHeader(self._header)

            # contour_layer.addData([self._data[k] for k in self._data.keys()])
            # contour_layer_min = min([self._data[k]["attributes"][self._pollutant] for k in self._data.keys()])
            # contour_layer_max = max([self._data[k]["attributes"][self._pollutant] for k in self._data.keys()])

            contour_layer.addData(self._data_cells)
            contour_layer_min = np.floor(self._data_cells.Q.min())
            contour_layer_max = np.ceil(self._data_cells.Q.max())

            contour_layer.setColorGradientRenderer(
                {
                    "numberOfClasses": 7,
                    "color1": "white",
                    "color2": "red",
                    "fieldname": self._pollutant,
                    "minValue": contour_layer_min,
                    "maxValue": contour_layer_max,
                }
            )

            # logger.debug("Adding: fieldname:%s, minValue:%s, maxValue:%s"%(self._pollutant, contour_layer_min, contour_layer_max) )
            self._contour_layer = contour_layer
            return self._contour_layer.getLayer()

        logger.warning("Could not complete endJob for QGISVectorLayerDispersionModule")
        return None
