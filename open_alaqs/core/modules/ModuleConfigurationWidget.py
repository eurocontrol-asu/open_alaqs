from datetime import datetime
from typing import Any, Iterable, Optional, Type, TypedDict, Union, cast

from qgis.gui import QgsDoubleSpinBox, QgsFileWidget, QgsSpinBox
from qgis.PyQt import QtCore, QtWidgets
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QFormLayout

from open_alaqs.core.alaqslogging import get_logger

logger = get_logger(__name__)


class TableWidgetConfig(TypedDict):
    table_headers: list[tuple[str, str]]


class ComboBoxWidgetConfig(TypedDict):
    options: Iterable[str] | Iterable[tuple[str, str]]


class FileWidgetConfig(TypedDict):
    filter: str
    dialog_title: str


class SpinBoxWidgetConfig(TypedDict):
    minimum: int
    maximum: int


class DoubleSpinBoxWidgetConfig(TypedDict):
    minimum: float
    maximum: float
    decimals: float
    suffix: Optional[str]


class SettingSchema(TypedDict):
    label: Optional[str]
    widget_type: Type[QtWidgets.QWidget]
    initial_value: Any
    widget_config: Optional[
        Union[
            TableWidgetConfig,
            ComboBoxWidgetConfig,
            FileWidgetConfig,
            SpinBoxWidgetConfig,
            DoubleSpinBoxWidgetConfig,
        ]
    ]
    tooltip: Optional[str]


SettingsSchema = dict[str, SettingSchema]


