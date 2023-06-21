from datetime import datetime as datetime
import astroplan, numpy
from scheduleLib import mpcUtils
from scheduleLib.genUtils import stringToTime, TypeConfiguration
import astropy.units as u
from scheduleLib.candidateDatabase import CandidateDatabase, Candidate


class MPCScorer(astroplan.Scorer):
    def __init__(self, candidateDict, *args, **kwargs):
        self.candidateDict = candidateDict
        super(MPCScorer, self).__init__(*args, **kwargs)

    # this makes a score array over the entire schedule for all of the blocks and each Constraint in the .constraints of each block and in self.global_constraints.
    def create_score_array(self, time_resolution=1 * u.minute):
        # score should be inversely proportional to (length of observable window / exposure time)
        start = self.schedule.start_time
        end = self.schedule.end_time
        times = astroplan.time_grid_from_range((start, end), time_resolution)
        scoreArray = numpy.ones(shape=(len(self.blocks), len(times)))
        for i, block in enumerate(self.blocks):
            desig = block.target.name
            candidate = self.candidateDict[desig]

            if block.constraints:
                for constraint in block.constraints:
                    appliedScore = constraint(self.observer, block.target,
                                              times=times)
                    scoreArray[i] *= appliedScore  # scoreArray[i] is an array of len(times) items

                window = (stringToTime(candidate.EndObservability) - stringToTime(
                    candidate.StartObservability)).total_seconds()

                scoreArray[i] *= (round(block.duration.to_value(u.second) / window,
                                        4))  # favor targets with short windows so that they get observed
                scoreArray[i] *= mpcUtils.isBlockCentered(block, candidate,
                                                          times)  # only allow observations at times where the blocks would be centered around a ten-minute interval
        for constraint in self.global_constraints:  # constraints applied to all targets
            scoreArray *= constraint(self.observer, self.targets, times, grid_times_targets=True)
        return scoreArray


def getConfig(startTimeUTC: datetime, endTimeUTC: datetime):
    # returns
    dbConnection = CandidateDatabase("./candidate database.db", "Night Obs Tool")
    candidates = mpcUtils.candidatesForTimeRange(startTimeUTC, endTimeUTC, 1, dbConnection)
    designations = [c.CandidateName for c in candidates]

    objTransitionDict = {'default': 180 * u.second}
    for d in designations:
        objTransitionDict[(d, "FocusLoop")] = 0 * u.second
        objTransitionDict[("FocusLoop", d)] = 0 * u.second  # i don't know if this one is necessary

    configuration = TypeConfiguration(candidates, MPCScorer, objTransitionDict, maxMinutesWithoutFocus=60)
    return "MPC NEO", configuration
    # this config will only apply to candidates with CandidateType "MPC NEO"
