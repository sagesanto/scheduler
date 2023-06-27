# Sage Santomenna 2023
import logging
import sys
from datetime import timedelta, datetime, timezone

import astroplan
import astropy.time
import pytz
from astral import LocationInfo
from astral import sun
from astropy import units as u
from astropy.coordinates import Angle
from astropy.time import Time
from abc import ABCMeta, abstractmethod


class ScheduleError(Exception):
    """Exception raised for user-facing errors in scheduling

    :param message: explanation of the error
    """

    def __init__(self, message="No candidates are visible tonight"):
        self.message = message
        super().__init__(self.message)


class TypeConfiguration(metaclass=ABCMeta):
    @abstractmethod
    def __init__(self, scorer: astroplan.Scorer, maxMinutesWithoutFocus=60, numObs=1, minMinutesBetweenObs=None):
        self.scorer = scorer
        self.maxMinutesWithoutFocus = maxMinutesWithoutFocus  # max time, in minutes, that this object can be scheduled after the most recent focus loop
        self.numObs = numObs
        self.minMinutesBetweenObs = minMinutesBetweenObs  # minimum time, in minutes, between the start times of multiple observations of the same object

    @abstractmethod
    def generateSchedulerLine(self, row, targetName, candidateDict):
        pass

    @abstractmethod
    def selectCandidates(self, startTimeUTC: datetime, endTimeUTC: datetime):
        pass

    @abstractmethod
    def generateTransitionDict(self):
        pass

    @abstractmethod
    def generateTypeConstraints(self):
        pass

    @abstractmethod
    def scoreRepeatObs(self, c, scoreLine, numPrev, currentTime):
        pass


def timeToString(dt, logger=None, scheduler=False):
    try:
        if isinstance(dt,
                      str):  # if we get a string, check that it's valid by casting it to dt. If it isn't, we'll return None
            dt = stringToTime(dt)
        return dt.strftime("%Y-%m-%d %H:%M:%S") if not scheduler else dt.strftime("%Y-%m-%dT%H:%M:%S.000")
    except:
        if logger:
            logger.error("Unable to coerce time from", dt)
        return None


class AutoFocus:
    def __init__(self, desiredStartTime):
        self.startTime = ensureDatetime(desiredStartTime)
        self.endTime = self.startTime + timedelta(minutes=5)

    def genLine(self):
        return "\n" + timeToString(self.startTime, scheduler=True) + "|1|Focus|0|0|0|0|0|CLEAR|'Refocusing'\n"

    @classmethod
    def fromLine(cls, line):
        time = line.split('|')[0]
        time = stringToTime(time)
        return cls(time)


def findCenterTime(startTime: datetime, duration: timedelta):
    """
    Find the nearest ten minute interval to the center of the time window {start, start+duration}
    :param startTime: datetime object representing the start of the window
    :param duration: timedelta representing the length of the window
    :return: datetime representing the center of the window, rounded to the nearest ten minutes
    """
    center = startTime + (duration / 2)
    return roundToTenMinutes(center)


def ensureDatetime(time, logger=None):
    if isinstance(time, datetime):
        return time
    if isinstance(time, str):
        try:
            stringToTime(time)
        except:
            if logger is not None:
                logger.error("Couldn't make datetime from string", time)
    if isinstance(time, astropy.time.Time):
        return time.to_datetime()


def stringToTime(timeString, logger=None, scheduler=False):
    if isinstance(timeString, datetime):  # they gave us a datetime, return it back to them
        return timeString
    try:
        return datetime.strptime(timeString, "%Y-%m-%d %H:%M:%S")
    except:
        try:
            return datetime.strptime(timeString, "%Y-%m-%d %H:%M:%S.%f")
        except Exception as e:
            print(repr(e))
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
    Return the decimal degree representation of an astropy Angle, as a float
    :return: Decimal degree representation, float
    """
    return round(float(angle.degree), 6)  # ew


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


def roundToTenMinutes(dt):
    dt += timedelta(minutes=5)
    return dt - timedelta(minutes=dt.minute % 10, seconds=dt.second, microseconds=dt.microsecond)


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
    return roundToTenMinutes(transitTime)


def getSunriseSunset():
    """
    get sunrise and sunset for tmo, as datetimes
    :return:
    """
    TMO = LocationInfo(name="TMO", region="CA, USA", timezone="UTC", latitude=34.36,
                       longitude=-117.63)

    s = sun.sun(TMO.observer, date=datetime.now(timezone.utc), tzinfo=timezone.utc)
    sunriseUTC = s["sunrise"]
    sunsetUTC = sun.time_at_elevation(TMO.observer, -10, direction=sun.SunDirection.SETTING)

    nowDt = datetime.utcnow()
    nowDt = pytz.UTC.localize(nowDt)

    # TODO: make this less questionable - it probably doesn't do exactly what i want it to when run at certain times of the day:
    if sunriseUTC < nowDt:  # if the sunrise we found is earlier than the current time, add one day to it (approximation ofc)
        sunriseUTC = sunriseUTC + timedelta(days=1)

    if sunsetUTC > sunriseUTC:
        sunsetUTC = sunsetUTC - timedelta(days=1)

    return sunriseUTC, sunsetUTC


def f(x):
    return round(float(x), 2)


def tS(time):
    return stringToTime(time).strftime("%H:%M") + " - "


def tE(time):
    return stringToTime(time).strftime("%H:%M")


def prettyFormat(candidateDf):
    """Format a candidate df to be more user friendly.

    :param candidateDf: The DataFrame containing the candidate information.
    :type candidateDf: pandas.DataFrame
    :returns: pandas.DataFrame
    """

    columns = ["CandidateName", "Processed", "Submitted", "Observability", "TransitTime", "RA",
               "Dec", "dRA", "dDec", "Magnitude",
               "RMSE", "ApproachColor"]

    formattedDf = candidateDf.copy()

    formattedDf["RA"] = formattedDf["RA"].apply(
        lambda x: (Angle(x, unit=u.degree) * 15).to_string(unit=u.hourangle, sep=" "))
    formattedDf["Dec"] = formattedDf["Dec"].apply(lambda x: Angle(x, unit=u.degree).to_string(unit=u.deg, sep=" "))

    formattedDf["RMSE"] = tuple(zip(formattedDf["RMSE_RA"].apply(f), formattedDf["RMSE_Dec"].apply(f)))
    formattedDf["Observability"] = formattedDf["StartObservability"].apply(tS) + formattedDf["EndObservability"].apply(
        tE)

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
        (-35, -34): (-35, 42.6104),
        (-34, -32): (-35, 45.9539),
        (-32, -30): (-35, 48.9586),
        (-30, -28): (-35, 51.6945),
        (-28, -26): (-35, 54.2121),
        (-26, -24): (-35, 56.5487),
        (-24, -22): (-35, 58.7332),
        (-22, 0): (-35, 60),
        (0, 46): (-52.5, 60),
        (46, 56): (-37.5, 60),
        (56, 65): (-30, 60)
    }
    for decRange in horizonBox:
        if decRange[0] < dec <= decRange[1]:  # man this is miserable
            finalDecRange = horizonBox[decRange]
            return tuple([Angle(finalDecRange[0], unit=u.deg), Angle(finalDecRange[1], unit=u.deg)])
    return None
