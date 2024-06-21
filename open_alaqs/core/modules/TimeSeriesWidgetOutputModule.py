import logging
from datetime import datetime
from typing import Any, TypedDict

import matplotlib
import pandas as pd
from matplotlib.dates import DateFormatter
from qgis.PyQt import QtWidgets
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.Emissions import Emission, PollutantType, PollutantUnit
from open_alaqs.core.interfaces.OutputModule import OutputModule
from open_alaqs.core.interfaces.Source import Source
from open_alaqs.core.plotting.MatplotlibQtDialog import MatplotlibQtDialog

logging.getLogger("matplotlib").setLevel(logging.ERROR)
matplotlib.use("Qt5Agg")

logger = get_logger(__name__)


class ReceptorPointRow(TypedDict):
    id: str
    latitude: str
    longitude: str
    epsg: str


class TimeSeriesWidgetOutputModule(OutputModule):
    """
    Module to plot a timeseries of the emission calculation
    """

    settings_schema = {
        "x_axis_title": {
            "label": "X-Axis Title",
            "widget_type": QtWidgets.QLineEdit,
            "initial_value": "Time [hh:mm:ss]",
        },
        "marker": {
            "label": "Marker",
            "widget_type": QtWidgets.QLineEdit,
            "initial_value": "x",
        },
        "receptor_point": {
            "label": "Receptor Point",
            "widget_type": QtWidgets.QTableWidget,
            "initial_value": [(None, None, None, "4326")],
            "widget_config": {
                "table_headers": [
                    ("id", "ID"),
                    ("longitude", "Longitude"),
                    ("latitude", "Latitude"),
                    ("epsg", "EPSG"),
                ],
            },
        },
    }

    @staticmethod
    def getModuleName() -> str:
        return "TimeSeriesWidgetOutputModule"

    @staticmethod
    def getModuleDisplayName() -> str:
        return "Time Series"

    def __init__(self, values_dict: dict[str, Any]) -> None:
        super().__init__(values_dict)

        # Widget configuration
        self._parent = values_dict.get("parent")
        self._widget = None

        # Plot configuration
        self._title = values_dict.get("title", "")
        self._xtitle = values_dict.get("x_axis_title", "")
        self._ytitle = values_dict.get("ytitle", "")
        self._marker = values_dict.get("marker", "")
        # TODO OPENGIS.ch: the `_receptor` should be empty, otherwise it fails later with `_epsg` attribute error
        self._receptor = values_dict.get("receptor_point", {})
        self.receptor_points: list[Point] = self.configuration_to_receptor_points(
            values_dict.get("receptor_point", {})
        )

        self._grid = values_dict.get("grid")

        # Results analysis
        self._time_start = values_dict["start_dt_inclusive"]
        self._time_end = values_dict["end_dt_inclusive"]

        self.pollutant_type = PollutantType(values_dict["pollutant"].lower())

    def configuration_to_receptor_points(
        self, receptor_point_rows: list[ReceptorPointRow]
    ) -> list[Point]:
        points = []
        for row in receptor_point_rows:
            if row["latitude"] and row["longitude"]:
                points.append(Point(row["latitude"], row["longitude"]))
            else:
                logger.info(f'Skipping row {row["id"]}...')

        return points

    def beginJob(self):
        self._data_x = []
        self._data_y = []

        self._griddata = self._grid.get_df_from_2d_grid_cells()
        self._griddata = self._griddata.assign(
            Emission=pd.Series(0, index=self._griddata.index)
        )
        self._griddata.crs = "epsg:3857"

    def process(
        self,
        timestamp: datetime,
        result: list[tuple[Source, list[Emission]]],
        **kwargs: Any,
    ) -> None:
        if self._time_start and self._time_end:
            if not (timestamp >= self._time_start and timestamp < self._time_end):
                return None

        if len(self.receptor_points) == 0:
            total_emissions_ = sum(
                [sum(emissions_) for (_, emissions_) in result if emissions_]
            )

            if total_emissions_:
                self._data_x.append(timestamp)
                self._data_y.append(
                    total_emissions_.get_value(self.pollutant_type, PollutantUnit.KG)
                )

        else:
            self._data_x.append(timestamp)

            for _source, emissions in result:
                for em_ in emissions:

                    EmissionValue = em_.get_value(self.pollutant_type, PollutantUnit.KG)
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
                            self._griddata.intersects(geom) == True  # noqa: E712
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
                            matched_cells_2D.loc[matched_cells_2D.index, "Emission"] = (
                                EmissionValue / len(matched_cells_2D)
                            )
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

            # FIXME OPENGIS.ch: most probably we should make it support more than 1 `receptor_point` in the future
            receptor_point_row = self.receptor_points[0]
            intersection = self._griddata.to_crs(
                {
                    "init": f"epsg:{receptor_point_row['epsg']}",
                }
            ).intersects(
                Point(receptor_point_row["longitude"], receptor_point_row["latitude"])
            )
            receptor_cell = self._griddata[intersection == True]  # noqa: E712

            if receptor_cell.empty:
                self._data_y.append(0)
            else:
                self._data_y.append(receptor_cell["Emission"].sum())

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
