import time
from datetime import UTC, datetime
from typing import Any, Optional, Union


# For time conversions: Use UTC time only
def convertToFloat(value: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Convert value to a float or if not possible return a default value.

    Handles European-locale decimal commas (GitHub #159). Qt displays
    database values through the user's QLocale, so a SQLite string
    ``"30.3"`` can appear in a form field as ``"30,3"`` on a German/
    French/Italian machine. Bare ``float()`` then raises ``ValueError``.

    Handled cases (in priority order):
      - Native ``float`` / ``int``: returned as-is via ``float()``.
      - ``"30.3"`` → 30.3 (US decimal, plain ``float()``).
      - ``"30,3"`` → 30.3 (European decimal, single comma, no dot).
      - ``"1.234,56"`` → 1234.56 (European thousands + decimal).
      - ``"1,234.56"`` → 1234.56 (US thousands + decimal).

    Known limitation: ``"1,234"`` (no dot, comma with 3+ digits after)
    is genuinely ambiguous — could be US thousands (=1234) or a typo of
    European decimal (=1.234). The current heuristic treats comma as
    decimal when it's the only separator, which matches the scenario
    in the reporter's issue but would misparse US thousands without a
    decimal part. OpenALAQS form fields (heights, speeds, times, lat/
    lon) never legitimately cross 1000 without a decimal, so this is
    not expected in practice.

    :param value: a string, int, or float to convert
    :param default: returned if conversion fails or value is empty/None
    :return: the converted float or ``default``
    """
    if value is None or value == "":
        return default

    try:
        return float(value)  # float takes only string or float
    except (ValueError, TypeError):
        # Locale normalisation for strings only
        if not isinstance(value, str):
            return default
        s = value.strip()
        has_comma = "," in s
        has_dot = "." in s
        if not has_comma:
            return default  # already tried float(), no separator tricks left
        if not has_dot:
            # Only commas: interpret the LAST comma as decimal separator
            candidate = s.replace(",", ".")
            # If there were multiple commas, this introduces multiple dots
            # — in that case it's still invalid, float() will fail below.
            if candidate.count(".") > 1:
                # European-style with thousands dots? No — we already said no dots.
                # Multiple commas with no dots: likely garbage like "1,2,3".
                return default
        else:
            # Both separators present — last-one-is-decimal heuristic
            last_comma = s.rfind(",")
            last_dot = s.rfind(".")
            if last_dot > last_comma:
                # US-style: thousands=',', decimal='.'. Strip commas.
                candidate = s.replace(",", "")
            else:
                # European-style: thousands='.', decimal=','.
                candidate = s.replace(".", "").replace(",", ".")
        try:
            return float(candidate)
        except (ValueError, TypeError):
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
    return datetime.fromtimestamp(int(value), UTC).utctimetuple()


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
