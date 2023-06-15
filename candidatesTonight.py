from datetime import datetime, timezone, timedelta

import pytz

from scheduleLib.candidateDatabase import CandidateDatabase, Candidate, generateID
from scheduleLib import mpcUtils, generalUtils, asyncUtils

from astral import LocationInfo, zoneinfo, sun, SunDirection

utc = pytz.UTC


obsName="TMO"
region="CA, USA"
obsTimezone="UTC"
obsLat=34.36
obsLon=-117.63
observatory = LocationInfo(name="TMO", region=region, timezone=obsTimezone, latitude=obsLat,
                                longitude=obsLon)

s = sun.sun(observatory.observer, date=datetime.now(timezone.utc), tzinfo=timezone.utc)
sunriseUTC = s["sunrise"]
sunsetUTC = sun.time_at_elevation(observatory.observer, -10,direction=SunDirection.SETTING)

now_dt = datetime.utcnow()
now_dt = utc.localize(now_dt)

if sunriseUTC < now_dt:  # if the sunrise we found is earlier than the current time, add one day to it (approximation ofc)
    sunriseUTC = sunriseUTC + timedelta(days=1)

if sunsetUTC > sunriseUTC:
    sunsetUTC = sunsetUTC - timedelta(days=1)

print("Sunrise:",sunriseUTC)
print("Sunset:",sunsetUTC)

dbConnection = CandidateDatabase("./candidate database.db", "Night Obs Tool")

candidates = dbConnection.table_query("Candidates", "*", "RemovedReason IS NULL AND RejectedReason IS NULL AND CandidateType IS \"MPC NEO\" AND DateAdded > ?",[datetime.utcnow() - timedelta(hours=24)], returnAsCandidates=True)

print("Found",len(candidates),"initial candidates")
for candidate in candidates:
    print(candidate)
print("\n\n")
for candidate in candidates:
    if candidate.isObservableBetween(sunsetUTC,sunriseUTC,1):
        print(candidate)
