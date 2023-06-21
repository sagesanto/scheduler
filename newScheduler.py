import os
from inspect import getmembers, isfunction
import astropy as astropy
import astropy.coordinates
import numpy
import pytz
from astroplan.target import get_skycoord
from importlib import import_module
import scheduleLib.sCoreCondensed
from scheduleLib.genUtils import stringToTime, timeToString, roundToTenMinutes
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
from importlib.util import find_spec
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


class ScorerSwitchboard(astroplan.Scorer):
    def __init__(self, candidateDict, configDict, *args, **kwargs):
        self.candidateDict = candidateDict  # desig : candidate
        self.configDict = configDict  # candidate type : config for that type
        super(ScorerSwitchboard, self).__init__(*args, **kwargs)

    def create_score_array(self, time_resolution=1*u.minute):
        start = self.schedule.start_time
        end = self.schedule.end_time
        times = astroplan.time_grid_from_range((start, end), time_resolution)
        scoreArray = numpy.zeros(shape=(len(self.blocks), len(times))) # default is zero

        for candType in self.configDict.keys():  # process groups of blocks with the same type
            indices = np.where(np.array([block.configuration["type"] == candType for block in self.blocks]))
            blocksOfType = np.array(self.blocks)[indices]
            if blocksOfType.size == 0:
                continue
            try:
                scorer = self.configDict[candType].scorer(self.candidateDict, blocksOfType, self.observer, self.schedule,
                           global_constraints=self.global_constraints)
                modifiedRows = scorer.create_score_array(time_resolution)
                scoreArray[indices] = modifiedRows
            except Exception as e:
                print("score error:",e)
                scoreArray[indices] = self.genericScoreArray(blocksOfType, time_resolution)
        return scoreArray

    def genericScoreArray(self,blocks, time_resolution): # generate a generic array of scores for targets that we couldn't get custom scores for
        start = self.schedule.start_time
        end = self.schedule.end_time
        times = astroplan.time_grid_from_range((start, end), time_resolution)
        scoreArray = np.ones((len(blocks), len(times)))
        for i, block in enumerate(blocks):
            if block.constraints:
                for constraint in block.constraints:
                    appliedScore = constraint(self.observer, block.target,
                                               times=times)
                    scoreArray[i] *= appliedScore
        for constraint in self.global_constraints:
            scoreArray *= constraint(self.observer, get_skycoord([block.target for block in blocks]), times,
                                      grid_times_targets=True)
        return scoreArray




def getLastFocusTime(currentTime,schedule):  # this will need to be written to determine when the last focus was so the schedule knows when its first one needs to be
    return currentTime

def makeFocusBlock(currentTime):
    pass

