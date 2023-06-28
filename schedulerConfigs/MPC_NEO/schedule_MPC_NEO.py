from datetime import datetime as datetime, timedelta

import astroplan
import astropy
import astropy.units as u
import numpy
import numpy as np
from astropy.time import Time

from scheduleLib import mpcUtils
from scheduleLib.candidateDatabase import CandidateDatabase
from scheduleLib.genUtils import stringToTime, TypeConfiguration


def reverseNonzeroRunInplace(arr):
    nonzeroIndices = np.nonzero(arr)[0]  # find the indices of non-zero elements
    arr[nonzeroIndices] = arr[nonzeroIndices[::-1]]  # reverse the non-zero run in-place
    return arr


class MpcConfig(TypeConfiguration):
    def __init__(self, scorer, maxMinutesWithoutFocus=65, numObs=2, minMinutesBetweenObs=45):
        self.scorer = scorer
        self.maxMinutesWithoutFocus = maxMinutesWithoutFocus  # max time, in minutes, that this object can be scheduled after the most recent focus loop
        self.numObs = numObs
        self.minMinutesBetweenObs = minMinutesBetweenObs  # minimum time, in minutes, between the start times of multiple observations of the same object
        self.timeResolution = None
        self.candidateDict = None
        self.designations = None

    def selectCandidates(self, startTimeUTC: datetime, endTimeUTC: datetime):
        dbConnection = CandidateDatabase("./candidate database.db", "Night Obs Tool")
        candidates = [c for c in mpcUtils.candidatesForTimeRange(startTimeUTC, endTimeUTC, 1, dbConnection) if
                      c.CandidateName]
        self.designations = [c.CandidateName for c in candidates]
        self.candidateDict = zip(candidates, self.designations)
        return candidates

    def generateTransitionDict(self):
        objTransitionDict = {'default': 240 * u.second}
        for d in self.designations:
            objTransitionDict[("Focus", d)] = 0 * u.second
            objTransitionDict[("Unused Time", d)] = 0 * u.second
        return objTransitionDict

    def scoreRepeatObs(self, c, scoreLine, numPrev, currentTime):
        return reverseNonzeroRunInplace(scoreLine)

    def generateTypeConstraints(self):
        return None

    def generateSchedulerLine(self, row, targetName, candidateDict):
        desig = targetName[:-2]
        c = candidateDict[desig]
        startDt = stringToTime(row["start time (UTC)"])
        duration = timedelta(minutes=row["duration (minutes)"])
        center = startDt + duration / 2
        center -= timedelta(seconds=center.second, microseconds=center.microsecond)
        return mpcUtils.candidateToScheduleLine(c, startDt, center, targetName)


def linearDecrease(lenArr, x1, xIntercept):
    return (np.arange(lenArr) - xIntercept) * -1 / (xIntercept - x1)


class MPCScorer(astroplan.Scorer):
    def __init__(self, candidateDict, *args, **kwargs):
        self.candidateDict = candidateDict
        super(MPCScorer, self).__init__(*args, **kwargs)

    # this makes a score array over the entire schedule for all of the blocks and each Constraint in the .constraints of each block and in self.global_constraints.
    def create_score_array(self, time_resolution=1 * u.minute):
        start = self.schedule.start_time
        end = self.schedule.end_time
        times = astroplan.time_grid_from_range((start, end), time_resolution)
        scoreArray = numpy.ones(shape=(len(self.blocks), len(times)))
        for i, block in enumerate(self.blocks):
            desig = block.target.name
            candidate = self.candidateDict[desig]

            if block.constraints:
                for constraint in block.constraints:  # apply the observability window constraint
                    appliedScore = constraint(self.observer, block.target,
                                              times=times)
                    scoreArray[i] *= appliedScore  # scoreArray[i] is an array of len(times) items

                window = (stringToTime(candidate.EndObservability) - stringToTime(
                    candidate.StartObservability)).total_seconds()

                startIdx = int((Time(stringToTime(candidate.StartObservability)) - start) / time_resolution)
                endIdx = int((Time(stringToTime(candidate.EndObservability)) - start) / time_resolution)
                scoreArray[i] *= linearDecrease(len(times), startIdx, endIdx)

                # scoreArray[i] *= (round(block.duration.to_value(u.second) / window,
                #                         4))  # favor targets with short windows so that they get observed
                # scoreArray[i] *= (round(1 / block.duration.to_value(u.second),
                #                         4))  # favor targets with long windows so it's more likely they get 2 obs in
                # scoreArray[i] *= 1/(float(candidate.Magnitude))
        for constraint in self.global_constraints:  # constraints applied to all targets
            scoreArray *= constraint(self.observer, self.targets, times, grid_times_targets=True)
        return scoreArray


def getConfig():
    # returns a TypeConfiguration object for targets of type "MPC NEO"
    configuration = MpcConfig(MPCScorer)

    return "MPC NEO", configuration
    # this config will only apply to candidates with CandidateType "MPC NEO"
