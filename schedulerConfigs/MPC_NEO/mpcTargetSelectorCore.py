# Sage Santomenna 2023

from datetime import datetime, timezone, timedelta
import sys, os
# ---webtools
import httpx
# ---standard
import logging
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytz
from astral import LocationInfo
from astral import sun
from astropy.coordinates import Angle
# --- astronomy stuff
from astropy.time import Time
from bs4 import BeautifulSoup  # to parse html files
from numpy import sqrt
from photometrics.mpc_neo_confirm import MPCNeoConfirm as mpcObj

from schedulerConfigs.MPC_NEO import mpcUtils
# general fuckery
try:
    grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
    sys.path.append(
        grandparentDir)
    from scheduleLib import genUtils, asyncUtils
    sys.path.remove(grandparentDir)
except:
    from scheduleLib import genUtils, asyncUtils

utc = pytz.UTC

BLACK = [0, 0, 0]
RED = [255, 0, 0]
GREEN = [0, 255, 0]
BLUE = [0, 0, 255]
ORANGE = [255, 191, 0]
PURPLE = [221, 160, 221]


def remove_tags(html):
    # parse html content
    soup = BeautifulSoup(html, "html.parser")
    for data in soup(['style', 'script']):
        # Remove tags
        data.decompose()

    # return data by retrieving the tag content
    return ' '.join(soup.stripped_strings)


def rootMeanSquared(vals):
    return sqrt(1 / len(vals) * sum([i ** 2 for i in vals]))


