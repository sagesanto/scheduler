import os
import queue
import copy
from inspect import getmembers, isfunction
import astropy as astropy
import astropy.coordinates
import numpy
import pandas
import pandas as pd
import pytz
from astroplan.target import get_skycoord
from importlib import import_module
import random
from matplotlib.colors import ListedColormap

import scheduleLib.sCoreCondensed
from scheduleLib.genUtils import stringToTime, timeToString, roundToTenMinutes
from scheduleLib import sCoreCondensed as sc, genUtils, mpcUtils
from scheduleLib.candidateDatabase import CandidateDatabase, Candidate
from scheduleLib.mpcTargetSelectorCore import TargetSelector
from candidatesTonight import visualizeObservability
import astropy.units as u
import seaborn as sns
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

focusLoopLenSeconds = 300


class ScorerSwitchboard(astroplan.Scorer):
    def __init__(self, candidateDict, configDict, temperature, *args, **kwargs):
        self.candidateDict = candidateDict  # desig : candidate
        self.configDict = configDict  # candidate type : config for that type\
        self.temperature = temperature
        super(ScorerSwitchboard, self).__init__(*args, **kwargs)

    def create_score_array(self, time_resolution=1 * u.minute):
        start = self.schedule.start_time
        end = self.schedule.end_time
        times = astroplan.time_grid_from_range((start, end), time_resolution)
        scoreArray = numpy.zeros(shape=(len(self.blocks), len(times)))  # default is zero

        for candType in self.configDict.keys():  # process groups of blocks with the same type
            indices = np.where(np.array([block.configuration["type"] == candType for block in self.blocks]))
            blocksOfType = np.array(self.blocks)[indices]
            if blocksOfType.size == 0:
                continue
            try:
                scorer = self.configDict[candType].scorer(self.candidateDict, blocksOfType, self.observer,
                                                          self.schedule,
                                                          global_constraints=self.global_constraints)
                modifiedRows = scorer.create_score_array(time_resolution) * round(
                    random.uniform(1 - self.temperature, 1 + self.temperature), 3)
                scoreArray[indices] = modifiedRows
            except Exception as e:
                raise e
                print("score error:", e)
                scoreArray[indices] = self.genericScoreArray(blocksOfType, time_resolution) * round(
                    random.uniform(1 - self.temperature, 1 + self.temperature), 3)
        return scoreArray

    def genericScoreArray(self, blocks,
                          time_resolution):  # generate a generic array of scores for targets that we couldn't get custom scores for
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


def getLastFocusTime(currentTime,
                     schedule):  # this will need to be written to determine when the last focus was so the schedule knows when its first one needs to be
    return currentTime


def makeFocusBlock():
    dummyTarget = FixedTarget(coord=SkyCoord(ra=0 * u.deg, dec=0 * u.deg), name="Focus")
    return ObservingBlock(dummyTarget, focusLoopLenSeconds * u.second, 0,
                          configuration={"object": "Focus", "type": "Focus",
                                         "duration": focusLoopLenSeconds},
                          constraints=None)


