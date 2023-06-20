import astropy as astropy
import astropy.coordinates
import numpy
import pytz
from scheduleLib.genUtils import stringToTime, timeToString
from scheduleLib import sCoreCondensed as sc, genUtils, mpcUtils
from scheduleLib.candidateDatabase import CandidateDatabase, Candidate
from scheduleLib.mpcTargetSelectorCore import TargetSelector
from candidatesTonight import visualizeObservability
import astropy.units as u
from astropy.coordinates import EarthLocation
from pytz import timezone
from matplotlib import pyplot as plt
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


BLACK = [0, 0, 0]
RED = [255, 0, 0]
GREEN = [0, 255, 0]
BLUE = [0, 0, 255]
ORANGE = [255, 191, 0]
PURPLE = [221, 160, 221]


class MPCScorer(astroplan.Scorer):
    def __init__(self, *args, **kwargs):
        super(MPCScorer,self).__init__(*args, **kwargs)

    #this makes a score array over the entire schedule for all of the blocks and each Constraint in the .constraints of each block and in self.global_constraints.
    def create_score_array(self, time_resolution=1*u.minute):
        # score should be inversely proportional to (length of observable window / exposure time)
        start = self.schedule.start_time
        end = self.schedule.end_time
        times = astroplan.time_grid_from_range((start, end), time_resolution)
        scoreArray = numpy.zeros(shape=(len(self.blocks), len(times)))





class TMOScheduler(astroplan.scheduling.Scheduler):
    def __init__(self, *args, **kwargs):
        super(TMOScheduler, self).__init__(*args, **kwargs)

    # this will actually make the schedule
    def _make_schedule(self, blocks):
        # gather all the constraints on each block into a single attribute
        for b in blocks:
            if b.constraints is None:
                b._all_constraints = self.constraints
            else:
                b._all_constraints = self.constraints + b.constraints
            b.observer = self.observer  # set the observer (initialized by parent constructor)

def visualizeSchedule(scheduleTable: Table):
    schedule = scheduleTable.to_pandas()
    schedule = schedule.loc[(schedule["target"] != "TransitionBlock")]
    beginDt = stringToTime(schedule.iloc[0]["start time (UTC)"])
    endDt = stringToTime(schedule.iloc[len(schedule.index) - 1]["end time (UTC)"])
    print("Begin:", beginDt)
    print("End:", endDt)
    print(schedule.columns)
    print(schedule)
    xMin, xMax = beginDt.timestamp(), endDt.timestamp()
    notCandidates = ["TransitionBlock", "Unused Time"]

    # print(schedule["target"] not in notCandidates)
    targetNames = schedule.loc[(schedule["target"] != "Unused Time") & (schedule["target"] != "TransitionBlock")][
        "target"].tolist()
    print(targetNames)
    numTargets = len(targetNames)
    # numTargets = len(schedule.index)
    numColors = len(plt.cm.tab20.colors)
    print(numTargets)
    # Generate a list of colors using a loop
    colorDict = {}
    for i in range(numTargets):
        color = plt.cm.tab20(i if i not in (
            14, 17) else i + 1)  # going to use colors 14 and 17 (gray and yellow) for unused time and transition blocks
        colorDict[targetNames[i]] = color
    colorDict["Unused Time"] = plt.cm.tab20(14)
    colorDict["TransitionBlock"] = plt.cm.tab20(17)

    fig, ax = plt.subplots(figsize=(10, 4))
    for i in range(0, len(schedule.index)):
        row = schedule.iloc[i]
        startTime, endTime = stringToTime(row["start time (UTC)"]), stringToTime(row["end time (UTC)"])
        name = row["target"]

        startUnix = startTime.timestamp()
        endUnix = endTime.timestamp()

        # Calculate the duration of the observability window
        duration = endUnix - startUnix

        # Plot a rectangle representing the observability window
        ax.barh(0, duration, left=startUnix, height=0.6, color=colorDict[name])

        # Place the label at the center of the bar
        if name != "Unused Time":
            ax.text(max(startUnix + duration / 2, xMin + duration / 2), 0, '\n'.join(name), ha='center',
                    va='center' if name != "Unused Time" else "top", bbox={'facecolor': 'white', 'alpha': 0.75,
                                                                           'pad': 5})  # we use '\n'.join( ) to make the labels vertical

    # Set the x-axis limits based on start and end timestamps
    ax.set_xlim(xMin, xMax + (xMax - xMin) / 10)

    # Format x-axis labels as human-readable datetime
    def formatFunc(value, tickNumber):
        dt = datetime.utcfromtimestamp(value)
        return dt.strftime("%H:%M\n%d-%b")

    ax.xaxis.set_major_formatter(plt.FuncFormatter(formatFunc))

    # Set the x-axis label
    ax.set_xlabel("Time (UTC)")

    # Set the y-axis label

    # Adjust spacing
    plt.subplots_adjust(left=0.1, right=0.95, bottom=0.11, top=0.85)
    plt.suptitle("Schedule for " + datetime.utcfromtimestamp(xMin).strftime("%b %d, %Y"))
    plt.title(
        datetime.utcfromtimestamp(xMin).strftime("%b %d, %Y, %H:%M") + " to " + datetime.utcfromtimestamp(
            xMax).strftime(
            "%b %d, %Y, %H:%M"))

    # Show the plot
    plt.show()

    schedule.to_csv("schedule.csv")


