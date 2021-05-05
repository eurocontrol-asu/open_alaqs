from __future__ import absolute_import
import __init__

import time
import calendar
from datetime import datetime
import unicodedata

#for time conversions: Use UTC time only

def convertToFloat(value, default=None):
    try:
        if value is None:
            raise ValueError("Could not convert value 'None' to float.")
        return float(value) #float takes only string or float
    except ValueError:
        if not (default is None):
            return convertToFloat(default)
        return None
    return None

def convertToInt(value, default=None):
    try:
        if value is None:
            raise ValueError("Could not convert value 'None' to int.")
        return int(value)
    except ValueError:
        if not (default is None):
            return convertToInt(default)
        return None
    return None

def convertSecondsToTime(value, format_ = "%Y-%m-%d %H:%M:%S"):
    if value is None:
        return None
    return datetime.utcfromtimestamp(int(value)).strftime(format_)

def convertStringToTime(value, format_ = "%Y-%m-%d %H:%M:%S"):
    if not value:
        return None

    if isinstance(value, str):
        return time.strptime(value, format_)
    else:
        return None

def convertStringToDateTime(value, format_ = "%Y-%m-%d %H:%M:%S"):
    if not value:
        return None

    if isinstance(value, str):
        return datetime.strptime(value, format_)
    else:
        return None

def convertTimeToSeconds(value, format_ = "%Y-%m-%d %H:%M:%S"):
    if not value:
        return None

    if isinstance(value, str):
        return calendar.timegm(convertStringToTime(value, format_))
    elif isinstance(value, str):
        return convertTimeToSeconds(unicodedata.normalize('NFKD', value).encode('ascii','ignore'), format_)
    elif isinstance(value, datetime):
        return calendar.timegm(value.timetuple())
    elif isinstance(value, time.struct_time):
        return calendar.timegm(value)
    elif isinstance(value, int) or isinstance(value, float):
        return value
    else:
        return None

def convertSecondsToTime(value, format_ = "%Y-%m-%d %H:%M:%S"):
    if not value:
        return None

    if isinstance(value, int) or isinstance(value, float):
        return time.gmtime(value)
    else:
        return None

def convertSecondsToDateTime(value, format_ = "%Y-%m-%d %H:%M:%S"):
    if not value:
        return None

    if isinstance(value, int) or isinstance(value, float):
        return datetime.utcfromtimestamp(value)
    elif isinstance(value, str):
        return datetime.utcfromtimestamp(convertTimeToSeconds(value, format_))
    else:
        return None

def convertSecondsToTimeString(value, format_ = "%Y-%m-%d %H:%M:%S"):
    if not value:
        return None

    if isinstance(value, time.struct_time):
        return time.strftime(format_, value)
    elif isinstance(value, int) or isinstance(value, float):
        return time.strftime(format_, convertSecondsToTime(value,format_))
    else:
        return None

#converts a value given in 'meters' to 'feet'
def convertMetersToFeet(value):
    return value*3.28084
#converts a value given in 'feet' to 'meters'
def convertFeetToMeters(value):
    return value*0.3048