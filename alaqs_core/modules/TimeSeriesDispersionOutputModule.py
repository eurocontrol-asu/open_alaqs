import os
from collections import OrderedDict
from datetime import datetime, timedelta

import numpy as np
from dateutil import rrule
from matplotlib.dates import DateFormatter
from PyQt5 import QtWidgets

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.interfaces.OutputModule import OutputModule
from open_alaqs.alaqs_core.plotting.MatplotlibQtDialog import MatplotlibQtDialog
from open_alaqs.alaqs_core.tools import conversion

logger = get_logger(__name__)


class TimeSeriesDispersionModule(OutputModule):
    """
    Module to plot a timeseries of the emission calculation
    """

    @staticmethod
    def getModuleName():
        return "TimeSeriesDispersionModule"

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
        self._options = values_dict.get("options", "")

        self._max_values = values_dict.get(
            "Enable Plotting of Daily Maximum Values",
            values_dict.get("max. values", False),
        )

        # Results analysis
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

        self._averaging_period = values_dict.get("averaging_period", "annual mean")
        self._pollutant = values_dict.get("pollutant")
        self._check_uncertainty = values_dict.get("check_uncertainty", False)
        self._timeseries = values_dict.get("timeseries")
        self._concentration_database = values_dict.get("concentration_path", None)
        # self._total_concentration = 0.

        widget_parameters = OrderedDict(
            [
                ("X-Axis Title", QtWidgets.QLineEdit),
                ("Enable Plotting of Daily Maximum Values", QtWidgets.QCheckBox)
                # "moving average": QtGui.QCheckBox
                # "options" : QtGui.QLineEdit
            ]
        )
        self.setConfigurationWidget(widget_parameters)

        self.getConfigurationWidget().initValues(
            OrderedDict(
                {
                    "X-Axis Title": "Time [Y-m-d HH:MM]",
                    "Enable Plotting of Daily Maximum Values": False
                    # "moving average": False,
                    # "options" : "*"
                }
            )
        )

        self._configuration_widget.getSettings()[
            "Enable Plotting of Daily Maximum Values"
        ].setToolTip(
            "Enabled to plot daily max. instead of daily mean values for the whole grid"
        )
        # self._configuration_widget.getSettings()["moving average"].setToolTip('n-8 for hourly values, n-5 for daily values')

    def assure_time_interval(self, output_data):
        try:  # convert t1, t2 to dates and check timedelta
            t1, t2, t0 = (
                output_data["t1"][0],
                output_data["t2"][0],
                output_data["rdat"][0],
            )
            # reconstruct actual date
            start_date = datetime.strptime(t0, "%Y-%m-%d.%H:%M:%S")

            start_time = (
                datetime.strptime(t1, "%d.%H:%M:%S").replace(year=start_date.year)
                if ("." in t1)
                else datetime.strptime(t1, "%H:%M:%S").replace(year=start_date.year)
            )
            start_time = (
                start_time + timedelta(days=0)
                if ("." not in t1)
                else start_time.replace(
                    day=conversion.convertToInt(t1.split(".")[0]) + 1
                )
            )

            end_time = (
                datetime.strptime(t2, "%d.%H:%M:%S").replace(year=start_date.year)
                if ("." in t2)
                else datetime.strptime(t2, "%H:%M:%S").replace(year=start_date.year)
            )
            end_time = (
                end_time + timedelta(days=0)
                if ("." not in t2)
                else end_time.replace(day=conversion.convertToInt(t2.split(".")[0]) + 1)
            )

            # timedelta
            tdelta = end_time - start_time

            if self._averaging_period == "daily mean" and (
                tdelta.total_seconds() == 86400.0
            ):
                return True
            # if self._averaging_period == "1-h, 8-h, or else": timedelta should be 1h
            elif self._averaging_period != "daily mean" and (
                tdelta.total_seconds() == 3600.0
            ):
                return True
            else:
                QtWidgets.QMessageBox.warning(
                    None,
                    "Time interval error",
                    "Error in timedelta: (start: %s, end:%s)" % (t1, t2),
                )
                # logger.debug("Error in timedelta: (start: %s, end:%s)"%(t1, t2))
                # logger.debug("\t (SD: %s, ED:%s, TD:%s)"%(start_time, end_time, tdelta.total_seconds()))
                return False
        except Exception:
            return False

    def assert_validity(self, avg_period="annual mean"):
        required_proportion = 0.90 if avg_period == "annual mean" else 0.75
        if np.count_nonzero(self._data_y) < required_proportion * len(self._data_y):
            logger.error("Required proportion of valid data is not enough!")

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

    def CalculateMovingAverage(self, conc, n=3):
        ret = np.cumsum(conc, dtype=float)
        ret[n:] = ret[n:] - ret[:-n]
        return ret[n - 1 :] / n

    def beginJob(self):

        if self._pollutant.startswith("PM"):
            logger.debug(
                "Pollutant '%s', will be written simply as 'PM'" % self._pollutant
            )
            self._pollutant = "PM"

        self._data_x = []
        self._data_y = []
        self._data_y_std = []
        self._data_y_max = []
        self._8h_runnning_average = []
        self._8h_runnning_average_max = []

    def process(self):
        try:
            self._header = [(self._pollutant, "double")]

            if self._averaging_period == "annual mean":
                QtWidgets.QMessageBox.information(
                    None, "Error", "Cannot create time-series plot for annual mean"
                )

            else:
                OrderedDict()
                time_counter = 1

                if self._averaging_period == "daily mean":
                    logger.debug("Averaging based on %s" % self._averaging_period)
                    self._data_x = [
                        day_
                        for day_ in rrule.rrule(
                            rrule.DAILY,
                            dtstart=self._time_start,
                            until=self._time_end + timedelta(days=-1),
                        )
                    ]
                    while time_counter <= (self._time_end - self._time_start).days:
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
                            QtWidgets.QMessageBox.warning(
                                None,
                                "Timedelta Error",
                                "Make sure files do exist for averaging method: '%s'"
                                % self._averaging_period,
                            )
                            logger.warning(
                                "Error in timedelta when reading dispersion model outputs. Choose another averaging period."
                            )
                            return False

                        # self._sk = output_data['sk'] if ('sk' in output_data and len(output_data['sk']) > 0) else None
                        # self._units = output_data['unit'][0].decode('latin-1') if ('unit' in output_data and len(output_data['unit']) > 0) else None
                        self._units = (
                            output_data["unit"][0]
                            if ("unit" in output_data and len(output_data["unit"]) > 0)
                            else None
                        )

                        index_i = (
                            conversion.convertToInt(output_data["hghb"][0])
                            if ("hghb" in output_data and len(output_data["hghb"]) > 0)
                            else None
                        )  # columns
                        index_j = (
                            conversion.convertToInt(output_data["hghb"][1])
                            if ("hghb" in output_data and len(output_data["hghb"]) > 0)
                            else None
                        )  # rows
                        index_k = (
                            conversion.convertToInt(output_data["hghb"][2])
                            if ("hghb" in output_data and len(output_data["hghb"]) > 0)
                            else None
                        )  # z

                        if not (index_k and index_i and index_j):
                            logger.error(
                                "Error in reshaping concentration matrix: (%s, %s, %s)"
                                % (index_k, index_i, index_j)
                            )
                            return False

                        concentration_matrix_reshaped = np.reshape(
                            concentration_matrix, (index_k, index_j, index_i)
                        )
                        # The result files contain the horizontal layers k=1...Kmax
                        if (
                            self._check_uncertainty
                        ):  # take only first level for uncertainty: 0m to 3m
                            self._data_y.append(
                                np.mean(
                                    concentration_matrix_reshaped[0, :, :].squeeze()
                                )
                            )
                        else:
                            # take the concentration up tp Kmax: <c> = c1*H1/(H1+H2+H3+...) + c2*H2/(H1+H2+H3+...) + c3*H3/(H1+H2+H3+...) + ...
                            total_column_concentration = np.zeros(
                                shape=(index_j, index_i)
                            )
                            for z_ in range(1, index_k + 1):
                                total_column_concentration += (
                                    conversion.convertToFloat(output_data["sk"][z_])
                                    * concentration_matrix_reshaped[
                                        z_ - 1, :, :
                                    ].squeeze()
                                ) / conversion.convertToFloat(
                                    output_data["sk"][index_k]
                                )
                            self._data_y.append(np.mean(total_column_concentration))
                            self._data_y_max.append(np.max(total_column_concentration))
                            self._data_y_std.append(np.std(total_column_concentration))

                        time_counter += +1

                else:  # hourly means (1h, 8h, whatever ..)
                    self._data_x = [
                        hour_
                        for hour_ in rrule.rrule(
                            rrule.HOURLY,
                            dtstart=self._time_start,
                            until=self._time_end + timedelta(hours=-1),
                        )
                    ]
                    # assert len(self._data_x) > 8

                    for timeval in self._timeseries:

                        while time_counter <= len(self._data_x):
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

                            (
                                output_data,
                                index_,
                                concentration_matrix,
                            ) = self.readA2Koutput(output_file)
                            if not self.assure_time_interval(output_data):
                                QtWidgets.QMessageBox.warning(
                                    None,
                                    "Timedelta Error",
                                    "Make sure files do exist for averaging method: '%s'"
                                    % self._averaging_period,
                                )
                                logger.warning(
                                    "Error in timedelta when reading dispersion model outputs. Choose another averaging period."
                                )
                                return False
                                # raise Exception("Error in timedelta. Choose another averaging period for time interval (%s, %s)"%(output_data['t1'], output_data['t2']))

                            # self._sk = output_data['sk'] if ('sk' in output_data and len(output_data['sk']) > 0) else None
                            # self._units = output_data['unit'][0].decode('latin-1') if ('unit' in output_data and len(output_data['unit']) > 0) else None
                            self._units = (
                                output_data["unit"][0]
                                if (
                                    "unit" in output_data
                                    and len(output_data["unit"]) > 0
                                )
                                else None
                            )

                            index_i = (
                                conversion.convertToInt(output_data["hghb"][0])
                                if (
                                    "hghb" in output_data
                                    and len(output_data["hghb"]) > 0
                                )
                                else None
                            )  # columns
                            index_j = (
                                conversion.convertToInt(output_data["hghb"][1])
                                if (
                                    "hghb" in output_data
                                    and len(output_data["hghb"]) > 0
                                )
                                else None
                            )  # rows
                            index_k = (
                                conversion.convertToInt(output_data["hghb"][2])
                                if (
                                    "hghb" in output_data
                                    and len(output_data["hghb"]) > 0
                                )
                                else None
                            )  # z

                            concentration_matrix_reshaped = np.reshape(
                                concentration_matrix, (index_k, index_j, index_i)
                            )

                            # The result files contain the horizontal layers k=1...Kmax
                            if (
                                self._check_uncertainty
                            ):  # take only first level for uncertainty: 0m to 3m
                                self._data_y.append(
                                    np.mean(
                                        concentration_matrix_reshaped[0, :, :].squeeze()
                                    )
                                )
                            else:
                                # take the concentration up tp Kmax: <c> = c1*H1/(H1+H2+H3+...) + c2*H2/(H1+H2+H3+...) + c3*H3/(H1+H2+H3+...) + ...
                                total_column_concentration = np.zeros(
                                    shape=(index_j, index_i)
                                )
                                for z_ in range(1, index_k + 1):
                                    total_column_concentration += (
                                        conversion.convertToFloat(output_data["sk"][z_])
                                        * concentration_matrix_reshaped[
                                            z_ - 1, :, :
                                        ].squeeze()
                                    ) / conversion.convertToFloat(
                                        output_data["sk"][index_k]
                                    )

                                self._data_y.append(np.mean(total_column_concentration))
                                self._data_y_max.append(
                                    np.max(total_column_concentration)
                                )
                                self._data_y_std.append(
                                    np.std(total_column_concentration)
                                )

                            time_counter += +1

                    if self._averaging_period == "8-hours mean":
                        if len(self._data_x) <= 8:
                            logger.warning(
                                "Not enough data to calculate 8h running mean"
                            )
                            return False
                        else:
                            # calculate 8h-moving mean
                            self._8h_runnning_average = self.CalculateMovingAverage(
                                self._data_y, n=8
                            )
                            self._8h_runnning_average_max = self.CalculateMovingAverage(
                                self._data_y_max, n=8
                            )

        except Exception as e:
            logger.error("TimeSeriesDispersionModule: Cannot fetch data: %s" % e)

        # satisfy validity criteria check
        self.assert_validity(avg_period=self._averaging_period)

        return True

    def endJob(self):
        # show widget

        # create a new instance of a QtDialog for matplotlib plotting with parent of current QtDialog (focusing)
        if (
            self._data_x
            and self._data_y
            and self._data_y_std
            and len(self._data_x) == len(self._data_y)
        ):

            # at least one element must be nonzero ...
            if all(e is None for e in self._data_y):
                # self._data_y = [0.] * len(self._data_y)
                self._data_y[0] = 0.0

            self._widget = MatplotlibQtDialog(self._parent)  # self

            # axis formatting
            axis = self._widget.getAxes()

            if not self._max_values:

                if self._averaging_period == "8-hours mean" and np.all(
                    0 <= self._8h_runnning_average
                ):
                    plot = self._widget.plot(
                        self._data_x, self._data_y, self._options, lw=2, color="k"
                    )
                    leg = ["Daily mean"]
                    no = 8
                    plot = self._widget.plot(
                        self._data_x[no - 1 :],
                        self._8h_runnning_average,
                        self._options,
                        lw=2,
                        color="b",
                        alpha=0.5,
                    )
                    leg.append("8h moving avg")

                else:
                    plot = self._widget.plot(
                        self._data_x, self._data_y, self._options, lw=2, color="k"
                    )
                    leg = (
                        ["Daily mean"]
                        if self._averaging_period == "daily mean"
                        else ["Hourly mean"]
                    )
                    y_plus_std = [
                        self._data_y[i] + self._data_y_std[i]
                        for i, j in enumerate(self._data_y)
                    ]
                    y_minus_std = [
                        self._data_y[i] - self._data_y_std[i]
                        for i, j in enumerate(self._data_y)
                    ]
                    axis.fill_between(
                        self._data_x,
                        y_plus_std,
                        y_minus_std,
                        lw=2,
                        facecolor="k",
                        alpha=0.5,
                    )

            else:
                plot = self._widget.plot(
                    self._data_x, self._data_y_max, self._options, lw=2, color="k"
                )
                leg = (
                    ["Daily max"]
                    if self._averaging_period == "daily mean"
                    else ["Hourly max."]
                )
                self._title = (" ").join(
                    [leg[0], "concentration of %s" % self._pollutant]
                )

                if self._averaging_period == "8-hours mean" and np.all(
                    0 <= self._8h_runnning_average_max
                ):
                    no = 8
                    plot = self._widget.plot(
                        self._data_x[no - 1 :],
                        self._8h_runnning_average_max,
                        self._options,
                        lw=2,
                        color="b",
                        alpha=0.5,
                    )
                    leg.append("8h moving avg (max)")

                    # if self._moving_average:
                    #     no = 5
                    #     ma = self.CalculateMovingAverage(self._data_y_max, n=no)
                    #     plot_ma = self._widget.plot(self._data_x[no-1:], ma, self._options, lw=2, color='b', alpha=0.5)
                    #     leg.append('Moving avg')

            legend = self._widget.getPlt().legend(
                leg, shadow=True, fancybox=True, loc="best"
            )
            self._widget.getPlt().setp(
                legend.get_texts(), fontsize="medium"
            )  # sizes = ['xx-small', 'x-small', 'small', 'medium', 'large', 'x-large'

            # Titles
            self._widget.getFigure().suptitle(self._title)
            axis.set_xlabel(self._xtitle)
            self._ytitle = (" ").join([self._ytitle, "(", self._units, ")"])
            axis.set_ylabel(self._ytitle)

            # Set Xlim, Ylim
            # axis.set_ylim([min(self._widget.getPlt().ylim()[0],0), self._widget.getPlt().ylim()[1]*1.1])

            # use time as axis units
            # formatter = DateFormatter('%Y-%m-%d %H:%M:%S')
            formatter = DateFormatter("%Y-%m-%d %H:%M")
            axis.xaxis.set_major_formatter(formatter)

            # optimize the ticks of the axes
            self._widget.getFigure().autofmt_xdate()

            self._widget.getPlt().subplots_adjust(bottom=0.25, left=0.25)
            self._widget.getPlt().xticks(rotation=35)

        return self._widget
