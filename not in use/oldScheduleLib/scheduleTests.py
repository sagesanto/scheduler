import sys
import warnings
from datetime import datetime, timezone, timedelta, time

import astropy.units as u
from astral import LocationInfo
# from sCore import *
from astral.sun import sun
from astropy.coordinates import Angle
from astropy.utils.exceptions import AstropyWarning

from scheduleChecker import *

warnings.simplefilter('ignore', category=AstropyWarning)
debug = True #won't be accurate when this is True, change before using!

#dict of observation durations (seconds) to acceptable offsets (seconds)
obsTimeOffsets = {300:30,600:180,1200:300,1800:600}

## ----------Error Makers ----------

def noError():
    return Error("No Error",0,"No Error",lambda : "No Error")

def overlapErrorMaker(task1,task2):
    message = "Lines ending at " + friendlyString(task1[0].endTime) + " and starting at " + friendlyString(task2[0].startTime) + " overlap."
    return Error("Time Overlap Error",[task1[1],task2[1]],message)

def sunriseErrorMaker(sunrise,lastTask,timeDiff,lastLineNum):
    message = "Difference between sunrise ("+friendlyString(sunrise)+") and line #" + str(lastLineNum) +" is " + str(timeDiff) +". Must be at least one hour."
    return Error("Sunrise Error",lastLineNum,message)

def centeringErrorMaker(lineNum,offset,centerTime,correctOffset,midPoint):
    message = "Task on line " + str(lineNum) + " is centered at " + friendlyString(midPoint) + ", which is "+ str(offset) + " off of its preferred center ("+ friendlyString(centerTime) + "). Observations of its duration should have an offset of at most " + str(correctOffset) + "."
    return Error("Time-Centering Error",lineNum,message)

def chronoOrderErrorMaker(lineNum):
    message = "Line " + str(lineNum) + " starts after the line that follows it!"
    return Error("Chronological Order Error",lineNum,message)

def autoFocusErrorMaker(lineNum):
    message = "AutoFocus loops are too far apart! Must occur no less than once per hour!"
    return Error("AutoFocus Error",lineNum,message)

def RAdecErrorMaker(lineNum):
    message = "RA and Dec not within acceptable limits at time of observation"
    return Error("RA/Dec Error",lineNum,message)

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

def RAdeclimits(schedule):
    for task in schedule.tasks:
        if isinstance(task,Observation):
            if not RAinLimits(task,-2,4) or not decInRange(task,-20,60):
                return 1, RAdecErrorMaker(schedule.lineNumber(task))
    return 0,noError()

#--------Helper Functions---------

#astropy gives us sidereal time as an angle in hours, so we need to convert it to a time
def siderealAngleToTime(angle):
    hours= angle.hour
    return time(hour=int(hours),minute=int((hours-int(hours))*60),second=int((((hours-int(hours))*60)-int((hours-int(hours))*60))*60))

#check if the RA is within (siderealTime of the observation) + lim1 and (siderealTime of the observation) + lim2
def RAinLimits(observation,lim1,lim2):
    lim1, lim2 = lim1*u.hourangle, lim2*u.hourangle
    loc = EarthLocation.from_geodetic('117.63 W', '34.36 N', 100 * u.m)
    startTime = Time(observation.startTime, scale='utc', location=loc)
    endTime = Time(observation.endTime, scale='utc', location=loc)
    startSidereal = startTime.sidereal_time('mean')
    endSidereal = endTime.sidereal_time('mean')
    RA = Angle(observation.RA, unit=u.deg)
    success = RA.is_within_bounds(startSidereal+lim1,endSidereal+lim2)
    if not success and debug:
        print("RA out of bounds!")
        print("RA: ",RA.hms," Start: ",startSidereal+lim1," End: ",endSidereal+lim2)
    return success

def decInRange(observation,above,below):
    dec = float(observation.Dec)
    if not (dec > above and dec < below):
        print("Dec failure! Dec: ",dec,dec in range(above,below))
    return dec > above and dec < below

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
    start1, end1 = task1.startTime, (task1.endTime+timedelta(minutes=5) if isinstance(task1,Observation) else task1.endTime)
    start2, end2 = task2.startTime, (task2.endTime+timedelta(minutes=5) if isinstance(task2,Observation) else task2.endTime)
    return (start1 < end2 and end1 > start2) or (start2 < end1 and end2 > start1) #is this right


#next test: RA/Dec Limits
## -------- Main ----------

#initialize tests
overlapTest = Test("Overlap",scheduleOverlap)
sunriseTest = Test("Done Before Sunrise",checkSunrise)
obsCenteredTest = Test("Observations Centered",obsCentered)
chronOrderTest = Test("Chronological Order", chronologicalOrder)
autoFocusTest = Test("AutoFocus Timing",autoFocusTiming)
RAdecTest = Test("RA/Dec Limits",RAdeclimits)
tests = [overlapTest,sunriseTest,obsCenteredTest,chronOrderTest,autoFocusTest,RAdecTest]

def runTestingSuite(schedule,verbose=True):
    global tests
    return checkSchedule(schedule,tests,verbose)


#output
if __name__ == "__main__":
    if debug:
        # make schedules
        goodSchedule = readSchedule("files/exampleGoodSchedule.txt")
        # good schedule should pass almost all tests - will fail the autofocus test and the overlap test (doesn't allow 3 minutes between obs)
        badSchedule = readSchedule("files/exampleBadSchedule.txt")
        # bad schedule should fail every test, as so:
        #   - Time Overlap Error: lines 1 and 2 should overlap
        #   - Sunrise Error: last observation happens too close to "sunrise"
        #   - Obs Centered: line 1 is centered off of its target
        #   - Chronological Order: line 5 starts after the line after it
        #   - AutoFocus Timing: line 8 starts more than an hour after the previous autofocus
        #   - RA/Dec Limits: line 15 is outside of the RA/Dec limits
        print("-"*10)
        print(goodSchedule.summarize())
        checkSchedule(goodSchedule,tests)
        print("-"*10)
        print(badSchedule.summarize())
        checkSchedule(badSchedule,tests)
        print("-"*10)
        print("\033[1;31m In debug mode so some inputs simulated! Turn off debug to see accurate results! \033[0;0m")

    else:
        userSchedule = readSchedule(sys.argv[1])
        checkSchedule(userSchedule,tests)
