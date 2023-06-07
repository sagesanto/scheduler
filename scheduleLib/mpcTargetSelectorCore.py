# ---standard
import json, pandas as pd, time, os, asyncio, sys, numpy as np, logging, pytz
import matplotlib.colors as mcolors, matplotlib.pyplot as plt
from colorlog import ColoredFormatter

# ---webtools
import httpx
from io import BytesIO  # to support in saving images
from PIL import Image  # to save uncertainty map images
from bs4 import BeautifulSoup  # to parse html files

# --- astronomy stuff
from astropy.time import Time
from astral import LocationInfo, zoneinfo
from astral import sun
from datetime import datetime, timezone, timedelta
from astropy.coordinates import Angle
from numpy import sqrt
from astropy import units as u

from photometrics.mpc_neo_confirm import MPCNeoConfirm as mpcObj
import mpcUtils

utc = pytz.UTC

BLACK = [0,0,0]
RED = [255,0,0]
GREEN = [0,255,0]
BLUE = [0,0,255]
ORANGE = [255, 191, 0]
PURPLE = [221,160,221]

def remove_tags(html):
    # parse html content
    soup = BeautifulSoup(html, "html.parser")
    for data in soup(['style', 'script']):
        # Remove tags
        data.decompose()

    # return data by retrieving the tag content
    return ' '.join(soup.stripped_strings)

def rootMeanSquared(vals):
    return sqrt(1/len(vals)*sum([i**2 for i in vals]))