class TMOScheduler(astroplan.scheduling.Scheduler):
    def __init__(self, candidateDict, configDict, temperature, *args, **kwargs):
        self.candidateDict = candidateDict  # {desig: candidate object} - technically could be constructed from list of blocks, but i think we need it in the function that initializes this object anyway
        self.configDict = configDict  # {type of candidate (block.configuration["type"]) : TypeConfiguration object}
        self.temperature = temperature
        super(TMOScheduler, self).__init__(*args, **kwargs)  # initialize rest of schedule with normal arguments

    # this will actually make the schedule
    def _make_schedule(self, blocks):
        # gather all the constraints on each block into a single attribute:
        for b in blocks:
            if b.constraints is None:
                b._all_constraints = self.constraints
            else:
                b._all_constraints = self.constraints + b.constraints
            b.observer = self.observer  # set the observer (location and timezone info stuff) (one of the arguments to the constructor that is passed to the parent constructor)

        scorer = ScorerSwitchboard(self.candidateDict, self.configDict, self.temperature, blocks, self.observer,
                                   self.schedule,
                                   global_constraints=self.constraints)  # initialize our scorer object, which will calculate a score for each object at each time slot in the schedule
        scoreArray = scorer.create_score_array(
            self.time_resolution)  # this calculates the scores for the blocks at each time, returning a numpy array with dimensions (rows: number of blocks, columns: schedule length/time_resolution (time slots) )
        # if an element in the array is zero, it means the row's corresponding object does not meet all the constraints at the column's corresponding time

        for b in blocks:
            if self.configDict[b.configuration["type"]].numObs > 1:
                b.target.name += "_1"
                b.configuration["object"] += "_1"

        startTime = self.schedule.start_time
        lastFocusTime = getLastFocusTime(startTime, None)
        # ^ this is a placedholder right now, need to know how long before the beginning of our scheduling period the last SUCCESSFUL focus loop happened
        currentTime = startTime

        while currentTime < self.schedule.end_time:
            scheduledDict = {b.target.name.split("_")[0]: b.start_time for b in self.schedule.observing_blocks}
            scheduledNames = [b.target.name.split("_")[0] for b in self.schedule.observing_blocks]
            prospectiveDict = {}
            # print("Trying", len(blocks) - len(scheduledNames), "blocks for time", currentTime)
            # print("scheduled names:",scheduledNames)
            # print([b.target.name for b in blocks])
            # print([b.target.name for b in self.schedule.observing_blocks])
            for i, block in enumerate(blocks):
                config = self.configDict[block.configuration["type"]]
                if block in self.schedule.observing_blocks:
                    # print("Already scheduled", block.target.name)
                    continue
                focused = False
                runningTime = currentTime
                schedQueue = queue.Queue(maxsize=5)
                T1 = None
                if len(self.schedule.slots) != 1:
                    T1 = self.transitioner(self.schedule.observing_blocks[-1], block, currentTime, self.observer)
                    if T1 is not None:  # transition needed
                        schedQueue.put(T1)
                        runningTime = T1.end_time
                if runningTime - lastFocusTime > timedelta(minutes=config.maxMinutesWithoutFocus):  # focus loop needed
                    focusBlock = makeFocusBlock()
                    if T1 is not None:
                        _ = schedQueue.get()  # get rid of the transition, we need a focus loop instead
                        runningTime = currentTime
                    if runningTime > self.schedule.end_time:
                        # print("Not enough time to schedule", block.target.name)
                        continue
                    T2 = None
                    if len(self.schedule.slots) != 1:
                        T2 = self.transitioner(self.schedule.observing_blocks[-1], focusBlock, runningTime,
                                               self.observer)
                    if T2 is not None:
                        schedQueue.put(T2)
                        runningTime += T2.duration
                    schedQueue.put(focusBlock)
                    runningTime += focusBlock.duration
                    focused = True
                    if runningTime > self.schedule.end_time:
                        continue
                runningIdx = int((currentTime - startTime) / self.time_resolution)
                durationIdx = int(block.duration / self.time_resolution)
                # if any score during the block's duration would be 0, reject it
                if any(scoreArray[i][
                       runningIdx:runningIdx + durationIdx] == 0) or runningTime + block.duration > self.schedule.end_time:
                    continue
                if block.target.name[:-2] in scheduledDict.keys():
                    if config.minMinutesBetweenObs:
                        if runningTime - scheduledDict[block.target.name[:-2]] < timedelta(
                                minutes=config.minMinutesBetweenObs):
                            # print("Skipping", block.target.name, "at time", currentTime,
                            #       "because it's too close to the last occurrence at",
                            #       scheduledDict[block.target.name[:-2]])
                            continue
                schedQueue.put(block)
                score = scoreArray[i, runningIdx]
                prospectiveDict[score * 0.8 if focused else score] = schedQueue

            if not len(prospectiveDict):
                currentTime += self.gap_time
                # print("No blocks found for", currentTime)
                continue

            maxIdx = max(prospectiveDict.keys())
            bestQueue = prospectiveDict[maxIdx]
            # print(prospectiveDict)
            # print(maxIdx)
            # print(bestQueue)
            for i in range(bestQueue.qsize()):
                b = bestQueue.get()
                if isinstance(b, ObservingBlock) and b.target.name == "Focus":
                    lastFocusTime = currentTime
                self.schedule.insert_slot(currentTime, b)
                currentTime += b.duration
            justInserted = self.schedule.observing_blocks[-1]
            # print("Scheduled", justInserted.target.name, "at", currentTime)
            config = self.configDict[justInserted.configuration["type"]]
            numPrev = len([i for j, i in enumerate(scheduledNames) if i == justInserted.target.name[:-2]])
            if numPrev < config.numObs - 1:
                justIdx = blocks.index(justInserted)  # very efficient
                newArr = scoreArray[justIdx, :] * 10
                scoreArray = np.r_[scoreArray, [newArr]]
                # print("Considering additional observation of", justInserted.target.name, "which has", numPrev,
                #       "previous observations")
                blockCopy = copy.deepcopy(justInserted)
                # print(len(blocks))
                blockCopy.target.name = blockCopy.target.name[:-2] + "_" + str(numPrev + 2)
                blockCopy.configuration["object"] = blockCopy.target.name[:-2] + "_" + str(numPrev + 2)
                blocks.append(blockCopy)
                # print(len(blocks))
            continue

        # print("All done!")
        return self.schedule


