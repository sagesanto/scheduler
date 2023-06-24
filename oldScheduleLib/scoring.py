# view-source:https://cgi.minorplanetcenter.net/cgi-bin/uncertaintymap.cgi?Obj=X81536&JD=2460001.666667&Form=Y&Ext=VAR&OC=000&META=apm00
from datetime import timedelta

from astropy import units as u
from astropy.coordinates import AltAz, EarthLocation, SkyCoord
from astropy.time import Time

from sCore import *
from scheduleTests import runTestingSuite

schedule = readSchedule("files/exampleGoodSchedule.txt")

def calculateDowntime(schedule):
    schedDict = schedule.toDict()
    sortedDict = {key:schedDict[key] for key in sorted(schedDict.keys())}
    keys,vals = list(sortedDict),list(sortedDict.values())
    totalDowntime = timedelta()
    downtimes = []
    for i in range(len(vals)):
        if i+1 <= len(vals)-1:
            downtime = vals[i+1][0].startTime - (vals[i][0].endTime + timedelta(minutes = 5))
            downtime = downtime if downtime.total_seconds() > 0 else timedelta(minutes=0)
            downtimes.append(downtime)
            totalDowntime += downtime
    return totalDowntime, max(downtimes), totalDowntime/len(downtimes)

def numSchedErrors(schedule):
    return runTestingSuite(schedule,False)

def observationsNearMeridian(schedule):
    numNear = 0
    loc = EarthLocation.from_geodetic('117.63 W', '34.36 N', 100 * u.m)
    for task in schedule.tasks:
        if isinstance(task,Observation):
            obj = SkyCoord(ra=float(task.RA) * u.degree, dec=float(task.Dec) * u.degree, frame='icrs')
            time = Time(task.ephemTime)
            altaz = obj.transform_to(AltAz(obstime=time, location=loc))
            if altaz.alt.degree > 80:
                numNear += 1
    return numNear/len(schedule.tasks)

def countZTobservations(schedule):
    numZTF = 0
    for task in schedule.tasks:
        if isinstance(task,Observation):
            if task.targetName[:2] == "ZT":
                numZTF += 1
    return numZTF

#dictionary of value names to values
c = {}

c["zt"] = countZTobservations(schedule)
c["errors"] = numSchedErrors(schedule)
c["downtime"] = calculateDowntime(schedule)[0].total_seconds()/60
c["meridian"] = observationsNearMeridian(schedule)
c["numTargets"] = len(schedule.targets)
c["numObs"] = len(schedule.tasks)

score = (c["meridian"])/(c["errors"]*c["downtime"])*(2*c["numTargets"]+c["numObs"]) * 80
print("Score:",int(score))

#What makes a good schedule?
#  low downtime
#     lots of objects
#  correct
#  ZTF and SRO objects prioritized
#      near the meridian
#      score each obs, higher score for these is good
#  low airmass (HA close to 0?)