class TargetSelector:
    def __init__(self, startTimeUTC="now", endTimeUTC="sunrise", raMaxRMSE=360, decMaxRMSE=360, nObsMax=1000, vMagMax=21.5,
                 scoreMin=0, decMax=65, decMin=-25, altitudeLimit=0, obsCode=654, obsName="TMO", region="CA, USA",
                 obsTimezone="UTC", obsLat=34.36, obsLon=-117.63):
        """
        The TargetSelector object, around which the MPC target selector is built
        :param startTimeUTC: The earliest start time for an observing window. Can be ``"now"``, ``"sunset"``, or of the form ``"%Y%m%d %H%M"``
        :param endTimeUTC: The latest time the last observation can end. Can be ``"sunrise"`` or of the form ``"%Y%m%d %H%M"``. *NOTE "sunrise" actually refers to the time one hour before sunrise. . .*
        :param errorRange: The max absolute sigma that a target can have and still be selected
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
            print("Adjusting sunrise...")
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
        # if startTimeUTC < self.sunsetUTC:
        #     print("Entered time is before local sunset. Setting start time to local sunset.")
        #     startTimeUTC = self.sunsetUTC

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

        print("Length of window:", self.endTime - self.startTime)
        self.minHoursBeforeTransit = min(max(self.sunsetUTC - self.startTime, timedelta(hours=-2)),
                                         timedelta(hours=0)).total_seconds() / 3600
        self.maxHoursBeforeTransit = (self.endTime - self.startTime).total_seconds() / 3600

        print("Starting at", self.startTime.strftime("%Y-%m-%d %H:%M"), "and ending at",
              self.endTime.strftime("%Y-%m-%d %H:%M"))
        # i open my wallet and it's full of blood
        print("Allowing", self.minHoursBeforeTransit, "hours minimum before transit and", self.maxHoursBeforeTransit,
              "hours after.")
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
        self.uncertaintyStorage = {} #this will be {desig : (RAlist,Declist,list[color])}

        # init web client for retrieving offsets
        self.offsetClient = httpx.AsyncClient(follow_redirects=True, timeout=60.0)

    @staticmethod
    def _convertMPC(obj):
        # Internal: convert a named tuple mpc object from navtej's code to lists that can be put in a df
        l = [obj.designation, obj.score, obj.discovery_datetime, obj.ra, obj.dec, obj.vmag, obj.updated, obj.note,
             obj.num_obs, obj.arc_length, obj.hmag, obj.not_seen_days]
        for i in range(len(l)):
            if l[i] == "":
                l[i] = None
        return l

    def _extractUncertainty(self,name, offsetDict, logger,graph,savePath):
        """
        Internal: Take the name of an object and an offsetDict, as produced in fetchUncertainties, and extract + format + process the uncertainty values for the target
        :return: The maximum absolute uncertainty of the object, to be compared with self.errorRange
        """
        if name not in offsetDict.keys():
            logger.debug("Couldn't find", name, "in offsetDict")
            return None
        soup = offsetDict[name][0]  # for whatever reason, the value is a list and i don't feel like fixing it
        for a in soup.findAll('a', href=True):
            a.extract()
        text = soup.findAll('pre')[0].get_text()

        colorList = []
        #find the color of the error points (indicated by the characters at the end of the line)
        textList = text.split("\n")[1:-1]
        for line in textList:
            color = GREEN
            if "!!" in line:
                color = RED
            elif "!" in line:
                color = ORANGE
            elif "***" in line:
                color = BLACK
            colorList.append(color)
        if BLACK in colorList:
            print(name,"is a near-approach!")
        textList= [a.replace("!", '').replace("+", '').replace("*",'') for a in textList]
        splitList = [[x for x in a.split(" ") if x] for a in textList if a]  # lol
        splitList = [a[0:2] for a in splitList]  # sometimes it will have weird stuff (like "MBA soln") at the end,
        #                                        but in my experience the numbers always come first, so we can just slice them
        raList = [int(a[0]) for a in splitList]
        decList = [int(a[1]) for a in splitList]
        if not raList or not decList:
            print("uh oh, missing RA or Dec errors for target", name)
            print("list of text:", textList)
            print("splitList:", splitList)

        #calculate RMSE
        rmsRA = rootMeanSquared(raList)
        rmsDec = rootMeanSquared(decList)


        # recreate error plots
        if graph:
            fig, ax = plt.subplots()
            ax.invert_xaxis()
            plt.title(name,fontsize=18)
            plt.suptitle("RMS: "+str(round(rmsRA,3))+", "+str(round(rmsDec,3)))
            ax.scatter(raList,decList, c=np.array(colorList) / 255.0)
            plt.errorbar(np.mean(raList),np.mean(decList),xerr = rmsRA,yerr=rmsDec)
            plt.show()
            if savePath is not None:
                plt.savefig(savePath+"/"+name+".png")
            plt.close()

        # maxRA = max(abs(min(raList)), abs(max(raList)))
        # maxDec = max(abs(min(decList)), abs(max(decList)))

        # return max(maxRA, maxDec)
        return rmsRA,rmsDec

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
    
    @staticmethod
    def toDecimal(angle:Angle):
        return float(angle.to_string(decimal=True))  #ew

    @staticmethod
    def toSexagesimal(angle:Angle):
        return angle.to_string()

    @staticmethod
    def ensureAngle(angle):
        """
        Return angle as an astropy Angle, converting if necessary
        :param angle: float, int, hms Sexagesimal string, hms tuple, or astropy Angle
        :return: angle, as an astropy Angle
        """
        if not isinstance(angle,Angle):
            try:
                if isinstance(angle, str) or isinstance(angle, tuple):
                        angle = Angle(angle)
                else:
                    angle = Angle(angle,unit=u.deg)
            except Exception as err:
                print("Error in converting", angle, "to angle")
                raise err
        return angle

    @staticmethod
    def ensureFloat(angle):
        """
        Return angle as an astropy Angle, converting if necessary
        :param angle: float or astropy Angle
        :return: decimal angle, as a float
        """
        if not isinstance(angle,float):
            if isinstance(angle,Angle):
                angle = TargetSelector.toDecimal(angle)
            else:
                angle = float(angle)
        return angle


    @staticmethod
    def getHourAngleLimits(dec):
        """
        Get the hour angle limits of the target's observability window based on its dec.
        :param dec: float, int, or astropy Angle
        :return: A tuple of Angle objects representing the upper and lower hour angle limits
        """
        dec = TargetSelector.ensureFloat(dec)

        horizonBox = {   #{range(decWindow):tuple(minAlt,maxAlt)}
              range(-38, -36): (0, 0),
              range(-36, -34): (-35, 42.6104),
              range(-34, -32): (-35, 45.9539),
              range(-32, -30): (-35, 48.9586),
              range(-30, -28): (-35, 51.6945),
              range(-28, -26): (-35, 54.2121),
              range(-26, -24): (-35, 56.5487),
              range(-24, -22): (-35, 58.7332),
              range(-22, 0): (-35, 60),
              range(0, 46): (-52.5, 60),
              range(46,56): (-37.5,60),
              range(56, 66): (-30, 60),
              range(66, 74): (0, 0)
          }
        for decRange in horizonBox:
            if dec in decRange:  # man this is miserable
                finalDecRange = horizonBox[decRange]
                return tuple([Angle(finalDecRange[0],unit=u.deg),Angle(finalDecRange[1],unit=u.deg)])
        return None


    def siderealToDate(self,siderealAngle:Angle):
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


    def calculateObservability(self,objRA,objDec,dRA,dDec):
        """
        Calculate the start and end times of the observability window for an object, taking into account its velocity
        :param objRA: astropy `Angle` or coercible with `TargetSelector.ensureAngle()`
        :param objDec: astropy `Angle` or coercible with `TargetSelector.ensureAngle()`
        :param dRA: astropy `Angle` or coercible with `TargetSelector.ensureAngle()`
        :param dDec: astropy `Angle` or coercible with `TargetSelector.ensureAngle()`
        :return: tuple(datetime) The start and end times of the window in UTC
        """
        #convert inputs to astropy Angle objects (if they aren't already)
        objRA,objDec,dRA,dDec = TargetSelector.ensureAngle(objRA), TargetSelector.ensureAngle(objDec), TargetSelector.ensureAngle(dRA), TargetSelector.ensureAngle(dDec)

        #we'll start with the naive window and shorten/lengthen it based on the object's speed
        hourAngleWindow = TargetSelector.getHourAngleLimits(objDec)
        siderealAngleWindow = (objRA,objRA)+hourAngleWindow

        #for now, we're not going to subtract the length of the exposure from the end of the window - the scheduler should be able to handle it

        #---use the speed of the object to trim its observability window---

        # find the end of the window
        if dRA > 0:
            raMaxT = siderealAngleWindow[0] + (siderealAngleWindow[1] - objRA)/dRA
        else:
            raMaxT = siderealAngleWindow[1]
        if dDec > 0:
            decMaxT = siderealAngleWindow[0] + (self.decMax-objDec)/dDec
        else:
            decMaxT = siderealAngleWindow[1]
        endObsTime = min(min(raMaxT, decMaxT), siderealAngleWindow[1])


        # find the beginning of the window
        if dRA < 0:
            raMinT = endObsTime + (objRA - siderealAngleWindow[0]) / dRA  #latestEndTime + (initialRA - minimumRA) / dRA
                                                                                      # = latestEndTime + (distance to edge of window)/-speed  -->  dRA is always negative in this clause                                                                   # = latestEndTime - time before runs off edge
                                                                                      # = earliest start time
        else:
            raMinT = siderealAngleWindow[0] #default begin time, this is the earliest we will consider starting

        if dDec < 0:
            decMinT = endObsTime + (objDec - self.decMin) / dDec
        else:
            decMinT = siderealAngleWindow[0] #default begin time

        print("raMinT:",raMinT.hms,"decMinT:",decMinT.hms)
        beginObsTime = max(max(raMinT, decMinT), siderealAngleWindow[0])
        print("beginObsTime:",beginObsTime.hms)

        return tuple([beginObsTime,endObsTime])




    async def getObjectUncertainty(self, desig, errURL):
        """
        Asynchronously get the html of the uncertainty page for an object, given its temporary designation and the url of the page
        :return: A tuple, (designation, html)
        """
        offsetReq = await self.offsetClient.get(errURL)
        soup = BeautifulSoup(offsetReq.content, 'html.parser')
        return tuple([desig, soup])

    async def fetchUncertainties(self,graph=False,savePath = None):
        """
        Asynchronously get the uncertainties of the targets in the filtered dataframe
        """
        # this works like:
        # filtDf -> designations -> ephemeris pages -> uncertainty links -> uncertainty values -> inserted into filtDf

        post_params = {'mb': '-30', 'mf': '30', 'dl': '-90', 'du': '+90', 'nl': '0', 'nu': '100', 'sort': 'd',
                       'W': 'j',
                       'obj': 'P10POWX', 'Parallax': '1', 'obscode': self.obsCode, 'long': '',
                       'lat': '', 'alt': '', 'int': self.mpc.int, 'start': None, 'raty': self.mpc.raty,
                       'mot': self.mpc.mot,
                       'dmot': self.mpc.dmot, 'out': self.mpc.out, 'sun': self.mpc.supress_output,
                       'oalt': str(self.altitudeLimit)
                       }
        imageDict = {}  # for image maps, desig:mapURL
        offsetRequestTasks = []  # will store our async tasks for retrieving offsets

        # TODO: image maps
        for desig in self.filtDf.Temp_Desig:
            # make sure we're not starting in the past
            start_at = 0
            now_dt = utc.localize(datetime.utcnow())
            if now_dt < self.startTime:
                start_at = round((self.startTime - now_dt).total_seconds() / 3600.) + 1

            post_params["start"] = start_at
            post_params["obj"] = desig
            try:
                mpc_request = await self.offsetClient.post(self.mpc.mpc_post_url, data=post_params)
            except (httpx.ConnectError, httpx.HTTPError) as err:
                self.logger.error('Failed to connect/retrieve data from MPC. Stopping')
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
                    reqTask = asyncio.create_task(self.getObjectUncertainty(desig, errUrl))
                    offsetRequestTasks.append(reqTask)
                    # imageUrl = ephem[i + 2].get('href') #this doesnt work lol
                    # imageDict[desig] = imageUrl

        # now actually make all the requests
        offsets = await asyncio.gather(*offsetRequestTasks)
        # offsets is a list of tuples (desig,offset) which needs to be compiled to a dict
        offsetDict = dict()
        for des, off in offsets:
            offsetDict.setdefault(des, []).append(off)

        self.filtDf= pd.concat((self.filtDf,
            self.filtDf.apply(lambda row: pd.Series(self._extractUncertainty(row['Temp_Desig'], offsetDict, self.logger,graph,savePath), index=["rmsRA","rmsDec"],dtype=float),axis=1)), axis=1)

    async def killClients(self):
        """
        Mandatory: close the internal clients
        """
        await self.offsetClient.aclose()

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

    def fetchFilteredEphemerides(self):
        """
        Return the ephemerides of only targets that passed filtering. Note: must be called after filtering has been done to return anything meaningful
        :return: a Dictionary of {designation: {startTimeDt: ephemLine}}
        """
        return mpcUtils.pullEphems(self.mpc, self.filtDf.Temp_Desig, self.startTime, self.altitudeLimit)

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
        outFilename = saveDir + desig + "_ephems.txt"
        ephemLines = ephems[desig].values()
        with open(outFilename, "w") as f:
            f.write('\n'.join(ephemLines))
