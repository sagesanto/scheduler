import astropy as astropy
import astropy.coordinates
import pytz

from scheduleLib import sCoreCondensed as sc, genUtils, mpcUtils
from scheduleLib.candidateDatabase import CandidateDatabase, Candidate
from scheduleLib.mpcTargetSelectorCore import TargetSelector

import astropy.units as u
from astropy.coordinates import EarthLocation
from pytz import timezone
from astroplan import Observer, AltitudeConstraint, AirmassConstraint, AtNightConstraint, TimeConstraint, is_observable, \
    is_always_observable, months_observable, FixedTarget, ObservingBlock, Transitioner, PriorityScheduler
from astroplan.scheduling import Schedule
from astropy.table import Table
from astropy.coordinates import SkyCoord
import astropy.units as u
import numpy as np
from astropy.time import Time
import astroplan.utils
from astral import LocationInfo, zoneinfo, sun, SunDirection
from datetime import datetime, timedelta, timezone

utc = pytz.UTC


# and the flags are all dead at the tops of their poles

class ObservabilityWindowConstraint(astroplan.Constraint):
    def __init__(self, candidateDict, boolean_constraint=True):
        self.booleanConstraint = boolean_constraint
        self.candidateDict = candidateDict

    def retrieveCandidateFromTarget(self, coord: astropy.coordinates.SkyCoord):
        coordTuple = (genUtils.ensureFloat(coord.ra), genUtils.ensureFloat(coord.dec))
        return self.candidateDict[coordTuple]

    def compute_constraint(self, times, observer, targets):
        print(targets)
        masks = []
        for target in targets:
            print(target)
            targetCandidate = self.retrieveCandidateFromTarget(target)
            expTime = timedelta(seconds=mpcUtils._findExposure(targetCandidate.Magnitude, str=False))
            obsMask = np.array([targetCandidate.isObservableBetween(time, time + expTime, expTime.days * 24) for time in
                                times.datetime])
            masks.append(obsMask)
        return np.array(masks)

        # this needs to return something that looks like this:


#             try:
#                 mask = np.array([min_time <= t.time() <= max_time for t in times.datetime])
#             except BaseException:                # use np.bool so shape queries don't cause problems
#                 mask = np.bool_(min_time <= times.datetime.time() <= max_time)


location = EarthLocation.from_geodetic(-117.6815, 34.3819, 0)
TMO = Observer(name='Table Mountain Observatory',
               location=location,
               timezone=utc,
               )  # timezone=pytz.timezone('US/Pacific')

sunriseUTC, sunsetUTC = genUtils.getSunriseSunset()

timeRange = Time([sunsetUTC, sunriseUTC])
#
# # Read in the table of targets
# target_table = Table.read('targets.txt', format='ascii.basic')

dbConnection = CandidateDatabase("./candidate database.db", "Night Obs Tool")

candidates = mpcUtils.candidatesForTimeRange(sunsetUTC, sunriseUTC, 1, dbConnection)

# candidateDict = {}
for c in candidates:
    c.RA = genUtils.ensureAngle(str(c.RA) + "h")
    c.Dec = genUtils.ensureAngle(float(c.Dec))
    # candidateDict[(c.RA, c.Dec)] = c

# create astroplan.FixedTarget objects for each one
# targets = [
#     FixedTarget(coord=SkyCoord(ra=genUtils.ensureAngle(c.RA), dec=genUtils.ensureAngle(c.Dec)), name=c.CandidateName)
#     for c in candidates]

# constraints = [ObservabilityWindowConstraint(candidateDict)]

# this is disgusting
timeConstraintDict = {c.CandidateName: TimeConstraint(Time(genUtils.stringToTime(c.StartObservability)),
                                                      Time(genUtils.stringToTime(c.EndObservability))) for c in
                      candidates}
print(timeConstraintDict)
# everObservable = astroplan.constraints.is_observable(constraints, TMO, targets, time_range=timeRange)

# Are targets *always* observable in the time range?
# alwaysObservable = is_always_observable(constraints, TMO, targets, time_range=timeRange)
blocks = []
for c in candidates:
    expTime = mpcUtils._findExposure(c.Magnitude, str=False) * u.second
    name = c.CandidateName
    target = FixedTarget(coord=SkyCoord(ra=c.RA, dec=c.Dec), name=name)
    print(name,target.coord)
    b = ObservingBlock(target, expTime, 0, configuration={"object": c.CandidateName},
                       constraints=[timeConstraintDict[name]])
    blocks.append(b)

slewRate = .8 * u.deg / u.second  # this is inaccurate and completely irrelevant. ignore it, we want a fixed min time between targets

transitioner = Transitioner(slewRate, {'object': {'default': 180 * u.second}})
priorityScheduler = PriorityScheduler(constraints=[], observer=TMO, transitioner=transitioner,time_resolution=5*u.minute)
schedule = Schedule(Time(sunsetUTC), Time(sunriseUTC))

print(blocks)
priorityScheduler(blocks, schedule)
print(schedule)
schedule.to_table(show_unused=False,show_transitions=False).pprint(max_width=2000)

# observabilityTable = Table()
#
# observabilityTable['candidate'] = [target.name for target in targets]
#
# # observabilityTable['everObservable'] = everObservable
# #
# # observabilityTable['alwaysObservable'] = alwaysObservable

# print(observabilityTable)
