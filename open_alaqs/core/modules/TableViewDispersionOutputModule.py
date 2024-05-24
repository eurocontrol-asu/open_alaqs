import os
from collections import OrderedDict
from datetime import datetime, timedelta

import numpy as np
from dateutil import rrule
from qgis.PyQt import QtWidgets
from qgis.PyQt.uic import loadUiType

from open_alaqs.core.alaqslogging import get_logger
from open_alaqs.core.interfaces.OutputModule import OutputModule
from open_alaqs.core.tools import conversion
from open_alaqs.core.tools.csv_interface import write_csv

Ui_TableViewDialog, _ = loadUiType(
    os.path.join(os.path.dirname(__file__), "..", "..", "ui", "ui_table_view_dialog.ui")
)

logger = get_logger(__name__)


class TableViewDispersionModule(OutputModule):
    """
    Module to plot results of emission calculation in a table
    """

    settings_schema = {
        "is_plotting_daily_max_enabled": {
            "label": "Enable Plotting of Daily Maximum Values",
            "widget_type": QtWidgets.QCheckBox,
            "initial_value": False,
        },
        "is_csv_output_enabled": {
            "label": "Enable CSV File Output",
            "widget_type": QtWidgets.QCheckBox,
            "initial_value": False,
        },
    }

    @staticmethod
    def getModuleName():
        return "TableViewDispersionModule"

    @staticmethod
    def getModuleDisplayName():
        return "Table View"

    def __init__(self, values_dict=None):
        if values_dict is None:
            values_dict = {}
        OutputModule.__init__(self, values_dict)

        # Widget configuration
        self._parent = values_dict.get("parent")

        # Results analysis
        self._time_start = (
            conversion.convertStringToDateTime(values_dict["start_dt_inclusive"])
            if "start_dt_inclusive" in values_dict
            else ""
        )
        self._time_end = (
            conversion.convertStringToDateTime(values_dict["end_dt_inclusive"])
            if "end_dt_inclusive" in values_dict
            else ""
        )
        self._pollutant_list = ["CO2", "CO", "HC", "NOx", "SOx", "PM"]

        self._widget = TableViewWidget(self._parent)

        self._max_values = (values_dict.get("is_plotting_daily_max_enabled", False),)
        self._save_csv = values_dict.get("is_csv_output_enabled", False)

        self._averaging_period = values_dict.get("averaging_period", "annual mean")
        self._check_uncertainty = values_dict.get("check_uncertainty", False)
        self._timeseries = values_dict.get("timeseries")
        self._concentration_database = values_dict.get("concentration_path")

    def getWidget(self):
        return self._widget

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

    def assert_validity(self, avg_period="annual mean"):
        required_proportion = 0.90 if avg_period == "annual mean" else 0.75
        if np.count_nonzero(self._data_y) < required_proportion * len(self._data_y):
            logger.error("Required proportion of valid data is not enough!")

    def beginJob(self):
        self._rows = []
        self._headers = ["Time"]

        self._data_x = []
        self._data = OrderedDict()

    def process(self):
        try:
            if self._averaging_period == "annual mean":
                QtWidgets.QMessageBox.information(
                    None, "Error", "Cannot create time-series plot for annual mean"
                )

            else:
                OrderedDict()

                if self._averaging_period == "daily mean":
                    # logger.debug("Averaging based on %s"%self._averaging_period)
                    self._data_x = [
                        day_
                        for day_ in rrule.rrule(
                            rrule.DAILY,
                            dtstart=self._time_start,
                            until=self._time_end + timedelta(days=-1),
                        )
                    ]

                    pollutant_list = []
                    for pollutant_ in self._pollutant_list:
                        self._data_y = []
                        self._data_y_max = []
                        time_counter = 1
                        while time_counter <= (self._time_end - self._time_start).days:

                            output_file = (
                                os.path.join(
                                    self._concentration_database,
                                    "%s-%sa.dmna"
                                    % (pollutant_.lower(), str(time_counter).zfill(3)),
                                )
                                if not self._check_uncertainty
                                else os.path.join(
                                    self._concentration_database,
                                    "%s-%ss.dmna"
                                    % (pollutant_.lower(), str(time_counter).zfill(3)),
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

                            if time_counter == 1:
                                pollutant_list.append(
                                    (" ").join([pollutant_, "[", self._units, "]"])
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
                                self._data_y_max.append(
                                    np.max(total_column_concentration)
                                )

                            time_counter += +1

                        if self._max_values:
                            self._data.update({pollutant_: self._data_y_max})
                        else:
                            self._data.update({pollutant_: self._data_y})

                else:  # hourly means (1h, 8h, whatever ..)
                    self._data_x = [
                        hour_
                        for hour_ in rrule.rrule(
                            rrule.HOURLY,
                            dtstart=self._time_start,
                            until=self._time_end + timedelta(hours=-1),
                        )
                    ]

                    pollutant_list = []
                    for pollutant_ in self._pollutant_list:
                        self._data_y = []
                        self._data_y_max = []
                        time_counter = 1
                        for timeval in self._timeseries:

                            while time_counter <= len(self._data_x):
                                output_file = (
                                    os.path.join(
                                        self._concentration_database,
                                        "%s-%sa.dmna"
                                        % (
                                            pollutant_.lower(),
                                            str(time_counter).zfill(3),
                                        ),
                                    )
                                    if not self._check_uncertainty
                                    else os.path.join(
                                        self._concentration_database,
                                        "%s-%ss.dmna"
                                        % (
                                            pollutant_.lower(),
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

                                # self._units = output_data['unit'][0].decode('latin-1') if ('unit' in output_data and len(output_data['unit']) > 0) else None
                                self._units = (
                                    output_data["unit"][0]
                                    if (
                                        "unit" in output_data
                                        and len(output_data["unit"]) > 0
                                    )
                                    else None
                                )

                                if time_counter == 1:
                                    pollutant_list.append(
                                        (" ").join([pollutant_, "[", self._units, "]"])
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
                                            concentration_matrix_reshaped[
                                                0, :, :
                                            ].squeeze()
                                        )
                                    )
                                else:
                                    # take the concentration up tp Kmax: <c> = c1*H1/(H1+H2+H3+...) + c2*H2/(H1+H2+H3+...) + c3*H3/(H1+H2+H3+...) + ...
                                    total_column_concentration = np.zeros(
                                        shape=(index_j, index_i)
                                    )
                                    for z_ in range(1, index_k + 1):
                                        total_column_concentration += (
                                            conversion.convertToFloat(
                                                output_data["sk"][z_]
                                            )
                                            * concentration_matrix_reshaped[
                                                z_ - 1, :, :
                                            ].squeeze()
                                        ) / conversion.convertToFloat(
                                            output_data["sk"][index_k]
                                        )
                                    self._data_y.append(
                                        np.mean(total_column_concentration)
                                    )
                                    self._data_y_max.append(
                                        np.max(total_column_concentration)
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
                                mov_average = (
                                    self.CalculateMovingAverage(self._data_y_max, n=8)
                                    if self._max_values
                                    else self.CalculateMovingAverage(self._data_y, n=8)
                                )

                        if self._max_values:
                            if self._averaging_period == "8-hours mean":
                                self._data.update({pollutant_: mov_average})
                            else:
                                self._data.update({pollutant_: self._data_y_max})
                        else:
                            if self._averaging_period == "8-hours mean":
                                self._data.update({pollutant_: mov_average})
                            else:
                                self._data.update({pollutant_: self._data_y})

        except Exception as e:
            logger.error("TableViewDispersionOutputModule: Cannot fetch data: %s" % e)

        # satisfy validity criteria check
        self.assert_validity(avg_period=self._averaging_period)

        DataTableHeaders = ["Time"]
        for poll_ in pollutant_list:
            DataTableHeaders.append(poll_)
            self._headers.append(poll_.encode("utf-8"))

        self._widget.setDataTableHeaders(DataTableHeaders)
        self._rows.append(self._headers)

        # logger.debug("DataTableHeaders: %s"%self._widget.getDataTableHeaders())

        # ToDo: ensure size of arrays !
        # write cells
        self._data_x = (
            self._data_x[7:]
            if self._averaging_period == "8-hours mean"
            else self._data_x
        )

        for index_row, time_interval in enumerate(self._data_x):
            time_ = (
                time_interval.strftime("%Y-%m-%d")
                if self._averaging_period == "daily mean"
                else time_interval.strftime("%Y-%m-%d %H:%M")
            )
            # increment rows in table by one
            self._widget.getTable().setRowCount(
                int(self._widget.getTable().rowCount() + 1)
            )

            cell_data = [time_]
            for pollutant_ in self._pollutant_list:
                cell_data.append("{:7.4}".format((self._data[pollutant_][index_row])))
            self._rows.append(cell_data)

            for index_col_, val_ in enumerate(cell_data):
                self._widget.getTable().setItem(
                    self._widget.getTable().rowCount() - 1,
                    index_col_,
                    QtWidgets.QTableWidgetItem(str(val_) if val_ is not None else ""),
                )

        return True

    @property
    def endJob(self):
        self._widget.resizeToContent()
        if self._max_values:
            self._widget.setWindowTitle(
                "Concentration results - %s (max. of all grid cells)"
                % self._averaging_period
            )
        else:
            self._widget.setWindowTitle(
                "Concentration results - %s (mean of all grid cells)"
                % self._averaging_period
            )

        # write output to csv file
        if self._save_csv:
            filename = (
                "max_conc_%s.csv" % self._averaging_period.replace(" ", "_")
                if self._max_values
                else "conc_%s.csv" % self._averaging_period.replace(" ", "_")
            )
            csv_path = os.path.join(self._concentration_database, filename)
            write_csv(csv_path, self._rows)

        return self._widget


class TableViewWidget(QtWidgets.QDialog):
    """
    This class provides a dialog for visualizing ALAQS results.
    """

    def __init__(self, parent=None):
        super(TableViewWidget, self).__init__(parent)

        self._parent = parent

        self.ui = Ui_TableViewDialog()
        self.ui.setupUi(self)

        self._data_table_headers = []

        self.initTable()

    def initTable(self):
        self.getTable().setColumnCount(len(self._data_table_headers))
        self.getTable().setHorizontalHeaderLabels(self._data_table_headers)
        self.getTable().verticalHeader().setVisible(False)

    def resizeToContent(self):
        self.getTable().resizeColumnsToContents()
        self.getTable().resizeRowsToContents()

    def getTable(self):
        return self.ui.data_table

    def resetTable(self):
        self.getTable().clear()
        self.getTable().setHorizontalHeaderLabels(self._data_table_headers)
        self.getTable().setRowCount(0)

    def setDataTableHeaders(self, headers):
        self._data_table_headers = headers
        self.initTable()

    def getDataTableHeaders(self):
        return self._data_table_headers
