from scheduleChecker import *
from sCore import *

def overlap(task1,task2):
    return (task1.startTime < task2.endTime and task1.endTime > task2.startTime) or (task2.startTime < task1.endTime and task2.endTime > task1.startTime) #is this right

def noError():
    return Error("No Error",0,"No Error",lambda : "No Error")

def overlapErrorMaker(task1,task2):
    message = "Lines starting at " + timeToString(task1[0].startTime) + " and " + timeToString(task2[0].startTime) + " overlap"
    return Error("Time Overlap Error",[task1[1],task2[1]],message)

def scheduleOverlap(schedule): #this is all bad
    schedDict = schedule.toDict()
    sortedDict = {key:schedDict[key] for key in sorted(schedDict.keys())} #this is a lazy and not necessarily performance-friendly way to do this
    keys,vals = list(sortedDict),list(sortedDict.values())
    for i in range(len(vals)):
        if i+1 <= len(vals)-1:
            if overlap(vals[i][0],vals[i+1][0]):
                print(vals[i][0],"end",timeToString(vals[i][0].endTime))
                return 1, overlapErrorMaker(vals[i],vals[i+1])
    return 0,noError()

tests = []
overlapTest = Test("Overlap",scheduleOverlap)
tests.append(overlapTest)

print("Testing main")
schedule = readSchedule("files/exampleSchedule.txt")
print(schedule.summarize())

checkSchedule(schedule,tests)

