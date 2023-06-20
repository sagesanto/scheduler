from datetime import datetime, timezone, timedelta

import numpy as np
import pytz
from astropy.coordinates import Angle
from astropy import units as u
from matplotlib import pyplot as plt
from astropy.table import Table
from scheduleLib.candidateDatabase import CandidateDatabase, Candidate
from scheduleLib.mpcUtils import candidatesForTimeRange
from scheduleLib import genUtils
from scheduleLib.genUtils import ScheduleError
import pandas as pd
from astral import LocationInfo, zoneinfo, sun, SunDirection

# most of this is proof-of-concept stuff for the newScheduler, just packaged to be semi-useful as a tool before i implement it

BLACK = [0, 0, 0]
RED = [255, 0, 0]
GREEN = [0, 255, 0]
BLUE = [0, 0, 255]
ORANGE = [255, 191, 0]
PURPLE = [221, 160, 221]


def visualizeObservability(candidates: list, beginDt, endDt, schedule=None):
    """
    Visualize the observability windows of candidates as a stacked timeline.

    :param candidates: list of Candidate objects
    :param beginDt: time of beginning of observability window, datetime
    :param endDt: time of edning of observability windows, datetime
    :param schedule: WIP: astropy Table output by a scheduler. if passed, will be overlaid over the graphics.
    :type schedule: Table

    """
    print(beginDt, endDt)
    # Filter candidates with observability windows
    observabilityCandidates = [c for c in candidates if
                               c.hasField("StartObservability") and c.hasField("EndObservability")]

    # Sort candidates by their start times (earliest to latest)
    observabilityCandidates.sort(key=lambda c: genUtils.stringToTime(c.StartObservability))

    # Calculate start and end timestamps
    xMin, xMax = beginDt.timestamp(), endDt.timestamp()
    windowDuration = xMax - xMin

    # Get the unique colors and calculate the number of bars per color
    numCandidates = len(observabilityCandidates)
    numColors = len(plt.cm.tab20.colors)

    # Generate a list of colors using a loop
    colors = []
    for i in range(numCandidates):
        colorIndex = i % numColors
        color = plt.cm.tab20(colorIndex)
        colors.append(color)

    # Set up the plot
    fig, ax = plt.subplots(figsize=(10, 7))
    colorDict = {"GREEN": GREEN, "ORANGE": ORANGE, "RED": RED, "BLACK": BLACK}

    # if schedule is not None:
    #     df = schedule.to_pandas()
    #     print(df)

    # Iterate over observability candidates and plot their windows
    for i, candidate in enumerate(observabilityCandidates):
        # TODO: take the time to actually figure out why the UTC stuff doesn't work instead of just applying this hardcoded offset:
        startTime = genUtils.stringToTime(candidate.StartObservability) - timedelta(
            hours=7)  # UTC conversion. this sucks
        endTime = genUtils.stringToTime(candidate.EndObservability) - timedelta(hours=7)

        # Convert start time and end time to Unix timestamps
        startUnix = startTime.timestamp()
        endUnix = endTime.timestamp()

        # Calculate the duration of the observability window
        duration = endUnix - startUnix

        # Plot a rectangle representing the observability window
        ax.barh(i, duration, left=startUnix, height=0.6, color=np.array(colorDict[candidate.ApproachColor]) / 255)

        # Place the label at the center of the bar
        ax.text(max(startUnix + duration / 2, xMin + duration / 2), i, candidate.CandidateName, ha='center',
                va='center', bbox={'facecolor': 'white', 'alpha': 0.75, 'pad': 5})

    # Set the x-axis limits based on start and end timestamps
    ax.set_xlim(xMin, xMax + windowDuration / 10)

    # Format x-axis labels as human-readable datetime
    def formatFunc(value, tickNumber):
        dt = datetime.utcfromtimestamp(value)
        return dt.strftime("%H:%M\n%d-%b")

    ax.xaxis.set_major_formatter(plt.FuncFormatter(formatFunc))

    # Set the x-axis label
    ax.set_xlabel("Time (UTC)")

    # Set the y-axis label
    ax.set_ylabel("Candidates")

    # Adjust spacing
    plt.subplots_adjust(left=0.1, right=0.95, bottom=0.1, top=0.9)
    plt.suptitle("Candidates for Tonight")
    plt.title(
        datetime.utcfromtimestamp(xMin).strftime("%b %d, %Y, %H:%M") + " to " + datetime.utcfromtimestamp(
            xMax).strftime(
            "%b %d, %Y, %H:%M"))

    # Show the plot
    plt.show()


utc = pytz.UTC

region = "CA, USA"
obsTimezone = "UTC"
obsLat = 34.36
obsLon = -117.63
TMO = LocationInfo(name="TMO", region="CA, USA", timezone="UTC", latitude=34.36,
                   longitude=-117.63)

s = sun.sun(TMO.observer, date=datetime.now(timezone.utc), tzinfo=timezone.utc)
sunriseUTC = s["sunrise"]
sunsetUTC = sun.time_at_elevation(TMO.observer, -10, direction=SunDirection.SETTING)

nowDt = datetime.utcnow()
nowDt = utc.localize(nowDt)

if sunriseUTC < nowDt:  # if the sunrise we found is earlier than the current time, add one day to it (approximation ofc)
    sunriseUTC = sunriseUTC + timedelta(days=1)

if sunsetUTC > sunriseUTC:
    sunsetUTC = sunsetUTC - timedelta(days=1)

print("Sunset:", sunsetUTC)
print("Sunrise:", sunriseUTC)

dbConnection = CandidateDatabase("./candidate database.db", "Night Obs Tool")

candidates = candidatesForTimeRange(sunsetUTC, sunriseUTC, 1, dbConnection)

# candidates = dbConnection.candidatesAddedSince(datetime.utcnow() - timedelta(hours=24))

print(genUtils.findTransitTime(Angle("18h39m00s"), TMO).strftime("%H:%M"))

if not len(candidates):
    del dbConnection
    raise ScheduleError()

print("Candidates for tonight(%s):" % len(candidates), candidates)
df = Candidate.candidatesToDf(candidates)
print(df.columns)
# df["TransitTime"] = df.apply(
#     lambda row: genUtils.findTransitTime(genUtils.ensureAngle(str(row["RA"]) + "h"), TMO).strftime("%H:%M"), axis=1)
df = genUtils.prettyFormat(df)
df.to_csv("out.csv",index=False)
print(df.to_string)
visualizeObservability(candidates, sunsetUTC, sunriseUTC - timedelta(hours=1))
