from typing import Iterable, Optional

from qgis.PyQt.QtWidgets import QComboBox


def populate_combobox(
    combobox: QComboBox,
    values: Iterable[str],
    value: Optional[str] = None,
    fallback_value: Optional[str] = None,
):
    combobox.clear()

    values = list(values)

    if not values:
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
