from scheduleChecker import *
from sCore import *
from astral.sun import sun
from astral import LocationInfo, zoneinfo
from datetime import datetime, timezone,timedelta

def overlap(task1,task2):
    return (task1.startTime < task2.endTime and task1.endTime > task2.startTime) or (task2.startTime < task1.endTime and task2.endTime > task1.startTime) #is this right

def noError():
    return Error("No Error",0,"No Error",lambda : "No Error")

def overlapErrorMaker(task1,task2):
    message = "Lines starting at " + timeToString(task1[0].startTime) + " and " + timeToString(task2[0].startTime) + " overlap"
    return Error("Time Overlap Error",[task1[1],task2[1]],message)

def sunriseErrorMaker(sunrise,lastTask,timeDiff,lastLineNum):
    message = "Difference between sunrise ("+timeToString(sunrise)+") and line #" + str(lastLineNum) +" is " + str(timeDiff) +". Must be at least one hour."
    return Error("Sunrise Error",lastLineNum,message)

def scheduleOverlap(schedule): #this is all bad
    schedDict = schedule.toDict()
    sortedDict = {key:schedDict[key] for key in sorted(schedDict.keys())} #this is a lazy and not necessarily performance-friendly way to do this
    keys,vals = list(sortedDict),list(sortedDict.values())
    for i in range(len(vals)):
        if i+1 <= len(vals)-1:
            if overlap(vals[i][0],vals[i+1][0]):
                return 1, overlapErrorMaker(vals[i],vals[i+1])
    return 0,noError()


def checkSunrise(schedule):
    # loc = LocationInfo(name='TMO', region='CA, USA', timezone='UTC',
    #                    latitude=34.36, longitude=-117.63)
    # s = sun(loc.observer, date=datetime.now(timezone.utc), tzinfo=timezone.utc)
    # sunriseUTC = s["sunrise"]
    #REPLACE THIS WITH ABOVE COMMENTED CODE:
    sunriseUTC = stringToTime("2022-12-26T10:00:00.000")
    end = len(schedule.tasks)-1
    lastLine = schedule.tasks[end]
    sunriseDiff = sunriseUTC - lastLine.endTime
    if sunriseDiff < timedelta(hours=1):
        return 1, sunriseErrorMaker(sunriseUTC,lastLine,sunriseDiff,end)
    return 0,noError()


overlapTest = Test("Overlap",scheduleOverlap)
sunriseTest = Test("Done Before Sunrise",checkSunrise)
tests = [overlapTest,sunriseTest]

print("Testing main")
goodSchedule = readSchedule("files/exampleGoodSchedule.txt")
#good schedule should pass all tests - it's a real observing schedule that was used
badSchedule = readSchedule("files/exampleBadSchedule.txt")
#bad schedule should fail every test in the following ways:
#   - Time Overlap Error: lines 1 and 2 should overlap
#   -


print("-"*10)
print(goodSchedule.summarize())
checkSchedule(goodSchedule,tests)
print("-"*10)
print(badSchedule.summarize())
checkSchedule(badSchedule,tests)