class TMOScheduler(astroplan.scheduling.Scheduler):
    def __init__(self, candidateDict, configDict, *args, **kwargs):
        self.candidateDict = candidateDict
        self.configDict = configDict
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
        scorer = ScorerSwitchboard(self.candidateDict, self.configDict, blocks, self.observer, self.schedule,
                           global_constraints=self.constraints)
        scoreArray = scorer.create_score_array(self.time_resolution)  # this has dimensions (number of blocks, schedule length/time_resolution)
        print("\n")
        print(scoreArray.shape)
        print(np.max(scoreArray))
        startTime = self.schedule.start_time
        lastFocusTime = getLastFocusTime(startTime,None) # this is a placedholder right now, need to know how long before the beginning of our scheduling period the last SUCCESSFUL focus loop happened
        currentTime = startTime

        while currentTime < self.schedule.end_time:
            scheduled = False  # have we found a block for this slot? initially: no
            currentIdx = int((currentTime - startTime) / self.time_resolution)  # index corresponding to the currentTime, which advances each time we fill a slot
            # find the column for the current time, then find the index representing the block in that column with the highest score:
            sortedIdxs = np.flip(np.argsort(scoreArray[:,currentIdx]))
            # ^ un-reversed, this array would contain the indices that sort scoreArray from *least* to *greatest*
            vals = scoreArray[sortedIdxs, currentIdx]
            sortedIdxs = sortedIdxs[vals != 0]  # omit the indices that correspond to a zero value
            i = 0 # loop index
            print("In outer loop at time",currentTime)
            while i < len(sortedIdxs) and scheduled is False:
                print("entered inner loop")
                # allValidBlocks = blocks[sortedIdxs]
                # for b in allValidBlocks:  # this is too slow.
                #     transition = self.transitioner(self.schedule.observing_blocks[-1],
                #                                    b, currentTime, self.observer)
                #     vectorizedSort = np.vectorize(lambda coord: dist(1, 1, coord[0], coord[1]))(allValidBlock)
                #     shortestIndices = np.argsort(vectorizedSort) # indices sorted by shortest total duration
                #     arr = np.array(arr)[arr3]
                #     shortestBlock = min({b.duration: b for b in
                #                          blocks})  # we calculate what the shortest block is for focus loop reasons
                #     minDuration = blocks.sort()
                j = sortedIdxs[i]  # this is the index of the block that we're trying. we try in order of score
                block = blocks[j]


                # the schedule starts with only 1 slot
                if len(self.schedule.slots) == 1:
                    testTime = currentTime
                # when a block is inserted, the number of slots increases
                else:
                    # a test transition between the last scheduled block and this one
                    transition = self.transitioner(self.schedule.observing_blocks[-1],
                                                   block, currentTime, self.observer)
                    testTime = currentTime + transition.duration

                # if testTime - lastFocusTime > timedelta(minutes=block.configuration.): # the shortest an observation can be is 8 minutes - if it's been more than 52 minutes since the last
                #     if self.schedule.end_time - testTime > timedelta(minutes=15): # min
                #         focusBlock = makeFocusBlock()
                #         transitionBlock = self.transitioner(self.schedule.observing_blocks[-1],
                #                                        focusBlock, currentTime, self.observer)
                #         if len(self.schedule.slots) > 1:
                #             self.schedule.insert_slot(currentTime, transition)
                #         testTime = currentTime + transition.duration

                # how many time intervals are we from the start
                start_idx = int((testTime - startTime) / self.time_resolution)
                duration_idx = int(block.duration / self.time_resolution)
                # if any score during the block's duration would be 0, reject it
                if any(scoreArray[j][start_idx:start_idx + duration_idx] == 0) or testTime+block.duration > self.schedule.end_time:
                    i += 1
                # if all of the scores are >0, accept and schedule it
                else:
                    if len(self.schedule.slots) > 1:
                        self.schedule.insert_slot(currentTime, transition)
                    self.schedule.insert_slot(testTime, block)
                    # advance the time and remove the block from the list
                    currentTime = testTime + block.duration
                    scheduled = True
                    print("Scheduled",block.target.name,"at",testTime)
                    blocks.remove(block)
                    scoreArray = np.delete(scoreArray, j, 0)
            # if every block failed, progress the time
            if i == len(sortedIdxs):
                print("finding block for time",currentTime,"failed D:")
                currentTime += self.gap_time
        print("All done!")
        return self.schedule


def visualizeSchedule(scheduleTable: Table, startDt=None, endDt=None):
    designations = [candidate.CandidateName for candidate in candidates]
    candidateDict = dict(zip(designations, candidates))
    schedule = scheduleTable.to_pandas()
    schedule = schedule.loc[(schedule["target"] != "TransitionBlock")]
    if startDt is None:
        startDt = stringToTime(schedule.iloc[0]["start time (UTC)"])
    if endDt is None:
        endDt = stringToTime(schedule.iloc[len(schedule.index) - 1]["end time (UTC)"])

    xMin, xMax = (startDt+timedelta(hours=7)).timestamp(), (endDt+timedelta(hours=7)).timestamp()

    targetNames = schedule.loc[(schedule["target"] != "Unused Time") & (schedule["target"] != "TransitionBlock")][
        "target"].tolist()
    numTargets = len(targetNames)
    # numTargets = len(schedule.index)
    numColors = len(plt.cm.tab20.colors)
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
    ax.set_xlim(xMin, xMax)

    # Format x-axis labels as human-readable datetime
    def formatFunc(value, tickNumber):
        dt = datetime.fromtimestamp(value)
        return dt.strftime("%H:%M\n%d-%b")

    ax.xaxis.set_major_formatter(plt.FuncFormatter(formatFunc))

    # Set the x-axis label
    ax.set_xlabel("Time (UTC)")

    # Set the y-axis label

    ax.set_yticks([])
    # Adjust spacing
    plt.subplots_adjust(left=0.1, right=0.95, bottom=0.11, top=0.85)
    plt.suptitle("Schedule for " + startDt.strftime("%b %d, %Y"))
    plt.title(
        startDt.strftime("%b %d, %Y, %H:%M") + " to " + endDt.strftime(
            "%b %d, %Y, %H:%M"))

    # Show the plot
    plt.show()

    schedule.to_csv("schedule.csv")


