import time
from datetime import datetime
from typing import Any, Optional, Union


# For time conversions: Use UTC time only
def convertToFloat(value: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Convert value to a float or if not possible return a default value.

    :param value:
    :param default:
    :return:
    """
    if value is None or value == "":
        return default

    try:
        return float(value)  # float takes only string or float
    except ValueError:
        return default


def convertToInt(value: Any, default: Optional[int] = None) -> Optional[int]:
    """
    Convert value to an integer or if not possible return a default value.

    :param value:
    :param default:
    :return:
    """
    if value is None or value == "":
        return default

    try:
        return int(value)
    except ValueError:
        return default


def convertSecondsToTime(value: float) -> Union[time.struct_time, None]:
    """
    Convert a timestamp in seconds to a timestamp as string.

    :param value:
    :return:
    """
    if value is None:
        return None
    return datetime.utcfromtimestamp(int(value)).utctimetuple()


def convertStringToTime(value: str, format_="%Y-%m-%d %H:%M:%S") -> Union[tuple, None]:
    """
    Convert a timestamp as string to a time tuple.

    :rtype: object
    """
    if not value:
        return None

    if isinstance(value, str):
        return time.strptime(value, format_)
    return None


def convertStringToDateTime(value: str) -> datetime:
    """
    Convert a timestamp as string to datetime object.
    """
    if not isinstance(value, str):
        raise ValueError(f"Not supported value of type {type(value)}!")

    return datetime.fromisoformat(value)


def convertTimeToSeconds(value: str) -> float:
    """
    Convert a timestamp as string to a timestamp in seconds.
    """
    if not isinstance(value, str):
        raise ValueError(f"Not supported value of type {type(value)}!")

    return datetime.fromisoformat(value).timestamp()


def convertSecondsToDateTime(value: Union[int, float]) -> Union[datetime, None]:
    """
    Converts a timestamp in seconds to a DateTime instance.
    """
    if not isinstance(value, (int, float)):
        raise ValueError(f"Not supported value of type {type(value)}!")

    return datetime.fromtimestamp(value)


def convertSecondsToTimeString(value: float) -> str:
    """
    Converts a timestamp in seconds to a timestamp as string.
    """
    if not isinstance(value, (int, float)):
        raise ValueError(f"Not supported value of type {type(value)}!")

    return time.strftime("%Y-%m-%d %H:%M:%S", convertSecondsToTime(value))


def convertMetersToFeet(value: float) -> float:
    """
    Converts a value given in 'meters' to 'feet'

    :param value:
    :return:
    """
    return value * 3.28084


def convertFeetToMeters(value: float) -> float:
    """
    Converts a value given in 'feet' to 'meters'

    :param value:
    :return:
    """
    return value * 0.3048
