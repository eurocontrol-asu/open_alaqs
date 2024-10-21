from typing import Iterable, Literal, Optional

from qgis.PyQt.QtWidgets import QComboBox, QWidget


def populate_combobox(
    combobox: QComboBox,
    values: Iterable[str],
    value: Optional[str] = None,
    fallback_value: Optional[str] = None,
    add_empty: bool = False,
):
    combobox.clear()

    values = list(values)

    if add_empty:
        combobox.addItem(None)

    if not values:
        combobox.setCurrentIndex(0)
        return

    if fallback_value is not None and fallback_value not in values:
        raise Exception("Expected fallback value to be in the list of values!")

    combobox.addItems(values)

    if combobox.count() == 0:
        return

    if value and value in values:
        combobox.setCurrentIndex(values.index(value))
    else:
        if fallback_value is None:
            combobox.setCurrentIndex(0)
        else:
            combobox.setCurrentIndex(values.index(fallback_value))


def color_ui_background(
    ui_element: QWidget, color: Literal[None, "red", "white", "green"]
) -> None:
    """Changes the background color of a UI object. Used to alert users to incorrect values.

    Args:
        ui_element (QWidget): the widget that needs to be updated
        color (str | None): the color to be set, or None if the color should be reset.

    Raises:
        NotImplementedError: _description_
    """
    if color is None:
        color_style = ""
        ui_element.setStyleSheet(color_style)
    elif color == "red":
        color_style = "QWidget { background-color: rgba(255, 107, 107, 150); }"
        ui_element.setStyleSheet(color_style)
    elif color == "green":
        color_style = "QWidget { background-color: rgba(0,255,0,0.3); }"
        ui_element.setStyleSheet(color_style)
    else:
        raise NotImplementedError(f"Unknown color: {color}")
