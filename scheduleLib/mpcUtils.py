# Sage Santomenna 2023

from photometrics.mpc_neo_confirm import MPCNeoConfirm as mpc
from datetime import datetime, timedelta
from scheduleLib import asyncUtils
import pytz, math, astropy
from scheduleLib.candidateDatabase import Candidate
from astroplan.scheduling import ObservingBlock
import numpy as np
from astropy.coordinates import SkyCoord
import httpx
from bs4 import BeautifulSoup
from scheduleLib import genUtils


# this isn't terribly elegant
def _findExposure(magnitude, str=True):
    # Internal: match magnitude to exposure description for TMO
    magnitude = float(magnitude)
    if str:
        if magnitude <= 19.5:
            return "1.0|300.0"
        if magnitude <= 20.5:
            return "1.0|600.0"
        if magnitude <= 21.0:
            return "2.0|600.0"
        if magnitude <= 21.5:
            return "3.0|600.0"
    else:
        if magnitude <= 19.5:
            return 1, 300
        if magnitude <= 20.5:
            return 1, 600
        if magnitude <= 21.0:
            return 2, 600
        if magnitude <= 21.5:
            return 3, 600
    return -1, -1


def isBlockCentered(block: ObservingBlock, candidate: Candidate, times: np.array(astropy.time.Time)):
    """
    return an array of bools indicating whether or not the block is centered around each of the times provided
    :return: array of bools
    """
    obsTimeOffsets = {300: 30, 600: 180, 1200: 300,
                      1800: 600}  # seconds of exposure: seconds that the observation can be offcenter

    expTime = timedelta(seconds=block.configuration["duration"])
    # this will fail if obs.duration is not 300, 600, 1200, or 1800 seconds:
    maxOffset = timedelta(seconds=obsTimeOffsets[expTime.seconds])
    bools = np.array([checkOffsetFromCenter(t, expTime, maxOffset) for t in times])
    # print(bools.shape)
    return bools


def checkOffsetFromCenter(startTime, duration, maxOffset):
    """
    is the observation that starts at startTime less that maxOffset away from the nearest ten minute interval?
    :param startTime:
    :param duration:
    :param maxOffset:
    :return:
    """
    center = startTime.datetime + (duration / 2)
    roundCenter = genUtils.roundToTenMinutes(center)
    return abs(roundCenter - center) < maxOffset
    # abs(nearestTenMinutesToCenter-(start + (expTime/2))) must be less than maxOffset


def dictFromEphemLine(ephem):
    returner = {"RA": (raDecFromEphem(ephem))[0], "dec": (raDecFromEphem(ephem))[1],
                "vMag": ephem[2],
                "dRA": (velFromEphem(ephem))[0], "dDec": (velFromEphem(ephem))[1],
                "obsTime": timeFromEphem(ephem)}

    return returner


def velFromEphem(ephem):
    dRa = str(round(float(ephem[3]) * 60, 2))
    dDec = str(round(float(ephem[4]) * 60, 2))
    return dRa, dDec


def raDecFromEphem(ephem):
    """
    Extracts the right ascension and declination coordinates from a raw ephemeris line

    :param ephem: list
    :return: Tuple containing the right ascension and declination coordinates as floats.
    :rtype: tuple[float, float]
    """
    coords = ephem[1]
    coords = coords.to_string("decimal").split(" ")
    return float(coords[0]), float(coords[1])


def timeFromEphem(ephem):
    """
    Converts the time associated with the ephem to a UTC datetime.

    :param ephem: List containing an ephem object.
    :type ephem: list

    :return: The UTC datetime extracted from the ephem object.
    :rtype: datetime.datetime
    """
    ephem[0].format = "fits"
    ephem[0].out_subfmt = "date_hms"
    date = ephem[0].value
    ephem[0].format = "iso"
    ephem[0].out_subfmt = "date_hm"
    inBetween = ephem[0].value
    return datetime.strptime(inBetween, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)

def candidateToScheduleLine(candidate:Candidate,startDt, centerDt):
    c = candidate
    RA = genUtils.ensureAngle(c.RA)
    Dec = genUtils.ensureAngle(c.Dec)
    return mpcScheduleLine(c.CandidateName,startDt,centerDt,SkyCoord(ra=RA, dec=Dec),dRA=float(c.dRA),dDec=float(c.dDec),vMag=c.Magnitude)