def visualizeSchedule(scheduleDf: pd.DataFrame, startDt=None, endDt=None, full=None, temp=None):
    schedule = scheduleDf.loc[(scheduleDf["target"] != "TransitionBlock")]
    if startDt is None:
        startDt = stringToTime(schedule.iloc[0]["start time (UTC)"])
    if endDt is None:
        endDt = stringToTime(schedule.iloc[len(schedule.index) - 1]["end time (UTC)"])

    xMin, xMax = (startDt + timedelta(hours=7)).timestamp(), (endDt + timedelta(hours=7)).timestamp()

    xTicks = []
    val = xMax - xMax % 3600
    while val > xMin:
        xTicks.append(val)
        val -= 3600

    targetNames = schedule.loc[(schedule["target"] != "Unused Time") & (schedule["target"] != "TransitionBlock")][
        "target"].tolist()
    targetNames = list(set([t[:-2] if "_" in t else t for t in targetNames]))
    numTargets = len(targetNames)
    # numTargets = len(schedule.index)
    sbPalette = sns.color_palette("hls", numTargets)
    cmap = ListedColormap(sns.color_palette(sbPalette).as_hex())
    # Generate a list of colors using a loop
    colorDict = {}
    for i in range(numTargets):
        color = cmap(i)
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
        ax.barh(0, duration, left=startUnix, height=0.6, color=colorDict[name[:-2] if "_" in name else name],
                edgecolor="black")

        # Place the label at the center of the bar
        if name != "Unused Time" and name != "Focus":
            ax.text(max(startUnix + duration / 2, xMin + duration / 2), 0, '\n'.join(name), ha='center',
                    va='center' if name != "Focus" else "top", bbox={'facecolor': 'white', 'alpha': 0.75,
                                                                     'pad': 3})  # we use '\n'.join( ) to make the labels vertical

    # Set the x-axis limits based on start and end timestamps
    ax.set_xlim(xMin, xMax)

    # Format x-axis labels as human-readable datetime
    def formatFunc(value, tickNumber):
        dt = datetime.fromtimestamp(value)
        return dt.strftime("%H:%M\n%d-%b")

    ax.xaxis.set_major_formatter(plt.FuncFormatter(formatFunc))
    ax.set_xticks(xTicks)
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


def createSchedule(startTime, endTime):
    # candidates = candidates.copy()  # don't want to mess with the candidates passed in
    configDict = {}

    # import configurations from python files placed in the schedulerConfigs folder
    files = os.listdir("schedulerConfigs")
    files = ["schedulerConfigs." + f[:-3] for f in os.listdir("./schedulerConfigs") if
             f[-3:] == ".py" and "init" not in f]
    # maybe wrap this in a try?:
    for file in files:
        module = import_module(file, "schedulerConfigs")
        typeName, conf = module.getConfig(startTime, endTime)
        configDict[typeName] = conf

    candidates = [candidate for candidateList in [c.selectedCandidates for c in configDict.values()] for candidate in
                  candidateList]  # turn the lists of candidates into one list

    if len(candidates) == 0:
        print("No candidates provided - nothing to schedule. Exiting.")
        exit()
    for c in candidates:
        c.RA = genUtils.ensureAngle(str(c.RA) + "h")
        c.Dec = genUtils.ensureAngle(float(c.Dec))

    designations = [candidate.CandidateName for candidate in candidates]
    candidateDict = dict(zip(designations, candidates))

    # constraint on when the observation can *start*
    timeConstraintDict = {c.CandidateName: TimeConstraint(Time(stringToTime(c.StartObservability)),
                                                          Time(stringToTime(c.EndObservability) - timedelta(
                                                              seconds=float(c.NumExposures) * float(c.ExposureTime))))
                          for c in candidates}
    typeSpecificConstraints = {}  # make a dict of constraints to put on all targets of a given type (specified by specs (config) py file)
    for typeName, conf in configDict.items():
        typeSpecificConstraints[
            typeName] = conf.typeConstraints  # dictionary of {type of target: list of astroplan constraints, initialized}

    print("Candidates:", candidates)
    blocks = []
    for c in candidates:
        exposureDuration = float(c.NumExposures) * float(c.ExposureTime)
        name = c.CandidateName
        specConstraints = typeSpecificConstraints[c.CandidateType]
        aggConstraints = [timeConstraintDict[name]]
        if specConstraints is not None:
            aggConstraints += specConstraints
        target = FixedTarget(coord=SkyCoord(ra=c.RA, dec=c.Dec), name=name)
        b = ObservingBlock(target, exposureDuration * u.second, 0,
                           configuration={"object": c.CandidateName, "type": c.CandidateType,
                                          "duration": exposureDuration, "candidate": c},
                           constraints=aggConstraints)
        blocks.append(b)

    slewRate = .8 * u.deg / u.second  # this is inaccurate and completely irrelevant. ignore it, we want a fixed min time between targets
    objTransitionDict = {'default': 180 * u.second}
    for conf in configDict.values():  # accumulate dictionary of tuples (CandidateName1,CandidateName2)that specifies how long a transition between object1 and object2 should be
        for objNames, val in conf.transitionDict.items():
            objTransitionDict[objNames] = val

    transitioner = Transitioner(slewRate, {'object': objTransitionDict})

    # tmoScheduler = TMOScheduler(candidateDict, configDict, 0, constraints=[], observer=TMO, transitioner=transitioner,
    #                             time_resolution=1 * u.minute, gap_time=1 * u.minute)

    schedule = Schedule(Time(startTime), Time(endTime))

    temperature = 0
    logDf = pd.DataFrame(columns=["Temperature", "Fullness"])
    # for i in range(10):
    #     for i in range(20):
    tmoScheduler = TMOScheduler(candidateDict, configDict, temperature, constraints=[], observer=TMO,
                                transitioner=transitioner,
                                time_resolution=20 * u.second, gap_time=1 * u.minute)
    schedule = copy.deepcopy(Schedule(Time(startTime), Time(endTime)))
    tmoScheduler(copy.deepcopy(blocks), schedule)  # do the scheduling (modifies schedule inplace)
    print(schedule)
    scheduleDf = schedule.to_table(show_unused=True).to_pandas()
    # print(scheduleDf.dtypes)
    # print("Columns:", scheduleDf.columns)
    # print(scheduleDf.info)
    # print(scheduleDf.to_string())
    unused = scheduleDf.loc[scheduleDf["target"] == "Unused Time"]["duration (minutes)"].sum()
    total = scheduleDf["duration (minutes)"].sum()
    fullness = 1 - (unused / total)
    print("Schedule is " + str(fullness * 100) + "% full")

    # print("Temp", temperature, "#" + str(i)+ ":", str(fullness * 100) + "% full")
    # newRow = dict(zip(logDf.columns, [temperature, fullness]))
    # logDf.loc[len(logDf)] = newRow
    visualizeSchedule(scheduleDf, startTime, endTime, fullness, temp=temperature)
    # temperature += 10
    schedLines = scheduleToTextFile(scheduleDf, configDict, candidateDict)
    with open("schedule.txt", "w") as f:
        f.writelines(schedLines)

    # logDf.to_csv("TempVsFullness.csv")
    return scheduleDf, blocks, schedule  # maybe don't need to return all of this


