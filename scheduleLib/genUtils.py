# Sage Santomenna 2023
import sys, logging
from datetime import timedelta, datetime

import pandas as pd
from astropy.coordinates import Angle, SkyCoord
from astropy import units as u
from astropy.time import Time


class ScheduleError(Exception):
    """Exception raised for user-facing errors in scheduling

    :param message: explanation of the error
    """

    def __init__(self, message="No candidates are visible tonight"):
        self.message = message
        super().__init__(self.message)


def timeToString(dt, logger=None):
    try:
        if isinstance(dt,
                      str):  # if we get a string, check that it's valid by casting it to dt. If it isn't, we'll return None
            dt = stringToTime(dt)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        if logger:
            logger.error("Unable to coerce time from", dt)
        return None


def stringToTime(timeString, logger=None):
    if isinstance(timeString, datetime):  # they gave us a datetime, return it back to them
        return timeString
    try:
        return datetime.strptime(timeString, "%Y-%m-%d %H:%M:%S")
    except:
        if logger:
            logger.error("Unable to coerce time from", timeString)
        return None


def filter(record):
    info = sys.exc_info()
    if info[1]:
        logging.exception('Exception!', exc_info=info)
        print("---Exception!---", info)
        raise
    return True


def logAndPrint(msg, loggerMethod):
    loggerMethod(msg)  # logger method is a function like logger.info logger.error etc
    print(msg)


def toDecimal(angle: Angle):
    """
    Return the decimal representation of an astropy Angle, as a float
    :return: Decimal representation, float
    """
    return float(angle.to_string(decimal=True))  # ew


def toSexagesimal(angle: Angle):
    """
    Return the sexagesimal representation of an astropy angle, as a string
    :param angle:
    :return: string
    """
    return angle.to_string()


def ensureAngle(angle):
    """
    Return angle as an astropy Angle, converting if necessary
    :param angle: float, int, hms Sexagesimal string, hms tuple, or astropy Angle
    :return: angle, as an astropy Angle
    """
    if not isinstance(angle, Angle):
        try:
            if isinstance(angle, str) or isinstance(angle, tuple):
                angle = Angle(angle)
            else:
                angle = Angle(angle, unit=u.deg)
        except Exception as err:
            print("Error converting", angle, "to angle")
            raise err
    return angle


def ensureFloat(angle):
    """
    Return angle as an astropy Angle, converting if necessary
    :param angle: float or astropy Angle
    :return: decimal angle, as a float
    """
    try:
        if isinstance(angle, str) or isinstance(angle, tuple):
            angle = Angle(angle)
            return ensureFloat(angle)  # lol
    except:
        pass
    if isinstance(angle, float):
        return angle
    if isinstance(angle, Angle):
        return toDecimal(angle)
    else:
        return float(angle)
    return None


def findTransitTime(rightAscension: Angle, observatory):
    """Calculate the transit time of an object at the given observatory.

    :param rightAscension: The right ascension of the object as an astropy Angle
    :type rightAscension: Angle
    :param observatory: The observatory location.
    :type observatory: astropy.coordinates.LocationInfo
    :return: The rounded transit time of the object as a datetime object.
    :rtype: datetime.datetime
    """

    currentTime = datetime.utcnow().replace(second=0, microsecond=0)
    lst = Time(currentTime).sidereal_time('mean', longitude=observatory.longitude)
    ha = rightAscension - lst
    haTime = ha.to(u.hourangle)
    haHours, haMinutes, haSeconds = haTime.hms
    transitTime = currentTime + timedelta(hours=haHours, minutes=haMinutes, seconds=0)
    roundedTransitTime = transitTime + timedelta(minutes=5)
    roundedTransitTime -= timedelta(minutes=roundedTransitTime.minute % 10)

    return roundedTransitTime


def prettyFormat(candidateDf):
    """Format a candidate df to be more user friendly.

    :param candidateDf: The DataFrame containing the candidate information.
    :type candidateDf: pandas.DataFrame
    :returns: pandas.DataFrame
    """

    columns = ["CandidateName", "Processed", "Submitted", "TransitTime", "RA", "Dec", "dRA", "dDec", "Magnitude",
               "RMSE","ApproachColor"]

    formattedDf = candidateDf.copy()

    formattedDf["RA"] = formattedDf["RA"].apply(
        lambda x: (Angle(x, unit=u.degree) * 15).to_string(unit=u.hourangle, sep=" "))
    formattedDf["Dec"] = formattedDf["Dec"].apply(lambda x: Angle(x, unit=u.degree).to_string(unit=u.deg, sep=" "))

    formattedDf["RMSE"] = tuple(zip(formattedDf["RMSE_RA"], formattedDf["RMSE_Dec"]))

    formattedDf = formattedDf[columns].sort_values(by="RA")

    return formattedDf


def getHourAngleLimits(dec):
    """
    Get the hour angle limits of the target's observability window based on its dec.
    :param dec: float, int, or astropy Angle
    :return: A tuple of Angle objects representing the upper and lower hour angle limits
    """
    dec = ensureFloat(dec)

    horizonBox = {  # {tuple(decWindow):tuple(minAlt,maxAlt)}
        (-38, -36): (0, 0),
        (-36, -34): (-35, 42.6104),
        (-34, -32): (-35, 45.9539),
        (-32, -30): (-35, 48.9586),
        (-30, -28): (-35, 51.6945),
        (-28, -26): (-35, 54.2121),
        (-26, -24): (-35, 56.5487),
        (-24, -22): (-35, 58.7332),
        (-22, 0): (-35, 60),
        (0, 46): (-52.5, 60),
        (46, 56): (-37.5, 60),
        (56, 66): (-30, 60),
        (66, 74): (0, 0)
    }
    for decRange in horizonBox:
        if decRange[0] <= dec < decRange[1]:  # man this is miserable
            finalDecRange = horizonBox[decRange]
            return tuple([Angle(finalDecRange[0], unit=u.deg), Angle(finalDecRange[1], unit=u.deg)])
    return None