def mpcScheduleLine(desig, startDt,centerDt, skycoord, dRA:float, dDec:float, vMag):
    # the dateTime in the ephems list is a Time object, need to convert it to string
    # name
    startDate = startDt.strftime('%Y-%m-%dT%H:%M:%S')
    # convert the skycoords object to decimal
    coords = skycoord.to_string("decimal").replace(" ", "|")

    # get the correct exposure string based on the vMag
    exposure = str(_findExposure(float(vMag)))

    # dRA and dDec come in arcsec/sec, we need /minute
    dRa = str(round(dRA, 2))
    dDec = str(round(dDec, 2))

    # for the description, we need RA and Dec in sexagesimal
    sexagesimal = skycoord.to_string("hmsdms").split(" ")
    # the end of the scheduler line must have a description that looks like this
    description = "\'MPC Asteroid " + desig + ", UT: " + datetime.strftime(centerDt, "%H%M") + " RA: " + \
                  sexagesimal[0] + " DEC: " + sexagesimal[1] + " dRA: " + dRa + " dDEC: " + dDec + "\'"

    lineList = [startDate, "1", desig, "1", coords, exposure, "CLEAR", description]
    expLine = "|".join(lineList)
    return expLine

def _formatEphem(ephems, desig):
    # Internal: take an object in the form returned from self.mpc.get_ephemeris() and convert each line to the scheduler format, before returning it in a dictionary of {startDt : line}
    ephemDict = {None: "DateTime|Occupied|Target|Move|RA|Dec|ExposureTime|#Exposure|Filter|Description"}
    if ephems is None:
        return None
    for i in ephems:
        # the dateTime in the ephems list is a Time object, need to convert it to string
        i[0].format = "fits"
        i[0].out_subfmt = "date_hms"
        date = i[0].value
        i[0].format = "iso"
        i[0].out_subfmt = "date_hm"
        inBetween = i[0].value
        dateTime = datetime.strptime(inBetween, "%Y-%m-%d %H:%M")
        # name
        target = desig
        # convert the skycoords object to decimal
        coords = i[1].to_string("decimal").replace(" ", "|")

        vMag = i[2]
        # get the correct exposure string based on the vMag
        exposure = str(_findExposure(float(vMag)))

        # dRA and dDec come in arcsec/sec, we need /minute
        dRa = str(round(float(i[3]) * 60, 2))
        dDec = str(round(float(i[4]) * 60, 2))

        # for the description, we need RA and Dec in sexagesimal
        sexagesimal = i[1].to_string("hmsdms").split(" ")
        # the end of the scheduler line must have a description that looks like this
        description = "\'MPC Asteroid " + target + ", UT: " + datetime.strftime(dateTime, "%H%M") + " RA: " + \
                      sexagesimal[0] + " DEC: " + sexagesimal[1] + " dRA: " + dRa + " dDEC: " + dDec + "\'"

        lineList = [date, "1", target, "1", coords, exposure, "CLEAR", description]
        expLine = "|".join(lineList)
        ephemDict[dateTime] = expLine
    return ephemDict


def pullEphem(mpcInst, desig, whenDt, altitudeLimit, schedulerFormat=False, obsCode=654):
    """
    Fetch the ephemeris of a target from the MPC NEO confirmation database, given a valid designation. Requires internet connection.
    :param mpcInst: An instance of the MPCNeoConfirm class from the (privileged) photometrics.mpc_neo_confirm module
    :param desig: the temporary designation of the NEO candidate, as it appears on the MPC
    :param whenDt: A datetime object representing the time for which the ephemeris should be generated
    :param altitudeLimit: The lower altitude limit, below which ephemeris lines will not be generated
    :return: A Dictionary {startTimeDt: ephemLine}
    """
    if whenDt != 'now':
        whenDt = whenDt.strftime('%Y-%m-%dT%H:%M')
    try:
        returner = mpcInst.get_ephemeris(desig, when=whenDt,
                                         altitude_limit=altitudeLimit, get_uncertainty=None)
    except:
        return None
    if schedulerFormat:
        returner = _formatEphem(returner, desig)

    return returner


