import unittest
from mpcTargetSelectorCore import TargetSelector
from astropy.coordinates import Angle
from astropy import units as u

class Test(unittest.TestCase):

    def test_toDecimal(self):
        testAngle = Angle(107, unit=u.deg)
        result = TargetSelector.toDecimal(testAngle)
        self.assertIsNotNone(result)
        self.assertEquals(result,107.0)

        testAngle = Angle(0, unit=u.deg)
        result = TargetSelector.toDecimal(testAngle)
        self.assertIsNotNone(result)
        self.assertEquals(result, 0.0)

        testAngle = Angle(-31,unit=u.deg)
        result = TargetSelector.toDecimal(testAngle)
        self.assertIsNotNone(result)
        self.assertEquals(result, -31.0)

    def test_ensureAngle(self):
        testAngle = Angle(284,unit=u.deg)
        self.assertEquals(TargetSelector.ensureAngle(testAngle),testAngle)
        self.assertEquals(TargetSelector.ensureAngle(284), testAngle)
        self.assertEquals(TargetSelector.ensureAngle(284.0), testAngle)
        self.assertEquals(TargetSelector.ensureAngle("284d"),testAngle)
        self.assertEquals(TargetSelector.ensureAngle("284d0m0s"),testAngle)
        self.assertEqual(TargetSelector.ensureAngle(TargetSelector.toSexagesimal(testAngle)),testAngle)

    def test_ensureFloat(self):
        testAngle = Angle(107, unit=u.deg)
        self.assertEquals(TargetSelector.ensureFloat(testAngle), 107.0)

        self.assertEquals(TargetSelector.ensureFloat(0), 0.0)

        self.assertEquals(TargetSelector.ensureFloat("-45"), -45)

    def test_getHourAngleLimits(self):
        print(TargetSelector.getHourAngleLimits(23))
        print(type(TargetSelector.getHourAngleLimits(23)))
        self.assertEqual(TargetSelector.getHourAngleLimits(23),(Angle(-52.5,unit=u.deg),Angle(60,unit=u.deg)))

    def test_ObservabilityWindow(self):
        selector = TargetSelector()
        window1 = selector.calculateObservability("12h",23,0,0)
        print(window1)
        # objRA, objDec, dRA, dDec