def lineConverter(row: pd.Series, configDict, candidateDict, runningList:list):
    targetName = row[0]

    if targetName in ["Unused Time", "TransitionBlock"]:
        return
    runningList.append("\n")
    if targetName == "Focus":
        targetStart = stringToTime(row[1])
        runningList.append(scheduleLib.genUtils.AutoFocus(targetStart).genLine())
        return

    try:
        runningList.append(configDict[row["configuration"]["type"]].generateLine(row, targetName, candidateDict))
    except Exception as e:
        raise e
        raise ValueError("Object "+str(targetName)+" doesn't have a schedule line generator. "+str(row))

def scheduleToTextFile(scheduleDf, configDict, candidateDict, prevSched=None):
    # each target type will need to have the machinery to turn an entry from the scheduleDf + the candidateDict into a
    # scheduler line - maybe we'll make a default version later
    linesList = ["DateTime|Occupied|Target|Move|RA|Dec|ExposureTime|#Exposure|Filter|Description"]
    scheduleDf.apply(lambda row: lineConverter(row, configDict, candidateDict, runningList=linesList), axis=1)
    print(linesList)
    return linesList

if __name__ == "__main__":
    location = EarthLocation.from_geodetic(-117.6815, 34.3819, 0)
    TMO = Observer(name='Table Mountain Observatory',
                   location=location,
                   timezone=utc,
                   )  # timezone=pytz.timezone('US/Pacific')

    sunriseUTC, sunsetUTC = genUtils.getSunriseSunset()
    sunriseUTC, sunsetUTC = roundToTenMinutes(sunriseUTC), roundToTenMinutes(sunsetUTC)
    sunriseUTC -= timedelta(hours=1)  # to account for us closing the dome one hour before sunrise
    sunsetUTC += timedelta(minutes=40) # temp
    # dbConnection = CandidateDatabase("./candidate database.db", "Night Obs Tool")
    #
    # candidates = mpcUtils.candidatesForTimeRange(sunsetUTC, sunriseUTC, 1, dbConnection)

    scheduleTable, _, _ = createSchedule(sunsetUTC, sunriseUTC)
    # scheduleTable.pprint(max_width=2000)
    # visualizeSchedule(scheduleTable, sunsetUTC, sunriseUTC)

    # del dbConnection