def createSchedule(candidates, startTime, endTime):
    # candidates = candidates.copy()  # don't want to mess with the candidates passed in

    configs = {}
    # import configurations from python files placed in the schedulerConfigs folder

    files = os.listdir("schedulerConfigs")
    print(files)
    files = ["schedulerConfigs."+f[:-3] for f in os.listdir("./schedulerConfigs") if f[-3:] == ".py" and "init" not in f]
    print(files)
    for file in files:
        module = import_module(file,"schedulerConfigs")
        print(module)
        print(dir(module))
        print(getmembers(module), isfunction)
        typeName, conf = module.getConfig(startTime,endTime)
        configs[typeName] = conf

    candidates = [candidate for candidateList in [c.selectedCandidates for c in configs.values()] for candidate in candidateList]  # turn the lists of candidates into one list

    for c in candidates:
        c.RA = genUtils.ensureAngle(str(c.RA) + "h")
        c.Dec = genUtils.ensureAngle(float(c.Dec))
    designations = [candidate.CandidateName for candidate in candidates]
    candidateDict = dict(zip(designations, candidates))
    # this is disgusting
    timeConstraintDict = {c.CandidateName: TimeConstraint(Time(stringToTime(c.StartObservability)),
                                                          Time(stringToTime(c.EndObservability))) for c in candidates}

    typeSpecificConstraints = {}
    for typeName, conf in configs.items():
        typeSpecificConstraints[typeName] = conf.typeConstraints # dictionary of {type of target: list of astroplan constraints, initialized}


    blocks = []
    for c in candidates:
        exposureDuration = float(c.NumExposures)*float(c.ExposureTime)
        name = c.CandidateName
        specConstraints = typeSpecificConstraints[c.CandidateType]
        aggConstraints = [timeConstraintDict[name]]
        if specConstraints is not None:
            aggConstraints += specConstraints
        target = FixedTarget(coord=SkyCoord(ra=c.RA, dec=c.Dec), name=name)
        b = ObservingBlock(target, exposureDuration * u.second, 0, configuration={"object": c.CandidateName,"type":c.CandidateType, "duration":exposureDuration,"candidate":c},
                           constraints=aggConstraints)
        blocks.append(b)

    slewRate = .8 * u.deg / u.second  # this is inaccurate and completely irrelevant. ignore it, we want a fixed min time between targets
    objTransitionDict = {'default': 180 * u.second}
    for conf in configs.values():  # accumulate dictionary of tuples (CandidateName1,CandidateName2)that specifies how long a transition between object1 and object2 should be
        for objNames, val in conf.transitionDict.items():
            objTransitionDict[objNames] = val

    transitioner = Transitioner(slewRate, {'object': objTransitionDict})
    # priorityScheduler = PriorityScheduler(constraints=[], observer=TMO, transitioner=transitioner,
    #                                       time_resolution=5 * u.minute)
    tmoScheduler = TMOScheduler(candidateDict, configs, constraints=[], observer=TMO, transitioner=transitioner,
                                time_resolution=1 * u.minute)

    schedule = Schedule(Time(startTime), Time(endTime))

    # priorityScheduler(blocks, schedule)
    tmoScheduler(blocks, schedule)
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
    sunriseUTC, sunsetUTC = roundToTenMinutes(sunriseUTC), roundToTenMinutes(sunsetUTC)
    sunriseUTC -= timedelta(hours=1)  # to account for us closing the dome one hour before sunrise

    dbConnection = CandidateDatabase("./candidate database.db", "Night Obs Tool")

    candidates = mpcUtils.candidatesForTimeRange(sunsetUTC, sunriseUTC, 1, dbConnection)

    scheduleTable, _, _ = createSchedule(candidates, sunsetUTC, sunriseUTC)
    scheduleTable.pprint(max_width=2000)
    visualizeSchedule(scheduleTable, sunsetUTC, sunriseUTC)

    del dbConnection