class TargetSelector:
    def __init__(self, startTimeUTC="now", endTimeUTC="sunrise", raMaxRMSE=360, decMaxRMSE=360, nObsMax=1000,
                 vMagMax=21.5,
                 scoreMin=0, decMax=65, decMin=-25, altitudeLimit=0, obsCode=654, obsName="TMO", region="CA, USA",
                 obsTimezone="UTC", obsLat=34.36, obsLon=-117.63):
        """
        The TargetSelector object, around which the MPC target selector is built
        :param startTimeUTC: The earliest start time for an observing window. Can be ``"now"``, ``"sunset"``, or of the form ``"%Y%m%d %H%M"``
        :param endTimeUTC: The latest time the last observation can end. Can be ``"sunrise"`` or of the form ``"%Y%m%d %H%M"``. *NOTE "sunrise" actually refers to the time one hour before sunrise. . .*
        :param nObsMax: The maximum number of times an object can have already been observed and still be selected
        :param vMagMax: The maximum magnitude of viable targets
        :param scoreMin: The minimum score of viable targets
        :param decMax: The maximum declination of viable targets
        :param decMin: The minimum declination of viable targets
        :param altitudeLimit: The lower altitude limit for ephemeris generation, below which ephemeris lines will not be generated
        :param obsCode: The MPC observatory code of the observatory
        :param obsName: The name of the observatory
        :param region: The region of the observatory. Must be a valid initializer for astral.LocationInfo.region
        :param obsTimezone: The timezone of the observatory. Must be a valid initializer for ``astral.LocationInfo.timezone``
        :param obsLat: The latitude of the observatory. Must be a valid initializer for ``astral.LocationInfo.latitude``
        :param obsLon: The longitude of the observatory. Must be a valid intializer for ``astral.LocationInfo.longitude``
        """

        # set up the logger
        self.logger = logging.getLogger(__name__)

        # set location
        self.observatory = LocationInfo(name=obsName, region=region, timezone=obsTimezone, latitude=obsLat,
                                        longitude=obsLon)
        # find sunrise and sunset
        s = sun.sun(self.observatory.observer, date=datetime.now(timezone.utc), tzinfo=timezone.utc)
        self.sunriseUTC = s["sunrise"]

        now_dt = datetime.utcnow()
        now_dt = utc.localize(now_dt)

        if self.sunriseUTC < now_dt:  # if the sunrise we found is earlier than the current time, add one day to it (approximation ofc)
            self.sunriseUTC = self.sunriseUTC + timedelta(days=1)
        self.sunsetUTC = sun.time_at_elevation(self.observatory.observer, -10)

        # parse start time
        if startTimeUTC == "sunset":
            startTimeUTC = self.sunsetUTC
        elif startTimeUTC != 'now':
            startTime_dt = utc.localize(datetime.strptime(startTimeUTC, '%Y-%m-%d %H:%M'))
            if now_dt < startTime_dt:
                startTimeUTC = startTime_dt
            else:
                print('Observation date should be in future. Setting current date time')
        else:
            startTimeUTC = datetime.utcnow()

        startTimeUTC = utc.localize(startTimeUTC)

        # NOTE: the "sunrise" keyword is actually referring to our close time, which is one hour before sunrise
        if endTimeUTC == "sunrise":
            endTimeUTC = self.sunriseUTC - timedelta(hours=1)
        else:
            endTimeUTC = datetime.strptime(endTimeUTC, '%Y-%m-%d %H:%M')

        if startTimeUTC.tzinfo is None:
            startTimeUTC = utc.localize(startTimeUTC)
        self.startTime = startTimeUTC
        self.endTime = endTimeUTC
        self.siderealStart = Time(self.startTime, scale='utc').sidereal_time(kind="apparent",
                                                                             longitude=self.observatory.longitude)

        self.minHoursBeforeTransit = min(max(self.sunsetUTC - self.startTime, timedelta(hours=-2)),
                                         timedelta(hours=0)).total_seconds() / 3600
        self.maxHoursBeforeTransit = (self.endTime - self.startTime).total_seconds() / 3600

        # i open my wallet and it's full of blood
        self.raMaxRMSE = raMaxRMSE
        self.decMaxRMSE = decMaxRMSE
        self.nObsMax = nObsMax
        self.vMagMax = vMagMax
        self.scoreMin = scoreMin
        self.decMax = decMax
        self.decMin = decMin
        self.altitudeLimit = altitudeLimit
        self.obsCode = obsCode

        # init navtej's mpc retriever
        self.mpc = mpcObj()

        # init here, will use later
        self.objDf = pd.DataFrame(
            columns=["Temp_Desig", "Score", "Discovery_datetime", "R.A.", "Decl.", "V", "Updated", "Note", "NObs",
                     "Arc", "H",
                     "Not_Seen_dys"
                     ])
        self.mpcObjDict = {}
        self.filtDf = pd.DataFrame()
        self.uncertaintyStorage = {}  # this will be {desig : (RAlist,Declist,list[color])}

        # init web client for retrieving offsets
        self.webClient = httpx.Client(follow_redirects=True, timeout=60.0)

        # init AsyncHelper
        self.asyncHelper = asyncUtils.AsyncHelper(followRedirects=True)

    def __del__(self):
        del self.asyncHelper
        self.killClients()

    def printSetupInfo(self):
        durationMinutes = round((self.endTime - self.startTime).total_seconds() / 60)
        formattedDuration = "{:02d}:{:02d}".format(durationMinutes // 60, durationMinutes % 60)
        print(f"Length of window: {formattedDuration} (h:m)")
        print("Starting at", self.startTime.strftime("%Y-%m-%d %H:%M"), "and ending at",
              self.endTime.strftime("%Y-%m-%d %H:%M"), "UTC")
        print("Allowing", self.minHoursBeforeTransit, "hours before transit and", self.maxHoursBeforeTransit,
              "hours after.")

    def getLocalSiderealTime(self, dt: datetime):
        """
        Return the local sidereal time at time dt, as an angle
        :param dt: A datetime object
        :return: Sidereal time, as an astropy Angle
        """
        return Time(dt, scale='utc').sidereal_time(kind="apparent", longitude=self.observatory.longitude)

    @staticmethod
    def _convertMPC(obj):
        # Internal: convert a named tuple mpc object from navtej's code to lists that can be put in a df
        l = [obj.designation, obj.score, obj.discovery_datetime, obj.ra, obj.dec, obj.vmag, obj.updated, obj.note,
             obj.num_obs, obj.arc_length, obj.hmag, obj.not_seen_days]
        for i in range(len(l)):
            if l[i] == "":
                l[i] = None
        return l

    @staticmethod
    def extractUncertainty(name, offsetDict, logger, graph=False, savePath=None):
        """
        Internal: Take the name of an object and an offsetDict, as produced in fetchUncertainties, and extract + format + process the uncertainty values for the target
        :return: list: RMSE for ra, RMSE for dec, highest approach color (string)
        """
        if name not in offsetDict.keys():
            logger.debug("Couldn't find " + name + " in offsetDict")
            return None, None
        soup = offsetDict[name][0]  # for whatever reason, the value is a list and i don't feel like fixing it
        if soup is None:
            return None, None
        for a in soup.findAll('a', href=True):
            a.extract()
        text = soup.findAll('pre')[0].get_text()

        colorPriorityDict = {1: "BLACK", 2: "RED", 3: "ORANGE", 4: "GREEN"}
        colorPriorityList = []
        colorList = []
        # find the color of the error points (indicated by the characters at the end of the line)
        textList = text.split("\n")[1:-1]
        for line in textList:
            color = GREEN  # green is default, change it if we find a relevant symbol at end
            colorPriorityList.append(4)
            if "!!" in line:
                color = RED
                colorPriorityList.append(2)
            elif "!" in line:
                color = ORANGE
                colorPriorityList.append(3)
            elif "***" in line:
                color = BLACK
                colorPriorityList.append(1)
            colorList.append(color)

        # determine what the highest priority color is among all the different error points
        highestPriority = min(colorPriorityList)  # use min because 1 is highest priority
        highestColor = colorPriorityDict[highestPriority]

        if highestColor == "BLACK":
            logger.info(name + " is a near-approach!")

        textList = [a.replace("!", '').replace("+", '').replace("*", '') for a in textList]
        splitList = [[x for x in a.split(" ") if x] for a in textList if a]  # lol
        splitList = [a[0:2] for a in splitList]  # sometimes it will have weird stuff (like "MBA soln") at the end,
        #                                        but in my experience the numbers always come first, so we can just slice them
        raList = [int(a[0]) for a in splitList]
        decList = [int(a[1]) for a in splitList]
        if not raList or not decList:
            logger.warning("uh oh, missing RA or Dec errors for target " + name)
            logger.warning("list of text: " + str(textList))
            logger.warning("splitList: " + str(splitList))

        # calculate RMSE
        rmsRA = rootMeanSquared(raList)
        rmsDec = rootMeanSquared(decList)

        # recreate error plots
        if graph:
            fig, ax = plt.subplots()
            ax.invert_xaxis()
            plt.title(name, fontsize=18)
            plt.suptitle("RMS: " + str(round(rmsRA, 3)) + ", " + str(round(rmsDec, 3)))
            ax.scatter(raList, decList, c=np.array(colorList) / 255.0)
            plt.errorbar(np.mean(raList), np.mean(decList), xerr=rmsRA, yerr=rmsDec)
            plt.show()
            if savePath is not None:
                plt.savefig(savePath + "/" + name + ".png")
            plt.close()

        return round(rmsRA, 2), round(rmsDec, 2), highestColor

    def timeUntilTransit(self, ra: float):
        """
        Time until a target with an RA of ra transits (at the observatory)
        :return: Time until transit in hours, float
        """
        ra = Angle(str(ra) + "h")
        return (ra - self.siderealStart).hour

    def makeMpcDataframe(self):
        """
        Make a dataframe of MPC targets from the named tuples returned by self.mpc.neo_confirm_list. Store as self.objDf
        """
        self.mpc.get_neo_list()
        # this is a dictionary of designations to their mpcObjects
        for obj in self.mpc.neo_confirm_list:
            self.mpcObjDict[obj.designation] = obj
            targetList = TargetSelector._convertMPC(obj)
            newRow = dict(zip(self.objDf.columns, targetList))
            self.objDf.loc[len(self.objDf)] = newRow


    def pruneMpcDf(self):
        """
        Filter self.objDf (populated by makeMpcDataframe) by magnitude, score, hour angle, declination, and number of observations
        """

        # calculate time until transit for each object
        self.objDf['TransitDiff'] = self.objDf.apply(lambda row: self.timeUntilTransit(row['R.A.']), axis=1)
        # original length of the dataframe
        original = len(self.objDf.index)
        print("Before pruning, we started with", original, "objects.")

        # establish the conditions for *excluding* a target
        conditions = [
            (self.objDf['Score'] < self.scoreMin),
            (self.objDf['V'] > self.vMagMax),
            (self.objDf['NObs'] > self.nObsMax),
            (self.objDf['TransitDiff'] < self.minHoursBeforeTransit) | (
                    self.objDf['TransitDiff'] > self.maxHoursBeforeTransit),
            (self.objDf['Decl.'] < self.decMin) | (self.objDf['Decl.'] > self.decMax)
        ]

        removedReasons = ["score", "magnitude", "nObs", "RA", "Declination"]

        # decide whether each target should be removed, and mark the reason why
        self.objDf["removed"] = np.select(conditions, removedReasons)
        # create a dataframe from only the targets not marked for removal
        self.filtDf = self.objDf.loc[(self.objDf["removed"] == "0")]

        for reason in removedReasons:
            print("Removed", len(self.objDf.loc[(self.objDf["removed"] == reason)].index), "targets because of their",
                  reason)

        print("In total, removed", original - len(self.filtDf.index), "targets.")
        print("\033[1;32mNumber of desirable targets found: " + str(len(self.filtDf.index)) + ' \033[0;0m')

        self.filtDf = self.filtDf.sort_values(by=["TransitDiff"], ascending=True)
        return

    def siderealToDate(self, siderealAngle: Angle):
        """
        Convert an angle representing a sidereal time to UTC by relating it to local sidereal time
        :param siderealAngle: astropy Angle
        :return: datetime object, utc
        """
        # ---convert from sidereal to UTC---
        # find the difference between the sidereal observability start time and the sidereal start time of the program
        siderealFromStart = siderealAngle - self.siderealStart
        # add that offset to the utc start time of the program (we know siderealStart is local sidereal time at startTime, so we use it as our reference)
        timeUTC = self.startTime + timedelta(
            hours=siderealFromStart.hour / 1.0027)  # one solar hour is 1.0027 sidereal hours

        return timeUTC

    def dateToSidereal(self, dt: datetime):
        timeDiff = dt - self.startTime
        return self.siderealStart + Angle(str(timeDiff.total_seconds() / 3600) + "h")

    def getObjectUncertainty(self, desig, errURL):
        """
        Get the html of the uncertainty page for an object, given its temporary designation and the url of the page
        :return: A tuple, (designation, html)
        """
        offsetReq = self.webClient.get(errURL)
        soup = BeautifulSoup(offsetReq.content, 'html.parser')
        return tuple([desig, soup])

    async def getFilteredUncertainties(self, graph=False, savePath=None):
        desigs = list(self.filtDf.Temp_Desig)
        offsetDict = await self.fetchUncertainties(desigs)
        self.filtDf = pd.concat((self.filtDf,
                                 self.filtDf.apply(lambda row: pd.Series(
                                     list(TargetSelector.extractUncertainty(row['Temp_Desig'], offsetDict, self.logger,
                                                                            graph, savePath))[0:2],
                                     index=["rmsRA", "rmsDec"],
                                     dtype=float), axis=1)), axis=1)

    async def fetchUncertainties(self, designations: list):
        """
        Asynchronously get the uncertainties of the targets in the filtered dataframe
        """
        # this works like:
        # filtDf -> designations -> ephemeris pages -> uncertainty links -> uncertainty values -> inserted into filtDf

        post_params = {'mb': '-30', 'mf': '30', 'dl': '-90', 'du': '+90', 'nl': '0', 'nu': '100', 'sort': 'd',
                       'W': 'j',
                       'obj': 'P10POWX', 'Parallax': '1', 'obscode': "500", 'long': '',
                       'lat': '', 'alt': '', 'int': self.mpc.int, 'start': None, 'raty': self.mpc.raty,
                       'mot': self.mpc.mot,
                       'dmot': self.mpc.dmot, 'out': self.mpc.out, 'sun': self.mpc.supress_output,
                       'oalt': str(self.altitudeLimit)
                       }  # using 500 for obs code to ensure that we can always get an uncertainty, even if the target is below the horizon
        imageDict = {}  # for image maps, desig:mapURL
        offsetRequestTasks = []  # will store our async tasks for retrieving offsets

        desigs = []
        urls = []
        # TODO: image maps
        for desig in designations:
            # make sure we're not starting in the past
            start_at = 0
            now_dt = utc.localize(datetime.utcnow())
            if now_dt < self.startTime:
                start_at = round((self.startTime - now_dt).total_seconds() / 3600.) + 1

            post_params["start"] = start_at
            post_params["obj"] = desig
            try:
                mpc_request = self.webClient.post(self.mpc.mpc_post_url, data=post_params)
            except (httpx.ConnectError, httpx.HTTPError) as err:
                self.logger.error('Failed to connect to/retrieve data from the MPC. Stopping')
                self.logger.error(err)
                exit()  # this will have to be handled by a wrapper if one is written
            if mpc_request.status_code == 200:
                # extract 'pre' tags from reply
                soup = BeautifulSoup(mpc_request.text, 'html.parser')
                ephem = soup.find_all('pre')[0].contents
                num_recs = len(ephem)

                if num_recs == 1:
                    self.logger.warning('Target is not observable')

                else:
                    errUrl = ephem[3].get('href')
                    urls.append(errUrl)
                    desigs.append(desig)
            else:
                raise ConnectionError

        # # now actually make all the requests
        # thanks to our handy-dandy async helper !!!!!!!!!!
        offsetDict = await self.asyncHelper.multiGet(urls, desigs, soup=True)
        return offsetDict

    def observationViable(self, dt: datetime, ra: Angle, dec: Angle):
        """
        Can a target with RA ra and Dec dec be observed at time dt? Checks hour angle limits.
        :return: bool
        """
        hourAngleWindow = genUtils.getHourAngleLimits(dec)
        raWindow = (self.dateToSidereal(dt) - hourAngleWindow[0],
                    self.dateToSidereal(dt) - hourAngleWindow[1])
        # print("Datetime:",dt)
        # print("Hour angle window:",hourAngleWindow)
        # print("RA window:", raWindow)
        # print("RA, dec:",ra,dec)
        # print("Is within bounds:",ra.is_within_bounds(raWindow[1], raWindow[0]))
        return ra.is_within_bounds(raWindow[1], raWindow[0])

    def isObservable(self, ephem):
        """
        Is observation described by ephemeris line (as dictionary) observable?
        :param ephem: dict
        :return: bool
        """
        if self.decMin < ephem["dec"] < self.decMax:
            RA, dec = genUtils.ensureAngle(ephem["RA"]), genUtils.ensureAngle(ephem["dec"])
            return self.observationViable(ephem["obsTime"], RA, dec)
        return False

    async def calculateObservability(self, desigs: list):
        """
        Calculate the start and end times of the observability window for an object by querying its ephemeris and clipping at sunrise/sunset
        :param desigs: list of designations of objects to be queried - must be valid MPC temp identifiers
        :returns: Dictionary {desig:(startDt,endDt)} or None
        """
        self.logger.info("Waiting on web requests...")
        ephems = await mpcUtils.asyncMultiEphem(desigs, datetime.utcnow(), self.altitudeLimit, self.mpc,
                                                self.asyncHelper, self.logger,
                                                obsCode=500)  # request for geocenter to get more output


        if ephems is None or len(ephems)==0:
            self.logger.error("Couldn't get any ephems for any observability windows!")
            return None
        endTime = mpcUtils.timeFromEphem(list(ephems.values())[-1][-1])

        secondEphems = await mpcUtils.asyncMultiEphem(desigs, endTime, self.altitudeLimit, self.mpc,
                                                self.asyncHelper, self.logger,
                                                obsCode=500)

        windows = {}  # {desig:(startDt,endDt)}
        for desig in desigs:
            obsStart = False
            start = None
            end = None
            if desig not in ephems.keys():
                self.logger.warning(
                    "Couldn't get ephems and so can't calculate observability window for " + desig + ". Skipping.")
                windows[desig] = None
                continue
            if ephems[desig] is None:
                windows[desig] = None
                break

            if desig in secondEphems.keys() and secondEphems[desig] is not None:
                # print("Have",len(ephems[desig]),"ephems. Concatenating...")
                ephems[desig] = ephems[desig] + secondEphems[desig]  # if we got ephems for now and the window following, append them together before continuing
                # print("New len",len(ephems[desig]))
                # print(desig,"can read all the way to",mpcUtils.timeFromEphem(list(ephems.values())[-1][0]))
            for ephem in ephems[desig]:
                ephem = mpcUtils.dictFromEphemLine(ephem)
                obsTime = ephem["obsTime"]
                if self.isObservable(ephem):
                    if not obsStart:  # window begins
                        obsStart = True
                        start = obsTime
                elif obsStart:  # we've already started and we're no longer observable. window over
                    end = obsTime
                    windows[desig] = (start, end)
                    break
                end = obsTime
                if start is None or end is None:  # we've run through all the ephemeris. End the window here, if one was started. otherwise, return None
                    windows[desig] = None
                else:
                    windows[desig] = (start, end)

        for desig in windows.keys():
            if windows[desig] is not None:
                self.logger.debug("Target" + desig + "is visible between" +
                                  windows[desig][0].strftime("%Y-%m-%d %H:%M") + "and" +
                                  windows[desig][1].strftime("%Y-%m-%d %H:%M"))
            else:
                self.logger.debug("Nominal: No valid observability window for target " + desig + ".")
        return windows

    def killClients(self):
        """
        Mandatory: close the internal clients
        """
        self.webClient.close()

    def pruneByError(self):
        """
        Remove targets with rms values > acceptable from the running filtered dataframe
        """
        self.filtDf = self.filtDf.loc[self.filtDf['rmsRA'] <= self.raMaxRMSE]
        self.filtDf = self.filtDf.loc[self.filtDf['rmsDec'] <= self.decMaxRMSE]

    def saveCSVs(self, path):
        """
        Save csvs of the filtered and unfiltered targets to outputDir
        """
        self.filtDf.to_csv(path + "/Targets.csv")
        self.objDf.to_csv(path + "/All.csv")

    def fetchEphem(self, desig):
        """
        Return the ephemeris for a target, using the TargetSelector object's startTime and altitude limits
        :param desig: The temporary designation of the target
        :return: a Dictionary of {startTimeDt: ephemLine}
        """
        return mpcUtils.pullEphem(self.mpc, desig, self.startTime, self.altitudeLimit)

    async def fetchFilteredEphemerides(self):
        """
        Return the ephemerides of only targets that passed filtering. Note: must be called after filtering has been done to return anything meaningful
        :return: a Dictionary of {designation: {startTimeDt: ephemLine}}
        """
        return await mpcUtils.asyncMultiEphem(list(self.filtDf.Temp_Desig), self.startTime, self.altitudeLimit,
                                              self.mpc, self.asyncHelper, self.logger, autoFormat=True)

    def fetchAllEphemerides(self):
        """
        Return the ephemerides of all targets from the initial selection
        :return: a Dictionary of {designation: {startTimeDt: ephemLine}}
        """
        return mpcUtils.pullEphems(self.mpc, self.objDf.Temp_Desig, self.startTime, self.altitudeLimit)


def saveEphemerides(ephems, saveDir):
    """
    Save each set of ephemerides to the file [saveDir]/[desig]_ephems.txt
    :param ephems: The ephemerides to save, in {designation: {startTimeDt: ephemLine}} form
    :param saveDir: The directory to save to
    """
    for desig in ephems.keys():
        outFilename = saveDir + "/" + desig + "_ephems.txt"
        ephemLines = ephems[desig].values()
        with open(outFilename, "w") as f:
            f.write('\n'.join(ephemLines))