class ModuleConfigurationWidget(QtWidgets.QWidget):
    def __init__(
        self,
        settings_schema: SettingsSchema,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._settings_schema = settings_schema
        self._settings_widgets: dict[str, QtWidgets.QWidget] = {}
        self._settings_labels: dict[str, QtWidgets.QLabel] = {}

        self.setLayout(QtWidgets.QFormLayout())

        for setting_name, setting_schema in settings_schema.items():
            self._add_setting(setting_name, setting_schema)

        self.init_values()

    def _add_setting(self, name: str, setting_schema: SettingSchema) -> None:
        WidgetType = setting_schema["widget_type"]
        widget_config = setting_schema.get("widget_config") or {}

        widget = WidgetType()
        label = QtWidgets.QLabel(setting_schema["label"])

        if isinstance(widget, QtWidgets.QDateTimeEdit):
            widget.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        elif isinstance(widget, QtWidgets.QAbstractButton):
            widget.setText(setting_schema["label"])
            label = None
        elif isinstance(widget, QgsDoubleSpinBox):
            widget_config = cast(DoubleSpinBoxWidgetConfig, widget_config)

            if widget_config.get("minimum") is not None:
                widget.setMinimum(widget_config["minimum"])

            if widget_config.get("maximum") is not None:
                widget.setMaximum(widget_config["maximum"])

            if widget_config.get("decimals") is not None:
                widget.setDecimals(widget_config["decimals"])

            if widget_config.get("suffix") is not None:
                widget.setSuffix(widget_config["suffix"])
        elif isinstance(widget, QtWidgets.QTableWidget):
            widget_config = cast(TableWidgetConfig, widget_config)

            widget.setRowCount(len(setting_schema["initial_value"]))
            widget.setColumnCount(len(widget_config["table_headers"]))
            widget.setHorizontalHeaderLabels(
                [p[1] for p in widget_config["table_headers"]]
            )
            widget.resizeColumnsToContents()
        elif isinstance(widget, QtWidgets.QComboBox):
            widget_config = cast(ComboBoxWidgetConfig, widget_config)

            widget.clear()
            options = self._normalize_combobox_values(widget_config["options"])
            for option in options:
                widget.addItem(option[1], option[0])
        elif isinstance(widget, QgsFileWidget):
            widget_config = cast(FileWidgetConfig, widget_config)

            if widget_config.get("filter") is not None:
                widget.setDialogTitle(widget_config["filter"])

            if widget_config.get("dialog_title") is not None:
                widget.setDialogTitle(widget_config["dialog_title"])

        widget.setToolTip(setting_schema.get("tooltip", ""))
        parent_layout = self.layout()

        assert isinstance(parent_layout, QFormLayout)

        if name in self._settings_widgets:
            old_widget = self._settings_widgets[name]
            old_label = self._settings_labels[name]

            old_widget.deleteLater()

            # the old label might be None, e.g. for checkboxes
            if old_label is not None:
                old_label.deleteLater()
                parent_layout.replaceWidget(old_label, label)

            parent_layout.replaceWidget(old_widget, widget)
        else:
            if label:
                parent_layout.insertRow(-1, label, widget)
            else:
                parent_layout.insertRow(-1, widget)

            self._settings_widgets[name] = widget
            self._settings_labels[name] = label

    def get_values(self) -> dict[str, Any]:
        values = {}

        for setting_name, setting_widget in self._settings_widgets.items():
            value = None
            if isinstance(setting_widget, QtWidgets.QLabel):
                value = setting_widget.text()
            elif isinstance(setting_widget, QtWidgets.QLineEdit):
                value = setting_widget.text()
            elif isinstance(setting_widget, QtWidgets.QAbstractButton):
                value = setting_widget.isChecked()
            elif isinstance(setting_widget, QtWidgets.QDateTimeEdit):
                value = (
                    setting_widget.dateTime()
                    .toString(Qt.DateFormat.ISODate)
                    .replace("T", " ")
                )
            elif isinstance(setting_widget, QtWidgets.QComboBox):
                widget_config = cast(
                    ComboBoxWidgetConfig,
                    self._settings_schema[setting_name]["widget_config"],
                )

                options = self._normalize_combobox_values(widget_config["options"])

                if not options:
                    value = None

                current_index = setting_widget.currentIndex()

                if current_index == -1:
                    current_index = 0

                value = options[current_index][0]
            elif isinstance(setting_widget, QtWidgets.QTableWidget):
                widget_config = cast(
                    TableWidgetConfig,
                    self._settings_schema[setting_name]["widget_config"],
                )

                value = []
                headers = widget_config["table_headers"]

                for row_idx in range(setting_widget.rowCount()):
                    value[row_idx] = {}

                    for col_idx in range(setting_widget.columnCount()):
                        if setting_widget.item(row_idx, col_idx) is not None:
                            raw_value = setting_widget.item(row_idx, col_idx).text()
                        else:
                            raw_value = None

                        column_name = headers[col_idx]
                        value[row_idx][column_name] = raw_value
            elif isinstance(setting_widget, QgsDoubleSpinBox) or isinstance(
                setting_widget, QgsSpinBox
            ):
                value = setting_widget.value()
            elif isinstance(setting_widget, QgsFileWidget):
                value = setting_widget.filePath()
            elif isinstance(
                setting_widget, (QtWidgets.QHBoxLayout, QtWidgets.QVBoxLayout)
            ):
                continue
            else:
                logger.error(
                    "Did not find method to read values from widget of type '%s'!",
                    type(setting_widget),
                )

            values[setting_name] = value

        return values

    def init_values(self, init_values: Optional[dict[str, Any]] = None) -> None:
        if not init_values:
            init_values = {}

            for setting_name, setting_schema in self._settings_schema.items():
                init_values[setting_name] = setting_schema.get("initial_value", None)

        for setting_name, value in init_values.items():
            setting_widget = self._settings_widgets[setting_name]
            setting_schema = self._settings_schema[setting_name]

            if isinstance(setting_widget, QtWidgets.QLabel):
                setting_widget.setText(str(value))
            elif isinstance(setting_widget, QtWidgets.QLineEdit):
                setting_widget.setText(str(value))
            elif isinstance(setting_widget, QtWidgets.QAbstractButton):
                setting_widget.setChecked(value)
            elif isinstance(setting_widget, QtWidgets.QComboBox):
                idx = self._get_combobox_index(setting_name, value)
                setting_widget.setCurrentIndex(idx)
            elif isinstance(setting_widget, QtWidgets.QTableWidget):
                setting_widget.setRowCount(len(value))

                for row_idx in range(setting_widget.rowCount()):
                    for col_idx in range(setting_widget.columnCount()):
                        item = QtWidgets.QTableWidgetItem(value[row_idx][col_idx])
                        setting_widget.setItem(row_idx, col_idx, item)

                setting_widget.resizeColumnsToContents()
            elif isinstance(setting_widget, QtWidgets.QHBoxLayout) or isinstance(
                setting_widget, QtWidgets.QVBoxLayout
            ):
                continue
            elif isinstance(setting_widget, QtWidgets.QDateTimeEdit):
                if isinstance(value, (datetime, QtCore.QDateTime)):
                    setting_widget.setDateTime(value)
                elif isinstance(value, str):
                    setting_widget.setDateTime(QtCore.QDateTime.fromString(value))
                else:
                    raise NotImplementedError(
                        f"Not implemented support for date of type `{type(value)}`"
                    )
            elif isinstance(setting_widget, QgsDoubleSpinBox):
                setting_widget.setValue(float(value))
            elif isinstance(setting_widget, QgsSpinBox):
                setting_widget.setValue(int(value))
            elif isinstance(setting_widget, QgsFileWidget):
                setting_widget.setFilePath(value)
            else:
                logger.error(
                    "Did not find method to set values to widget of type '%s'!",
                    type(setting_widget),
                )

        self.update()

    def patch_schema(self, schema: SettingsSchema) -> None:
        for setting_name, new_schema in schema.items():
            old_schema = self._settings_schema[setting_name]
            patched_setting_schema = cast(
                SettingSchema,
                {
                    **old_schema,
                    **new_schema,
                    "widget_config": {
                        **(old_schema.get("widget_config") or {}),
                        **(new_schema.get("widget_config") or {}),
                    },
                },
            )
            self._settings_schema[setting_name] = patched_setting_schema
            self._add_setting(setting_name, patched_setting_schema)
            self.init_values({setting_name: patched_setting_schema["initial_value"]})

    def get_widget(self, setting_name: str) -> QtWidgets.QWidget:
        return self._settings_widgets[setting_name]

    def get_table_value(self, setting_name: str) -> list[dict[str, Any]]:
        widget_config = cast(
            TableWidgetConfig, self._settings_schema[setting_name]["widget_config"]
        )
        headers = widget_config["table_headers"]
        raw_values = self.get_values()[setting_name]

        values = []

        for keys, raw_value in raw_values.items():
            row_idx, col_idx = keys

            try:
                values[row_idx]
            except IndexError:
                values[row_idx] = {}

            column_name = headers[col_idx]
            values[row_idx][column_name] = raw_value

        return values

    def _normalize_combobox_values(
        self, options: Union[Iterable[str], Iterable[tuple[str, str]]]
    ) -> list[tuple[str, str]]:
        result = []

        for option in options:
            if isinstance(option, str):
                result.append((option, option))
            elif isinstance(option, tuple):
                result.append(option)
            else:
                raise ValueError(
                    "Expected options to be iterable of tuples or strings!"
                )

        return result

    def _get_combobox_index(self, setting_name: str, value: str) -> int:
        widget_config = cast(
            ComboBoxWidgetConfig,
            self._settings_schema[setting_name]["widget_config"],
        )
        options = self._normalize_combobox_values(widget_config["options"])

        for idx, option in enumerate(options):
            if option[0] == value:
                return idx

        return -1
