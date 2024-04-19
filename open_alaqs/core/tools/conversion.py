import calendar
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


def convertStringToDateTime(
    value: str, format_="%Y-%m-%d %H:%M:%S"
) -> Union[datetime, None]:
    """
    Convert a timestamp as string to datetime object.

    :param value:
    :param format_:
    :return:
    """
    if not value:
        return None

    if isinstance(value, str):
        return datetime.strptime(value, format_)
    return None


def convertTimeToSeconds(
    value: Union[str, datetime, tuple], format_="%Y-%m-%d %H:%M:%S"
) -> Union[float, None]:
    """
    Convert a timestamp as string, datetime object, or time tuple to a timestamp
    in seconds.

    :param value:
    :param format_:
    :return:
    """
    if not value:
        return None

    if isinstance(value, str):
        return calendar.timegm(convertStringToTime(value, format_))
    if isinstance(value, datetime):
        return calendar.timegm(value.timetuple())
    if isinstance(value, time.struct_time):
        return calendar.timegm(value)
    if isinstance(value, (int, float)):
        return value
    return None


def convertSecondsToDateTime(
    value: Union[str, float], format_: str = "%Y-%m-%d %H:%M:%S"
) -> Union[datetime, None]:
    """
    Converts a timestamp in seconds or as string to a DateTime instance.

    :param value:
    :param format_:
    :return:
    """
    if not value:
        return None

    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(value)
    if isinstance(value, str):
        return datetime.utcfromtimestamp(convertTimeToSeconds(value, format_))
    return None


def convertSecondsToTimeString(
    value: float, format_: str = "%Y-%m-%d %H:%M:%S"
) -> Union[str, None]:
    """
    Converts a timestamp in seconds to a string using the provided format.

    :param value:
    :param format_:
    :return:
    """
    if not value:
        return None

    if isinstance(value, time.struct_time):
        return time.strftime(format_, value)
    if isinstance(value, (int, float)):
        return time.strftime(format_, convertSecondsToTime(value))
    return None


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
