from datetime import datetime, timezone, timedelta

import pytz
from astropy.coordinates import Angle
from astropy import units as u
from matplotlib import pyplot as plt

from scheduleLib.candidateDatabase import CandidateDatabase, Candidate
from scheduleLib.mpcUtils import candidatesForTimeRange
from scheduleLib import genUtils
from scheduleLib.genUtils import ScheduleError

from astral import LocationInfo, zoneinfo, sun, SunDirection

#most of this is proof-of-concept stuff for the newScheduler, just packaged to be semi-useful as a tool
def visualizeObservability(candidates: list, sunset, sunrise):
    """
    Visualize the observability windows of candidates as a stacked timeline.

    :param candidates: list of Candidate objects

    """
    print(sunset, sunrise)
    # Filter candidates with observability windows
    observability_candidates = [c for c in candidates if
                                c.hasField("StartObservability") and c.hasField("EndObservability")]

    # Sort candidates by their start times (earliest to latest)
    observability_candidates.sort(key=lambda c: genUtils.stringToTime(c.StartObservability))

    # Calculate start and end timestamps

    xMin, xMax = sunset.timestamp(), sunrise.timestamp()
    windowDuration = xMax - xMin
    # Get the unique colors and calculate the number of bars per color
    num_candidates = len(observability_candidates)
    num_colors = len(plt.cm.tab20.colors)

    # Generate a list of colors using a loop
    colors = []
    for i in range(num_candidates):
        color_index = i % num_colors
        color = plt.cm.tab20(color_index)
        colors.append(color)

    # Set up the plot
    fig, ax = plt.subplots(figsize=(10, 7))

    # Iterate over observability candidates and plot their windows
    for i, candidate in enumerate(observability_candidates):
        start_time = genUtils.stringToTime(candidate.StartObservability) - timedelta(hours=7)
        end_time = genUtils.stringToTime(candidate.EndObservability) - timedelta(hours=7)

        # Convert start time and end time to Unix timestamps
        start_unix = start_time.timestamp()
        end_unix = end_time.timestamp()

        # Calculate the duration of the observability window
        duration = end_unix - start_unix

        # Plot a rectangle representing the observability window
        ax.barh(i, duration, left=start_unix, height=0.6, color=colors[i])

        # Place the label at the center of the bar
        # ax.text(start_unix + duration / 2, i, candidate.CandidateName, ha='center', va='center')
        ax.text(max(start_unix + duration / 2, xMin + duration / 2), i, candidate.CandidateName, ha='center',
                va='center', bbox={'facecolor': 'white', 'alpha': 0.75, 'pad': 5})

    # Set the x-axis limits based on start and end timestamps
    ax.set_xlim(xMin, xMax + windowDuration / 10)

    # Format x-axis labels as human-readable datetime
    def format_func(value, tick_number):
        dt = datetime.utcfromtimestamp(value)
        return dt.strftime("%H:%M\n%d-%b")

    ax.xaxis.set_major_formatter(plt.FuncFormatter(format_func))

    # Set the x-axis label
    ax.set_xlabel("Time (UTC)")

    # Set the y-axis label
    ax.set_ylabel("Candidates")

    # Adjust spacing
    plt.subplots_adjust(left=0.1, right=0.95, bottom=0.1, top=0.9)
    plt.suptitle("Candidates for Tonight")
    plt.title(
        datetime.fromtimestamp(xMin).strftime("%b %d, %Y, %H:%M") + " to " + datetime.fromtimestamp(xMax).strftime(
            "%b %d, %Y, %H:%M"))
    # Show the plot
    plt.show()


utc = pytz.UTC

region = "CA, USA"
obsTimezone = "UTC"
obsLat = 34.36
obsLon = -117.63
TMO = LocationInfo(name="TMO", region=region, timezone=obsTimezone, latitude=obsLat,
                   longitude=obsLon)

s = sun.sun(TMO.observer, date=datetime.now(timezone.utc), tzinfo=timezone.utc)
sunriseUTC = s["sunrise"]
sunsetUTC = sun.time_at_elevation(TMO.observer, -10, direction=SunDirection.SETTING)

now_dt = datetime.utcnow()
now_dt = utc.localize(now_dt)

if sunriseUTC < now_dt:  # if the sunrise we found is earlier than the current time, add one day to it (approximation ofc)
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
df["TransitTime"] = df.apply(
    lambda row: genUtils.findTransitTime(genUtils.ensureAngle(str(row["RA"]) + "h"), TMO).strftime("%H:%M"), axis=1)
df = genUtils.prettyFormat(df)
df.to_csv("out.csv")
print(df.to_string)
visualizeObservability(candidates, sunsetUTC, sunriseUTC)