# currently unused
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
        # ^ this ^ needs to return something that looks like this:   # this note might not be relevant anymore 6/19/2023
        # try:
        #     mask = np.array([min_time <= t.time() <= max_time for t in times.datetime])
        # except BaseException:                # use np.bool so shape queries don't cause problems
        #     mask = np.bool_(min_time <= times.datetime.time() <= max_time)


def createSchedule(candidates, startTime, endTime):
    candidates = candidates.copy()  # don't want to mess with the candidates passed in
    for c in candidates:
        c.RA = genUtils.ensureAngle(str(c.RA) + "h")
        c.Dec = genUtils.ensureAngle(float(c.Dec))

    # this is disgusting
    timeConstraintDict = {c.CandidateName: TimeConstraint(Time(stringToTime(c.StartObservability)),
                                                          Time(stringToTime(c.EndObservability))) for c in candidates}

    blocks = []
    for c in candidates:
        expTime = mpcUtils._findExposure(c.Magnitude, str=False) * u.second
        name = c.CandidateName
        target = FixedTarget(coord=SkyCoord(ra=c.RA, dec=c.Dec), name=name)
        b = ObservingBlock(target, expTime, 0, configuration={"object": c.CandidateName},
                           constraints=[timeConstraintDict[name]])
        blocks.append(b)

    slewRate = .8 * u.deg / u.second  # this is inaccurate and completely irrelevant. ignore it, we want a fixed min time between targets

    transitioner = Transitioner(slewRate, {'object': {'default': 180 * u.second}})
    priorityScheduler = PriorityScheduler(constraints=[], observer=TMO, transitioner=transitioner,
                                          time_resolution=5 * u.minute)
    schedule = Schedule(Time(startTime), Time(endTime))

    print(blocks)
    priorityScheduler(blocks, schedule)
    print(schedule)
    scheduleTable = schedule.to_table(show_unused=True)
    return scheduleTable, blocks, schedule  # maybe don't need to return all of this


if __name__ == "__main__":
    location = EarthLocation.from_geodetic(-117.6815, 34.3819, 0)
    TMO = Observer(name='Table Mountain Observatory',
                   location=location,
                   timezone=utc,
                   )  # timezone=pytz.timezone('US/Pacific')

    sunriseUTC, sunsetUTC = genUtils.getSunriseSunset()
    sunriseUTC -= timedelta(hours=1)  # to account for us closing the dome one hour before sunrise

    dbConnection = CandidateDatabase("./candidate database.db", "Night Obs Tool")

    candidates = mpcUtils.candidatesForTimeRange(sunsetUTC, sunriseUTC, 1, dbConnection)
    visualizeObservability(candidates, sunsetUTC, sunriseUTC)

    scheduleTable, _, _ = createSchedule(candidates, sunsetUTC, sunriseUTC)
    scheduleTable.pprint(max_width=2000)
    visualizeSchedule(scheduleTable)

    del dbConnection
