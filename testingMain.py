from scheduleChecker import *
from sCore import *
from astral.sun import sun
from astral import LocationInfo, zoneinfo
from datetime import datetime, timezone,timedelta

debug = True
#dict of observation durations (seconds) to acceptable offsets (seconds)
obsTimeOffsets = {300:30,600:180,1200:300,1800:600}

## ----------Error Makers ----------

def noError():
    return Error("No Error",0,"No Error",lambda : "No Error")

def overlapErrorMaker(task1,task2):
    message = "Lines ending at " + timeToString(task1[0].endTime) + " and starting at " + timeToString(task2[0].startTime) + " overlap."
    return Error("Time Overlap Error",[task1[1],task2[1]],message)

def sunriseErrorMaker(sunrise,lastTask,timeDiff,lastLineNum):
    message = "Difference between sunrise ("+timeToString(sunrise)+") and line #" + str(lastLineNum) +" is " + str(timeDiff) +". Must be at least one hour."
    return Error("Sunrise Error",lastLineNum,message)

def centeringErrorMaker(lineNum,offset,centerTime,correctOffset,midPoint):
    message = "Task on line " + str(lineNum) + " is centered at " + timeToString(midPoint) + ", which is "+ str(offset) + " off of its preferred center ("+ timeToString(centerTime) + "). Observations of its duration should have an offset of at most " + str(correctOffset) + "."
    return Error("Time-Centering Error",lineNum,message)

def chronoOrderErrorMaker(lineNum):
    message = "Line " + str(lineNum) + " starts after the line that follows it!"
    return Error("Chronological Order Error",lineNum,message)

def autoFocusErrorMaker(lineNum):
    message = "AutoFocus loops are too far apart! Must occur no less than once per hour!"
    return Error("AutoFocus Error",lineNum,message)

## ----------Tests--------------

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
    global debug
    if debug:
        sunriseUTC = stringToTime("2022-12-26T10:00:00.000")
    else:
        loc = LocationInfo(name='TMO', region='CA, USA', timezone='UTC',
                           latitude=34.36, longitude=-117.63)
        s = sun(loc.observer, date=datetime.now(timezone.utc), tzinfo=timezone.utc)
        sunriseUTC = s["sunrise"]
    end = len(schedule.tasks)-1
    lastLine = schedule.tasks[end]
    sunriseDiff = sunriseUTC - lastLine.endTime
    if sunriseDiff < timedelta(hours=1):
        return 1, sunriseErrorMaker(sunriseUTC,lastLine,sunriseDiff,end)
    return 0,noError()

def obsCentered(schedule):
    #only call on observations
    for task in schedule.tasks:
        if isinstance(task,Observation):
            centered, offset, maxOffset, midPoint = checkObservationOffset(task)
            lineNum = schedule.lineNumber(task)
            if not centered:
                return 1, centeringErrorMaker(lineNum,offset,task.ephemTime,maxOffset,midPoint)
    return 0,noError()

def chronologicalOrder(schedule):
    for i in range(len(schedule.tasks)-1):
        if not isBefore(schedule.tasks[i],schedule.tasks[i+1]):
            return 1, chronoOrderErrorMaker(i)
    return 0, noError()

def autoFocusTiming(schedule):
    prevTime = schedule.tasks[0].startTime
    for task in schedule.tasks:
        if isinstance(task,AutoFocus):
            if abs(prevTime - task.startTime) > timedelta(hours=1):
                return 1, autoFocusErrorMaker(schedule.lineNumber(task))
            prevTime = task.startTime
    #now check to make sure that the remaining schedule is less that one hour
    print(prevTime - schedule.tasks[-1].startTime)

    if abs(prevTime - schedule.tasks[-1].startTime) > timedelta(hours=1):
        return 1, autoFocusErrorMaker(schedule.lineNumber(schedule.tasks[-1]))
    return 0,noError()

#--------Helper Functions---------

#take in an observation and calculate the difference between the middle of the observation window and the generated "ephemTime" of the object
def offsetFromCenter(observation):
    midPoint = observation.startTime+relativedelta(seconds = float(observation.duration)/2)
    offset = abs(midPoint - observation.ephemTime)
    return offset, midPoint

#check that an observation is close enough to its intended center
def checkObservationOffset(obs):
    global obsTimeOffsets
    #this will fail if obs.duration is not 300, 600, 1200, or 1800 seconds
    maxOffset = timedelta(seconds=obsTimeOffsets[obs.duration])
    offset, midPoint = offsetFromCenter(obs)
    return offset<=maxOffset, offset, maxOffset,midPoint

#check if task1 starts before task2
def isBefore(task1,task2):
    return task1.startTime < task2.startTime

def overlap(task1,task2):
    start1, end1 = task1.startTime, (task1.endTime+timedelta(minutes=3) if isinstance(task1,Observation) else task1.endTime)
    start2, end2 = task2.startTime, (task2.endTime+timedelta(minutes=3) if isinstance(task2,Observation) else task2.endTime)
    return (start1 < end2 and end1 > start2) or (start2 < end1 and end2 > start1) #is this right


#next test: RA/Dec Limits
## -------- Main ----------

#initialize tests
overlapTest = Test("Overlap",scheduleOverlap)
sunriseTest = Test("Done Before Sunrise",checkSunrise)
obsCenteredTest = Test("Observations Centered",obsCentered)
chronOrderTest = Test("Chronological Order", chronologicalOrder)
autoFocusTest = Test("AutoFocus Timing",autoFocusTiming)
tests = [overlapTest,sunriseTest,obsCenteredTest,chronOrderTest,autoFocusTest]
#make schedules
goodSchedule = readSchedule("files/exampleGoodSchedule.txt")
    #good schedule should pass almost all tests - will fail the autofocus test and the overlap test (doesn't allow 3 minutes between obs)
badSchedule = readSchedule("files/exampleBadSchedule.txt")
    #bad schedule should fail every test in the following ways:
    #   - Time Overlap Error: lines 1 and 2 should overlap
    #   - Sunrise Error: last observation happens too close to "sunrise"
    #   - Obs Centered: line 1 is centered off of its target
    #   - Chronological Order: line 5 starts after the line after it

#output
print("-"*10)
print(goodSchedule.summarize())
checkSchedule(goodSchedule,tests)
print("-"*10)
print(badSchedule.summarize())
checkSchedule(badSchedule,tests)