def pullEphems(mpcInst, designations: list, whenDt: datetime, minAltitudeLimit, schedulerFormat=False):
    """
    Use pullEphem to pull ephemerides for multiple targets, given a list of their designations. Requires internet connection.
    :param mpcInst: An instance of the MPCNeoConfirm class from the (privileged) photometrics.mpc_neo_confirm module
    :param designations: A list of designations (strings) of the targets to retrieve
    :param whenDt: A datetime object representing the time for which the ephemeris should be generated
    :param minAltitudeLimit: The lower altitude limit, below which ephemeris lines will not be generated
    :return: a Dictionary of {designation: {startTimeDt: ephemLine}}
    """
    ephemsDict = {}
    for desig in designations:
        ephemsDict[desig] = pullEphem(mpcInst, desig, whenDt, minAltitudeLimit, schedulerFormat)
    return ephemsDict


async def asyncMultiEphem(designations, when, minAltitudeLimit, mpcInst: mpc, asyncHelper: asyncUtils.AsyncHelper,
                          logger, autoFormat=False,
                          mpcPostURL='https://cgi.minorplanetcenter.net/cgi-bin/confirmeph2.cgi', obsCode=654):
    """
    Asynchronously retrieves and parses multiple ephemeris data for given designations.

   :param designations: A list of object designations.
   :type designations: List[str]
   :param when: The datetime indicating the time of the ephemeris.
   :type when: datetime.datetime
   :param minAltitudeLimit: The minimum altitude limit for observability.
   :type minAltitudeLimit: float
   :param mpcInst: An instance of the `mpc` class.
   :type mpcInst: mpc
   :param asyncHelper: An instance of the `asyncUtils.AsyncHelper` class.
   :type asyncHelper: asyncUtils.AsyncHelper
   :param logger: The logger object for logging purposes.
   :param autoFormat: (Optional) Indicates whether to automatically format the ephemeris data. Defaults to False.
   :type autoFormat: bool
   :param mpcPostURL: (Optional) The URL for the MPC ephemeris confirmation. Defaults to 'https://cgi.minorplanetcenter.net/cgi-bin/confirmeph2.cgi'.
   :type mpcPostURL: str
   :param obsCode: (Optional) The observatory code. Defaults to 654.
   :type obsCode: int

   :return: A dictionary containing the parsed ephemeris data for each designation.
   :rtype: Dict[str, List[Tuple[datetime.datetime, str, float, str, str, Any]]]
    """
    ephemResults, ephemDict = await asyncMultiEphemRequest(designations, when, minAltitudeLimit, mpcInst, asyncHelper,
                                                           logger, mpcPostURL, obsCode)
    designations = ephemResults.keys()

    for designation in designations:
        # parse valid ephems
        ephem = ephemResults[designation][0]
        if ephem is None:
            print("No ephem for",designation)
            ephemDict[designation] = None
            continue

        ephem = ephem.find_all('pre')
        if len(ephem) == 0:
            print("No pre tags for ephem",designation)
            ephemDict[designation] = None
            continue

        ephem = ephem[0].contents
        numRecs = len(ephem)

        # get object coordinates
        if numRecs == 1:
            logger.warning('Target ' + designation + ' is not observable')
        else:
            obsList = []
            ephem_entry_num = -1
            for i in range(0, numRecs - 3, 4):
                # get datetime, ra, dec, vmag and motion
                if i == 0:
                    obsRec = ephem[i].split('\n')[-1].replace('\n', '')
                else:
                    obsRec = ephem[i].replace('\n', '').replace('!', '').replace('*', '')

                # keep a running count of ephem entries
                ephem_entry_num += 1

                # parse obs_rec
                obsDatetime, coords, vMag, vRa, vDec = mpcInst._MPCNeoConfirm__parse_ephemeris(obsRec)

                deltaErr = None

                obsList.append((obsDatetime, coords, vMag, vRa, vDec, deltaErr))
            if autoFormat:
                obsList = _formatEphem(obsList, designation)
            ephemDict[designation] = obsList
    return ephemDict


