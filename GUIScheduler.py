from condensedScheduleLib import sCoreCondensed as sc
schedule = sc.readSchedule("files/exampleSchedule.txt")
print(schedule.summarize())

print(sc.obsTimeOffsets)

class observationPackage:
    def __init__(self,obs):
        self.obs = obs
def findStartTimeRange(obs): #given an observation, based on its length, center it and find the range of acceptable start times
   pass