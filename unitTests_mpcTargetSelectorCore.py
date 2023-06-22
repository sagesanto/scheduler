# Sage Santomenna 2023
import asyncio
import unittest
from datetime import datetime
import random

import pytz

from scheduleLib.mpcTargetSelectorCore import TargetSelector
from astropy.coordinates import Angle, SkyCoord
from astropy import units as u
from astropy.time import Time
from scheduleLib import genUtils, mpcUtils


class Test(unittest.TestCase):

    def test_toDecimal(self):
        for i in range(1000):  # this test is cheap so we'll do it quite a few times
            randomDecimal = random.uniform(-360, 360)  # in this case we can use random inputs
            testAngle = Angle(randomDecimal, unit=u.deg)
            result = genUtils.toDecimal(testAngle)
            self.assertIsNotNone(result)  # assert statement, this should be true
            self.assertEquals(result, round(randomDecimal, 6))  # assert statement, this should be true

    def test_ensureAngle(self):
        testAngle = Angle(284, unit=u.deg)
        self.assertEquals(genUtils.ensureAngle(testAngle), testAngle)
        self.assertEquals(genUtils.ensureAngle(284), testAngle)
        self.assertEquals(genUtils.ensureAngle(284.0), testAngle)
        self.assertEquals(genUtils.ensureAngle("284d"), testAngle)
        self.assertEquals(genUtils.ensureAngle("284d0m0s"), testAngle)
        self.assertEqual(genUtils.ensureAngle(genUtils.toSexagesimal(testAngle)), testAngle)

    def test_ensureFloat(self):
        testAngle = Angle(107, unit=u.deg)
        self.assertEquals(genUtils.ensureFloat(testAngle), 107.0)

        self.assertEquals(genUtils.ensureFloat(0), 0.0)

        self.assertEquals(genUtils.ensureFloat("-45"), -45)

    def test_getHourAngleLimits(self):
        print(genUtils.getHourAngleLimits(23)[0].hms, genUtils.getHourAngleLimits(23)[1].hms)
        print(type(genUtils.getHourAngleLimits(23)))
        eastLimit, westLimit = genUtils.getHourAngleLimits(-39)
        print("HA limits for -39 dec are:")
        print(eastLimit)
        print(westLimit)
        self.assertEqual(genUtils.getHourAngleLimits(23), (Angle(-52.5, unit=u.deg), Angle(60, unit=u.deg)))

    def test_ObservabilityWindow(self):
        selector = TargetSelector()
        print(selector.observationViable(datetime.utcnow().replace(tzinfo=pytz.UTC), selector.siderealStart, 0.0))

        # window1 = asyncio.run(selector.calculateObservability(["C9C2MX2","C440NCZ","P21FYod","C9C5672","C9AZCE2","C9C5GX2"]))
        # print(window1)
        # objRA, objDec, dRA, dDec

    def test_VelocityExtraction(self):
        # (obsDatetime, coords, vMag, vRa, vDec, deltaErr)
        dRA, dDec = round(random.uniform(-100, 100), 3), round(random.uniform(-100, 100), 3)
        coords = SkyCoord("17 04 33.1 +09 32 46".strip(), unit=(u.hourangle, u.deg))
        testEphem = (Time(datetime.utcnow()), coords, 21, str(dRA), str(dDec))
        print(mpcUtils.dictFromEphemLine(testEphem))

    def test_transitTime(self):
        from astral import LocationInfo
        from astropy.time import Time
        TMO = LocationInfo(name="TMO", region="CA, USA", timezone="UTC", latitude=34.36,
                           longitude=-117.63)  # this is your LocationInfo object
        currentTime = datetime.utcnow().replace(second=0, microsecond=0)
        # here's how you can get the local sidereal time (lst) at runtime:
        lst = Time(currentTime).sidereal_time('mean', longitude=TMO.longitude)
        # and here's how you can call the function that needs to be tested,
        # in this case with the local sidereal time as the RA of the object:
        transitTime = genUtils.findTransitTime(Angle(lst), TMO)
        # ^ this will return a datetime object rounded to the nearest (?) ten minutes
        print("Current transit time =", transitTime)

    def test_timeToString(self):
        exampleString = "1993-12-30 11:10:00.00"
        # badExampleString = "shit"
        string = genUtils.stringToTime(exampleString)
        # badString = genUtils.stringToTime(badExampleString)
        print(string)

    def test_RiseSet(self):
        sunrise, sunset = genUtils.getSunriseSunset()
        sunriseString = genUtils.timeToString(sunrise)
        sunsetString = genUtils.timeToString(sunset)
        print("the sunrise and sunset are respectively:",  sunriseString, sunsetString)