async def asyncMultiEphemRequest(designations, when, minAltitudeLimit, mpcInst: mpc,
                                 asyncHelper: asyncUtils.AsyncHelper, logger,
                                 mpcPostURL='https://cgi.minorplanetcenter.net/cgi-bin/confirmeph2.cgi', obsCode=654):
    """
    Asynchronously retrieve ephemerides for multiple objects. Requires internet connection.
    :param designations: A list of designations (strings) of the targets to objects
    :param when: 'now', a datetime object representing the time for which the ephemeris should be generated, or a string in the format 'YYYY-MM-DDTHH:MM:SS'
    :param minAltitudeLimit: The lower altitude limit, below which ephemeris lines will not be generated
    :param mpcInst: An instance of the MPCNeoConfirm class from the (privileged) photometrics.mpc_neo_confirm module
    :param asyncHelper: An instance of the asyncHelper class
    :return: Result of query in _____ form
    """
    designations = list(set(designations))  # filter for only unique desigs
    urls = [mpcPostURL] * len(designations)
    postContents = {}
    defaultPostParams = {'mb': '-30', 'mf': '30', 'dl': '-90', 'du': '+90', 'nl': '0', 'nu': '100', 'sort': 'd',
                         'W': 'j',
                         'obj': 'None', 'Parallax': '1', 'obscode': obsCode, 'long': '',
                         'lat': '', 'alt': '', 'int': mpcInst.int, 'start': None, 'raty': mpcInst.raty,
                         'mot': mpcInst.mot,
                         'dmot': mpcInst.dmot, 'out': mpcInst.out, 'sun': mpcInst.supress_output,
                         'oalt': str(minAltitudeLimit)
                         }
    start_at = 0

    now_dt = datetime.utcnow().replace(tzinfo=pytz.UTC)

    if when != "now":
        # if we've been given a string, convert it to dt. Otherwise, assume we have a dt and carry on
        if isinstance(when, str):
            when = datetime.strptime(when, '%Y-%m-%dT%H:%M')
        when = when.replace(tzinfo=pytz.UTC)
        if now_dt < when:
            start_at = round((when - now_dt).total_seconds() / 3600.) + 1

    for objectName in designations:
        newPostContent = defaultPostParams.copy()
        newPostContent["start"] = start_at
        newPostContent["obj"] = objectName
        postContents[objectName] = newPostContent

    ephemResults = await asyncHelper.multiGet(urls, designations, soup=True, postContent=list(postContents.values()))

    ephemDict = {}
    failedList = []

    for designation in designations:
        if designation not in ephemResults.keys() or ephemResults[designation] is None:
            logger.debug("Request for ephemeris for candidate " + designation + " failed. Will retry.")
            failedList.append(designation)

    if len(failedList):
        logger.debug("Retrying...")
        retryPost = [postContents[a] for a in failedList]
        retryEphems = await asyncHelper.multiGet([mpcPostURL] * len(failedList), failedList, soup=True,
                                                 postContent=retryPost)

        for retryDesignation in failedList:
            if retryDesignation not in retryEphems.keys() or retryEphems[retryDesignation] is None:
                logger.debug("Request for", retryDesignation, "failed on retry. Eliminating and moving on.")
                ephemDict[retryDesignation] = None
            else:
                ephemResults[retryDesignation] = retryEphems[retryDesignation]

    return ephemResults, ephemDict


strMonthDict = dict(
    zip(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], range(1, 13)))


def updatedStringToDatetime(updated):
    """
    Convert the string from the "Updated" field of the MPC list to a datetime object
    :param updated: string
    :return: datetime
    """
    if not updated:
        return None
    updated = updated.split()[1:3]
    month = strMonthDict[updated[0][:3]]
    fractionalDay, integerDay = math.modf(float(updated[1]))
    year = datetime.today().year
    return datetime(year, month, int(integerDay)) + timedelta(days=fractionalDay)


def candidatesForTimeRange(obsStart, obsEnd, duration, dbConnection):
    candidates = dbConnection.table_query("Candidates", "*",
                                          "RemovedReason IS NULL AND RejectedReason IS NULL AND CandidateType IS \"MPC NEO\" AND DateAdded > ?",
                                          [datetime.utcnow() - timedelta(hours=36)], returnAsCandidates=True)

    res = [candidate for candidate in candidates if candidate.isObservableBetween(obsStart, obsEnd, duration)]
    candidateDict = {}
    for c in res:
        if c.CandidateName not in candidateDict.keys():
            candidateDict[c.CandidateName] = c
        else:
            duplicate = candidateDict[c.CandidateName]
            if genUtils.stringToTime(duplicate.Updated) < genUtils.stringToTime(c.Updated):
                candidateDict[c.CandidateName] = c
    res = list(candidateDict.values())
    return res
