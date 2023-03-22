import sys

from scheduleLib import sCoreCondensed as sc
schedule = sc.readSchedule("files/exampleSchedule.txt")
print(schedule.summarize())

#will take the following things as input: [1] path to a folder with lists of ephemerides for each object (filename should be [object name].txt),
#[2] preferred min time between observations, [3] preferred minimum time between observations of the same object, [4] start time in the format DD-MM-YYYY HH:MM:SS

ephemsDir, minTimeBetween, minTimeBetweenSame, startTime = sys.argv[1:5]
startTime = datetime.strptime(startTime, "%d-%m-%Y %H:%M:%S")


loc = LocationInfo(name='TMO', region='CA, USA', timezone='UTC',
                   latitude=34.36, longitude=-117.63)
s = sun(loc.observer, date=datetime.now(timezone.utc), tzinfo=timezone.utc)
sunrise = s["sunrise"]

offsets = sc.obsTimeOffsets

class observationPackage:
    def __init__(self,obs):
        self.obs = obs
        self.objName = obs.targetName
        self.startRange = self.findStartTimeRange(self.obs)
    def findStartTimeRange(self): #given an observation, based on its length, center it and find the range of acceptable start times
        centered, offset, maxOffset, midPoint = sc.checkObservationOffset(self.obs)
        range = []
        for minute in maxOffset.minutes/60:
            range.append(midPoint - minute)
            range.append(midPoint + minute)
        return range.sort()

def loadPotentialObs(ephemsDir, startTime):
    potentialObs = {} #potential obs is a dictionary that has maps object names to a dictionary of {start times : observation packages}
    for file in os.listdir(ephemsDir):
        objObs = {} #dictionary of {start times : observation packages}
        with open(os.path.join(ephemsDir, file)) as f:
            for line in f:
                if line[0] == "\n":
                    continue
                else:
                    obs = sc.Observation.fromLine(line)
                    obsPack = observationPackage(obs)
                    if obs.range[-1] > startTime:
                        objObs[obs.range[0]] = obsPack
        potentialObs[obs.targetName] = objObs
    return potentialObs

def objNextObs(ObjPotentialObs,startTime):
    for time in ObjPotentialObs[startTime].startRange: #we're checking if the observation indicated by the provided start time can start at one of the times in its range start at any time in the range
        if time > startTime:
            pkg = ObjPotentialObs[startTime]
            pkg.obs.startTime = time
            pkg.obs.endTime = pkg.obs.startTime+pkg.obs.duration
            return pkg
    return None

class scheduleBuilder:
    def __init__(self):
        self.currentTime = startTime #this time will be updated as the schedule is built
        self.schedule = sc.Schedule()
    def placeObservation(self, obsPack,obsStartTime):
        obs = obsPack.obs
        obs.startTime, obs.endTime = obsStartTime, obsStartTime + relativedelta(seconds = float(obs.duration))
        schedule.appendTask(obs)
        self.currentTime = obsStartTime + relativedelta(seconds = float(obs.duration)) + relativedleta(minutes = float(minTimeBetween))
    def deleteObservation(self,obs): #deletes the given observation and all observations after it - probably better to use some graph structure here but whatever
        index = self.schedule.tasks.index(obs)
        while self.schedule.tasks[index]:
            self.schedule.deleteTask(index)
        self.currentTime = self.observations[index-1][0]
    def nextObservationCandidates(self, potentialObs, startTime): #my head hurts
        nextObs = {} #dictionary of {observation packages : start times}
        for obj in potentialObs.keys():
            target = self.schedule.targets[obj]
            lastStart = target.observations[-1].startTime
            for start in potentialObs[obj].keys():
                candidate = objNextObs(potentialObs[obj], max(start,lastStart+relativedelta(minutes = minTimeBetweenSame)))
                if candidate:
                    nextObs[obj] = candidate
                    break
        return nextObs
    def buildScheduleLoop(self, potentialObs):
        while True:
            nextObs = self.nextObservationCandidates(potentialObs, self.currentTime)
            if nextObs == {}:
                break
            else:
                nextToPlace = presentOptions(nextObs)
                placeObservation(nextToPlace, nextToPlace.startRange[0])

