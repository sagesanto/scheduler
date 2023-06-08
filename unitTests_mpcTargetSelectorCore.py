import unittest
from scheduleLib.mpcTargetSelectorCore import TargetSelector
from astropy.coordinates import Angle
from astropy import units as u
from scheduleLib import teleUtils

class Test(unittest.TestCase):

    def test_toDecimal(self):
        testAngle = Angle(107, unit=u.deg)
        result = teleUtils.toDecimal(testAngle)
        self.assertIsNotNone(result)
        self.assertEquals(result,107.0)

        testAngle = Angle(0, unit=u.deg)
        result = teleUtils.toDecimal(testAngle)
        self.assertIsNotNone(result)
        self.assertEquals(result, 0.0)

        testAngle = Angle(-31,unit=u.deg)
        result = teleUtils.toDecimal(testAngle)
        self.assertIsNotNone(result)
        self.assertEquals(result, -31.0)

    def test_ensureAngle(self):
        testAngle = Angle(284,unit=u.deg)
        self.assertEquals(teleUtils.ensureAngle(testAngle),testAngle)
        self.assertEquals(teleUtils.ensureAngle(284), testAngle)
        self.assertEquals(teleUtils.ensureAngle(284.0), testAngle)
        self.assertEquals(teleUtils.ensureAngle("284d"),testAngle)
        self.assertEquals(teleUtils.ensureAngle("284d0m0s"),testAngle)
        self.assertEqual(teleUtils.ensureAngle(teleUtils.toSexagesimal(testAngle)),testAngle)

    def test_ensureFloat(self):
        testAngle = Angle(107, unit=u.deg)
        self.assertEquals(teleUtils.ensureFloat(testAngle), 107.0)

        self.assertEquals(teleUtils.ensureFloat(0), 0.0)

        self.assertEquals(teleUtils.ensureFloat("-45"), -45)

    def test_getHourAngleLimits(self):
        print(teleUtils.getHourAngleLimits(23))
        print(type(teleUtils.getHourAngleLimits(23)))
        self.assertEqual(teleUtils.getHourAngleLimits(23),(Angle(-52.5,unit=u.deg),Angle(60,unit=u.deg)))

    def test_ObservabilityWindow(self):
        selector = TargetSelector()
        window1 = selector.calculateObservability("12h",23,0,0)
        print(window1)
        # objRA, objDec, dRA, dDec







