import logging
from collections import OrderedDict

import matplotlib
import pandas as pd
from matplotlib.dates import DateFormatter
from PyQt5 import QtWidgets
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.interfaces.OutputModule import OutputModule
from open_alaqs.alaqs_core.plotting.MatplotlibQtDialog import MatplotlibQtDialog
from open_alaqs.alaqs_core.tools import conversion

logging.getLogger("matplotlib").setLevel(logging.ERROR)
matplotlib.use("Qt5Agg")

logger = get_logger(__name__)


class TimeSeriesWidgetOutputModule(OutputModule):
    """
    Module to plot a timeseries of the emission calculation
    """

    @staticmethod
    def getModuleName():
        return "TimeSeriesWidgetOutputModule"

    @staticmethod
    def getModuleDisplayName():
        return "Time Series"

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        OutputModule.__init__(self, values_dict)

        # Widget configuration
        self._parent = values_dict.get("parent")
        self._widget = None

        # Plot configuration
        self._title = values_dict.get("title", "")
        self._xtitle = values_dict.get("X-Axis Title", values_dict.get("xtitle", ""))
        self._ytitle = values_dict.get("ytitle", "")
        self._marker = values_dict.get("Marker", values_dict.get("marker", ""))
        self._receptor = values_dict.get(
            "Receptor Point", values_dict.get("receptor point", {})
        )
        self._grid = values_dict.get("grid")

        self._TableWidgetHeader = ("id", "longitude", "latitude", "epsg")
        self._TableWidgetRows = values_dict.get("rows", 1)
        self._TableWidgetCols = values_dict.get("columns", len(self._TableWidgetHeader))
        self._TableWidgetInputs = {
            "rows": self._TableWidgetRows,
            "columns": self._TableWidgetCols,
            "header": self._TableWidgetHeader,
        }

        # Results analysis
        self._time_start = ""
        if "Start (incl.)" in values_dict:
            self._time_start = conversion.convertStringToDateTime(
                values_dict["Start (incl.)"]
            )
        self._time_end = (
            conversion.convertStringToDateTime(values_dict["End (incl.)"])
            if "End (incl.)" in values_dict
            else ""
        )
        self._pollutant = values_dict.get("pollutant")

        self.setConfigurationWidget(
            OrderedDict(
                [
                    ("X-Axis Title", QtWidgets.QLineEdit),
                    ("Marker", QtWidgets.QLineEdit),
                    ("Receptor Point", QtWidgets.QTableWidget),
                ]
            )
        )

        self.getConfigurationWidget().initValues(
            OrderedDict(
                {
                    "X-Axis Title": "Time [hh:mm:ss]",
                    "Marker": "x",
                    "Receptor Point": self._TableWidgetInputs,
                }
            )
        )

    def beginJob(self):

        self._data_x = []
        self._data_y = []
        self._receptor_df = pd.DataFrame()
        self._receptor_geom = Point()

        try:
            self._receptor_df = pd.DataFrame(
                columns=[hdr for hdr in self._TableWidgetHeader],  # Fill columnets
                index=range(self._TableWidgetRows),  # Fill rows
            )
            for i in range(self._TableWidgetRows):
                for j in range(self._TableWidgetCols):
                    self._receptor_df.ix[i, j] = self._receptor[(i, j)]

                if (
                    not self._receptor_df.dropna(how="any").empty
                    and "longitude" in self._receptor_df.keys()
                    and "latitude" in self._receptor_df.keys()
                ):
                    self._lon = self._receptor_df["longitude"].astype(float).values[0]
                    self._lat = self._receptor_df["latitude"].astype(float).values[0]
                    self._id = self._receptor_df["id"].astype(str).values[0]
                    self._epsg = self._receptor_df["epsg"].astype(str).values[0]
                    self._receptor_geom = Point(self._lon, self._lat)
                    logger.info(
                        "Timeseries will be generated for the point: %s"
                        % self._receptor_geom.to_wkt()
                    )
                    self._title += "\n(at %s)" % str(self._receptor_geom)

        except Exception as exc_:
            logger.error(exc_)

        self._griddata = self._grid.get_df_from_2d_grid_cells()
        self._griddata = self._griddata.assign(
            Emission=pd.Series(0, index=self._griddata.index)
        )
        self._griddata.crs = "epsg:3857"

        if self._receptor_df.dropna(how="any").empty:
            logger.info(
                "No receptor point found. Timeseries will be generated for the entire domain."
            )

    def process(self, timeval, result, **kwargs):
        # result is of format [(Source, Emission)]s
        # filter by configured time
        if self._time_start and self._time_end:
            if not (timeval >= self._time_start and timeval < self._time_end):
                return True

        if self._receptor_df.dropna(how="any").empty:
            total_emissions_ = sum(
                [
                    _f
                    for _f in [
                        sum([_f for _f in emissions_ if _f])
                        for (source, emissions_) in result
                    ]
                    if _f
                ]
            )

            if total_emissions_:
                self._data_x.append(timeval)

                if self._pollutant is not None:
                    self._data_y.append(
                        total_emissions_.getValue(self._pollutant, unit="kg")[0]
                    )
                else:
                    self._data_y.append(None)
        else:
            self._data_x.append(timeval)

            for (source, emissions) in result:
                for em_ in emissions:

                    EmissionValue = em_.getValue(self._pollutant, unit="kg")[0]
                    if EmissionValue == 0:
                        continue

                    try:
                        geom = em_.getGeometry()
                        if not geom.is_valid:
                            logger.debug("Not valid geometry %s" % str(geom))
                            geom = geom.buffer(0)  # unary_union(geom)

                        # some convenience variables
                        isPoint_element_ = bool(
                            isinstance(em_.getGeometry(), Point)
                        )  # bool("POINT" in emissions_.getGeometryText())
                        isLine_element_ = bool(
                            isinstance(em_.getGeometry(), LineString)
                        )
                        isMultiLine_element_ = bool(
                            isinstance(em_.getGeometry(), MultiLineString)
                        )
                        isPolygon_element_ = bool(
                            isinstance(em_.getGeometry(), Polygon)
                        )
                        isMultiPolygon_element_ = bool(
                            isinstance(em_.getGeometry(), MultiPolygon)
                        )

                        matched_cells_2D = self._griddata[
                            self._griddata.intersects(geom) == True
                        ]

                        # Calculate Emissions' horizontal distribution
                        if isLine_element_:
                            # ToDo: Add if
                            matched_cells_2D.loc[matched_cells_2D.index, "Emission"] = (
                                EmissionValue
                                * matched_cells_2D.intersection(geom).length
                                / geom.length
                            )
                        elif isPoint_element_:
                            matched_cells_2D.loc[
                                matched_cells_2D.index, "Emission"
                            ] = EmissionValue / len(matched_cells_2D)
                        elif isPolygon_element_ or isMultiPolygon_element_:
                            matched_cells_2D.loc[matched_cells_2D.index, "Emission"] = (
                                EmissionValue
                                * matched_cells_2D.intersection(geom).area
                                / geom.area
                            )
                        elif isMultiLine_element_:
                            matched_cells_2D.loc[matched_cells_2D.index, "Emission"] = (
                                EmissionValue
                                * matched_cells_2D.intersection(geom).length
                                / geom.length
                            )

                        self._griddata.loc[
                            matched_cells_2D.index, "Emission"
                        ] += matched_cells_2D["Emission"]
                    except Exception as exc_:
                        print(exc_)
                        continue

            receptor_cell = self._griddata[
                self._griddata.to_crs({"init": "epsg:%s" % self._epsg}).intersects(
                    self._receptor_geom
                )
                == True
            ]
            if not receptor_cell.empty:
                self._data_y.append(receptor_cell["Emission"].sum())
            else:
                self._data_y.append(0)

    def endJob(self):
        # show widget

        # create a new instance of a QtDialog for matplotlib plotting with parent of current QtDialog (focusing)
        if self._data_x and self._data_y and len(self._data_x) == len(self._data_y):

            # at least one element must be nonzero ...
            if all(e is None for e in self._data_y):
                # self._data_y = [0.] * len(self._data_y)
                self._data_y[0] = 0.0

            self._widget = MatplotlibQtDialog(self._parent)  # self

            self._widget.plot(self._data_x, self._data_y, self._marker)

            self._widget.getFigure().suptitle(self._title)

            # axis formatting
            axis = self._widget.getAxes()
            axis.set_xlabel(self._xtitle)
            axis.set_ylabel(self._ytitle)

            axis.set_ylim(
                [
                    min(self._widget.getPlt().ylim()[0], 0),
                    self._widget.getPlt().ylim()[1] * 1.1,
                ]
            )

            # use time as axis units
            formatter = DateFormatter("%Y-%m-%d %H:%M:%S")
            # formatter = DateFormatter('%H:%M:%S')
            axis.xaxis.set_major_formatter(formatter)

            # optimize the ticks of the axes
            self._widget.getFigure().autofmt_xdate()

            self._widget.getPlt().subplots_adjust(bottom=0.25, left=0.25)
            self._widget.getPlt().xticks(rotation=25)

        return self._widget

    # ToDo:
    # def ApplyAveraging


# def moving_average(a, n=3) :
#     ret = np.cumsum(a, dtype=float)
#     ret[n:] = ret[n:] - ret[:-n]
#     return ret[n - 1:] / n

# def movingaverage(interval, window_size):
# x is the array,  window_size: is the number of samples to consider
#     window = np.ones(int(window_size))/float(window_size)
#     return np.convolve(interval, window, 'same')
# Also check:
# https://gordoncluster.wordpress.com/2014/02/13/python-numpy-how-to-generate-moving-averages-efficiently-part-2/
# http://pandas.pydata.org/pandas-docs/stable/computation.html#moving-rolling-statistics-moments
