#Sage Santomenna 2023
import asyncio
import unittest
from scheduleLib.mpcTargetSelectorCore import TargetSelector
from astropy.coordinates import Angle
from astropy import units as u
from scheduleLib import generalUtils

class Test(unittest.TestCase):

    def test_toDecimal(self):
        testAngle = Angle(107, unit=u.deg)
        result = generalUtils.toDecimal(testAngle)
        self.assertIsNotNone(result)
        self.assertEquals(result,107.0)

        testAngle = Angle(0, unit=u.deg)
        result = generalUtils.toDecimal(testAngle)
        self.assertIsNotNone(result)
        self.assertEquals(result, 0.0)

        testAngle = Angle(-31,unit=u.deg)
        result = generalUtils.toDecimal(testAngle)
        self.assertIsNotNone(result)
        self.assertEquals(result, -31.0)

    def test_ensureAngle(self):
        testAngle = Angle(284,unit=u.deg)
        self.assertEquals(generalUtils.ensureAngle(testAngle),testAngle)
        self.assertEquals(generalUtils.ensureAngle(284), testAngle)
        self.assertEquals(generalUtils.ensureAngle(284.0), testAngle)
        self.assertEquals(generalUtils.ensureAngle("284d"),testAngle)
        self.assertEquals(generalUtils.ensureAngle("284d0m0s"),testAngle)
        self.assertEqual(generalUtils.ensureAngle(generalUtils.toSexagesimal(testAngle)),testAngle)

    def test_ensureFloat(self):
        testAngle = Angle(107, unit=u.deg)
        self.assertEquals(generalUtils.ensureFloat(testAngle), 107.0)

        self.assertEquals(generalUtils.ensureFloat(0), 0.0)

        self.assertEquals(generalUtils.ensureFloat("-45"), -45)

    def test_getHourAngleLimits(self):
        print(generalUtils.getHourAngleLimits(23))
        print(type(generalUtils.getHourAngleLimits(23)))
        self.assertEqual(generalUtils.getHourAngleLimits(23),(Angle(-52.5,unit=u.deg),Angle(60,unit=u.deg)))

    def test_ObservabilityWindow(self):
        selector = TargetSelector()
        window1 = asyncio.run(selector.calculateObservability(["C9C2MX2","C440NCZ","P21FYod","C9C5672","C9AZCE2","C9C5GX2"]))
        print(window1)
        # objRA, objDec, dRA, dDec

