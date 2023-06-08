#Sage Santomenna 2023

from astropy.coordinates import Angle
from astropy import units as u

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
    if not isinstance(angle, float):
        if isinstance(angle, Angle):
            angle = toDecimal(angle)
        else:
            angle = float(angle)
    return angle

def getHourAngleLimits(dec):
    """
    Get the hour angle limits of the target's observability window based on its dec.
    :param dec: float, int, or astropy Angle
    :return: A tuple of Angle objects representing the upper and lower hour angle limits
    """
    dec = ensureFloat(dec)

    horizonBox = {  # {range(decWindow):tuple(minAlt,maxAlt)}
        range(-38, -36): (0, 0),
        range(-36, -34): (-35, 42.6104),
        range(-34, -32): (-35, 45.9539),
        range(-32, -30): (-35, 48.9586),
        range(-30, -28): (-35, 51.6945),
        range(-28, -26): (-35, 54.2121),
        range(-26, -24): (-35, 56.5487),
        range(-24, -22): (-35, 58.7332),
        range(-22, 0): (-35, 60),
        range(0, 46): (-52.5, 60),
        range(46, 56): (-37.5, 60),
        range(56, 66): (-30, 60),
        range(66, 74): (0, 0)
    }
    for decRange in horizonBox:
        if dec in decRange:  # man this is miserable
            finalDecRange = horizonBox[decRange]
            return tuple([Angle(finalDecRange[0], unit=u.deg), Angle(finalDecRange[1], unit=u.deg)])
    return None