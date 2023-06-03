from scheduleLib import sCoreCondensed as sc
import astropy.units as u
from astropy.coordinates import EarthLocation
from pytz import timezone
from astroplan import Observer, AltitudeConstraint, AirmassConstraint, AtNightConstraint, is_observable, is_always_observable, months_observable, FixedTarget, ObservingBlock
from astropy.table import Table
from astropy.coordinates import SkyCoord
import astropy.units as u
import numpy as np
from astropy.time import Time
from astroplan.utils import time_grid_from_range

#and the flags are all dead at the tops of their poles

# class TmoAltitudeConstraint:
#     def __init__(self, boolean_constraint=True):
#         self.boolean_constraint = boolean_constraint
#
#         # This defines the min and max allowable altitude based on the target's dec
#
#         # TODO: Get EVERYONE to check this - if we fuck this up, it's all over
#         self.decToAltLimits = {  # {decWindow:range(minAlt,maxAlt)}
#             range(-38, -36): range(0, 0),
#             range(-36, -34): range(-35, 42.6104),
#             range(-34, -32): range(-35, 45.9539),
#             range(-32, -30): range(-35, 48.9586),
#             range(-30, -28): range(-35, 51.6945),
#             range(-28, -26): range(-35, 54.2121),
#             range(-26, -24): range(-35, 56.5487),
#             range(-24, -22): range(-35, 58.7332),
#             range(-22, 0): range(-35, 60),
#             range(0, 46): range(-52.5, 60),
#             range(56, 66): range(-30, 60),
#             range(66, 74): range(0, 0)
#         }
#
#     #this is gonna be so slow
#     def calculateLimits(self, times, observer, targets):
#         altitudeLimitDict = {}
#         for target in targets:
#             for decRange in self.decToAltLimits:
#                 if float(target.dec.to_string(decimal=True)) in decRange: #man this is miserable
#                     altitudeLimitDict[target] = self.decToAltLimits[decRange]
#                     break
#         return altitudeLimitDict
#
#     def compute_constraint(self, times, observer, targets):
#         altitudeLimitDict = self.calculateLimits(times,observer,targets)
#
#         for target in targets:
#             altaz = observer.altaz(times, target)
#             zenithAngle = altaz.zen #the return type of this is unclear atm - i think this is a list of zenith angles, one for each time
#             #now something clever needs to be done here that compares the zenith angle at each time and returns a boolean mask
#             zenMax =





location = EarthLocation.from_geodetic(-117.6815, 34.3819, 0)
TMO = Observer(name='Table Mountain Observatory',
               location=location,
               timezone=timezone('US/Pacific'),
               )

time_range = Time(["2023-06-01 20:00", "2023-06-02 04:45"])

# Read in the table of targets
target_table = Table.read('targets.txt', format='ascii.basic')

# Create astroplan.FixedTarget objects for each one in the table
targets = [FixedTarget(coord=SkyCoord(ra=ra*u.deg, dec=dec*u.deg), name=name)
           for name, ra, dec in target_table]

constraints = [AltitudeConstraint(10*u.deg, 90*u.deg),
               AirmassConstraint(5), AtNightConstraint.twilight_civil()]

ever_observable = is_observable(constraints, TMO, targets, time_range=time_range)

# Are targets *always* observable in the time range?
always_observable = is_always_observable(constraints, TMO, targets, time_range=time_range)


observability_table = Table()

observability_table['targets'] = [target.name for target in targets]

observability_table['ever_observable'] = ever_observable

observability_table['always_observable'] = always_observable

times = time_grid_from_range(time_range)
altaz = TMO.altaz(times, targets,grid_times_targets=True) #the returned value here is a skycoord object containing many lists and things
zenithAngle = altaz.zen #zenithAngle is an array that holds one array for each target. inside each target's array is a list of SkyCoord zenith angles, each corresponding to a time
print(altaz)
print(len(altaz))
print(type(altaz))
print(zenithAngle)
print(len(zenithAngle))
print(type(zenithAngle))
print(observability_table)
