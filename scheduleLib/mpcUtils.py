#Sage Santomenna 2023

from photometrics.mpc_neo_confirm import MPCNeoConfirm as mpc
from datetime import datetime, timedelta
from scheduleLib import asyncUtils
import pytz, math

import httpx
from bs4 import BeautifulSoup
from scheduleLib import generalUtils


# this isn't terribly elegant
def _findExposure(magnitude):
    # Internal: match magnitude to exposure description for TMO
    if magnitude < 19.5:
        return "1.0|300.0"
    if magnitude < 20.5:
        return "1.0|600.0"
    if magnitude < 21.0:
        return "2.0|600.0"
    if magnitude < 21.5:
        return "3.0|600.0"


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


def pullEphem(mpcInst, desig, whenDt, altitudeLimit, schedulerFormat = False):
    """
    Fetch the ephemeris of a target from the MPC NEO confirmation database, given a valid designation. Requires internet connection.
    :param mpcInst: An instance of the MPCNeoConfirm class from the (privileged) photometrics.mpc_neo_confirm module
    :param desig: the temporary designation of the NEO candidate, as it appears on the MPC
    :param whenDt: A datetime object representing the time for which the ephemeris should be generated
    :param altitudeLimit: The lower altitude limit, below which ephemeris lines will not be generated
    :return: A Dictionary {startTimeDt: ephemLine}
    """
    returner = mpcInst.get_ephemeris(desig, when=whenDt.strftime('%Y-%m-%dT%H:%M'),
                                              altitude_limit=altitudeLimit, get_uncertainty=None)
    if schedulerFormat:
        returner = _formatEphem(returner, desig)

    return returner


def pullEphems(mpcInst, designations: list, whenDt: datetime, minAltitudeLimit, schedulerFormat = False):
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
        ephemsDict[desig] = pullEphem(mpcInst,desig, whenDt, minAltitudeLimit,schedulerFormat)
    return ephemsDict

async def asyncMultiEphem(designations, when, minAltitudeLimit, mpcInst: mpc, asyncHelper: asyncUtils.AsyncHelper, logger, autoFormat=False, mpcPostURL ='https://cgi.minorplanetcenter.net/cgi-bin/confirmeph2.cgi'):

    ephemResults, ephemDict = await asyncMultiEphemRequest(designations,when,minAltitudeLimit,mpcInst,asyncHelper,mpcPostURL)
    designations = ephemResults.keys()

    for designation in designations:
        # parse valid ephems
        ephem = ephemResults[designation][0]
        ephem = ephem.find_all('pre')[0].contents
        numRecs = len(ephem)

        # get object coordinates
        if numRecs == 1:
            logger.warning('Target ' + designation + ' is not observable')
            obsList = None
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


async def asyncMultiEphemRequest(designations, when, minAltitudeLimit, mpcInst: mpc, asyncHelper: asyncUtils.AsyncHelper, mpcPostURL ='https://cgi.minorplanetcenter.net/cgi-bin/confirmeph2.cgi'):
    """
    Asynchronously retrieve ephemerides for multiple objects. Requires internet connection.
    :param designations: A list of designations (strings) of the targets to objects
    :param when: 'now', a datetime object representing the time for which the ephemeris should be generated, or a string in the format 'YYYY-MM-DDTHH:MM:SS'
    :param minAltitudeLimit: The lower altitude limit, below which ephemeris lines will not be generated
    :param mpcInst: An instance of the MPCNeoConfirm class from the (privileged) photometrics.mpc_neo_confirm module
    :param asyncHelper: An instance of the asyncHelper class
    :return: Result of query in _____ form
    """
    urls = [mpcPostURL] * len(designations)
    postContents = {}
    defaultPostParams = {'mb': '-30', 'mf': '30', 'dl': '-90', 'du': '+90', 'nl': '0', 'nu': '100', 'sort': 'd',
                   'W': 'j',
                   'obj': 'None', 'Parallax': '1', 'obscode': 654, 'long': '',
                   'lat': '', 'alt': '', 'int': mpcInst.int, 'start': None, 'raty': mpcInst.raty,
                   'mot': mpcInst.mot,
                   'dmot': mpcInst.dmot, 'out': mpcInst.out, 'sun': mpcInst.supress_output,
                   'oalt': str(minAltitudeLimit)
                   }
    start_at = 0
    now_dt = pytz.UTC.localize(datetime.utcnow())
    if when != "now":
        if isinstance(when,str):  # if we've been given a string, convert it to dt. Otherwise, assume we have a dt and carry on
            when = datetime.strptime(when, '%Y-%m-%dT%H:%M')
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
            print("Request for ephemeris for candidate",designation, "failed. Will retry.")
            failedList.append(designation)

    if len(failedList):
        print("Retrying...")
        retryPost = [postContents[a] for a in failedList]
        retryEphems = await asyncHelper.multiGet([mpcPostURL] * len(failedList), failedList, soup=True, postContent=retryPost)

        for retryDesignation in failedList:
            if retryDesignation not in retryEphems.keys() or retryEphems[retryDesignation] is None:
                print("Request for",retryDesignation, "failed on retry. Eliminating and moving on.")
                ephemDict[retryDesignation] = None
            else:
                ephemResults[retryDesignation] = retryEphems[retryDesignation]

    return ephemResults, ephemDict


strMonthDict = dict(zip(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], range(1,13)))

def updatedStringToDatetime(updated):
    if not updated:
        return None
    updated = updated.split()[1:3]
    month = strMonthDict[updated[0][:3]]
    dayAndTime = math.modf(float(updated[1]))
    integerDay = dayAndTime[1]
    fractionalDay = dayAndTime[0]
    year = datetime.today().year
    return datetime(year,month,int(integerDay)) + timedelta(days=fractionalDay)
