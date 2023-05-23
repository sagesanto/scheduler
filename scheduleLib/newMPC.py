#---standard
import json, pandas as pd, time, os, asyncio, sys, numpy as np, logging
from colorlog import ColoredFormatter

#---webtools
import httpx #this and selenium are our main tools for interacting with the web
from io import BytesIO # to support in saving images
from PIL import Image #to save uncertainty map images
from bs4 import BeautifulSoup #to parse html files

#--- astronomy stuff
from astropy.time import Time
from astral import LocationInfo, zoneinfo
from datetime import datetime, timezone,timedelta
from astropy.coordinates import Angle

from photometrics.mpc_neo_confirm import MPCNeoConfirm as mpcObj

LOGFORMAT = "  %(log_color)s%(levelname)-8s%(reset)s | %(log_color)s%(message)s%(reset)s"
LOG_LEVEL = logging.ERROR
logging.root.setLevel(LOG_LEVEL)
formatter = ColoredFormatter(LOGFORMAT)
stream = logging.StreamHandler()
stream.setLevel(LOG_LEVEL)
stream.setFormatter(formatter)


def remove_tags(html):
    # parse html content
    soup = BeautifulSoup(html, "html.parser")

    for data in soup(['style', 'script']):
        # Remove tags
        data.decompose()

    # return data by retrieving the tag content
    return ' '.join(soup.stripped_strings)

class TargetSelector:
    def __init__(self, startTimeUTC="now", errorRange=360, nObsMax=1000, vMagMax=21.5,
                 scoreMin=50, maxHoursBeforeTransit=6.75, minHoursBeforeTransit=0,
                 decMax=65, decMin=-25, altitudeLimit = 0, obsCode = 654, obsName="TMO", region="CA, USA", obsTimezone="UTC", obsLat=34.36, obsLon=-117.63):

        self.logger = logging.getLogger(__name__)
        self.logger.addHandler(stream)

        if startTimeUTC != 'now':
            now_dt = datetime.utcnow()
            startTime_dt = datetime.strptime(startTimeUTC, '%Y-%m-%dT%H:%M')
            if now_dt < startTime_dt:
                startTimeUTC = startTime_dt
            else:
                self.logger.warning('Observation date should be in future. Setting current date time')
        else:
            startTimeUTC = datetime.utcnow()

        self.startTime = startTimeUTC
        self.errorRange = errorRange
        self.nObsMax = nObsMax
        self.vMagMax = vMagMax
        self.scoreMin = scoreMin
        self.maxHoursBeforeTransit = maxHoursBeforeTransit
        self.minHoursBeforeTransit = minHoursBeforeTransit
        self.decMax = decMax
        self.decMin = decMin
        self.altitudeLimit = altitudeLimit
        self.obsCode = obsCode
        self.outputDir = "TargetSelect-" + datetime.now().strftime("%m_%d_%Y-%H_%M_%S")+"/"
        self.ephemDir = self.outputDir+"/ephemeridesDir/"
        os.mkdir(self.outputDir)
        os.mkdir(self.ephemDir)

        self.observatory = LocationInfo(name=obsName, region=region, timezone=obsTimezone, latitude=obsLat, longitude=obsLon)
        self.siderealStart = Time(self.startTime, scale='utc').sidereal_time(kind="apparent", longitude=self.observatory.longitude)

        #init navtej's mpc retriever
        self.mpc = mpcObj()

        #init here, will use later
        self.objDf = pd.DataFrame(
            columns=["Temp_Desig", "Score", "Discovery_datetime", "R.A.", "Decl.", "V", "Updated", "Note", "NObs", "Arc", "H",
                   "Not_Seen_dys"
                   ])
        self.mpcObjDict = {}
        self.filtDf = pd.DataFrame()

        #init web client for retrieving offset maps
        self.offsetClient = httpx.AsyncClient(follow_redirects=True, timeout=60.0)

    @staticmethod
    def convertMPC(obj): #convert a named tuple mpc object from navtej's code to lists that can be put in a df
        l = [obj.designation, obj.score, obj.discovery_datetime, obj.ra, obj.dec, obj.vmag, obj.updated, obj.note, obj.num_obs, obj.arc_length, obj.hmag, obj.not_seen_days]
        for i in range(len(l)):
            if l[i] == "":
                l[i] = None
        return l
    @staticmethod
    def extractUncertainty(name, offsetDict,logger):
        if name not in offsetDict.keys():
            logger.debug("Couldn't find", name, "in offsetDict")
            return None
        soup = offsetDict[name]
        for a in soup.findAll('a', href=True):
            a.extract()
        text = soup.findAll('pre')[0].get_text()
        textList = text.replace("!", '').replace("+", '').split("\n")
        splitList = [[x for x in a.split(" ") if x] for a in textList if a]
        splitList = [a for a in splitList if len(a) == 2]
        raList = [int(a[0]) for a in splitList]
        decList = [int(a[1]) for a in splitList]
        maxRA = max(abs(min(raList)), abs(max(raList)))
        maxDec = max(abs(min(decList)), abs(max(decList)))

        return max(maxRA, maxDec)

    def timeUntilTransit(self,ra):
        ra = Angle(str(ra) + "h")
        return (ra - self.siderealStart).hour


    def makeMpcDataFrame(self):
        self.mpc.get_neo_list()
          # this is a dictionary of designations to their mpcObjects
        for obj in self.mpc.neo_confirm_list:
            self.mpcObjDict[obj.designation] = obj
            targetList = TargetSelector.convertMPC(obj)
            newRow = dict(zip(self.objDf.columns, targetList))
            self.objDf.loc[len(self.objDf)] = newRow

    
    def pruneMpcDf(self):
        self.objDf['TransitDiff'] = self.objDf.apply(lambda row: self.timeUntilTransit(row['R.A.']), axis=1)
        original = len(self.objDf.index)
        # removed = pd.DataFrame(index=list(self.objDf.columns))
        print("Before pruning, we started with", original,"objects.")

        conditions = [
            (self.objDf['Score'] <= self.scoreMin),
            (self.objDf['V'] >= self.vMagMax),
            (self.objDf['NObs'] >= self.nObsMax),
            (self.objDf['TransitDiff'] <= self.minHoursBeforeTransit) | (self.objDf['TransitDiff'] >= self.maxHoursBeforeTransit),
            (self.objDf['Decl.'] <= self.decMin) | (self.objDf['Decl.'] >= self.decMax)
        ]

        removedReasons = ["score", "magnitude", "nObs", "RA", "Declination"]
        self.objDf["removed"] = np.select(conditions, removedReasons)
        self.filtDf = self.objDf.loc[(self.objDf["removed"] == "0")]

        for reason in removedReasons:
            print("Removed", len(self.objDf.loc[(self.objDf["removed"] == reason)].index), "targets because of their", reason)

        print("In total, removed", len(self.objDf.index) - len(self.filtDf.index), "targets.")
        print("\033[1;32mNumber of desirable targets found: " + str(len(self.filtDf.index)) + ' \033[0;0m')


        # filtDf['Updated'] = filtDf.apply(lambda row: slice(row['Updated']), axis=1)

        self.filtDf = self.filtDf.sort_values(by=["TransitDiff"], ascending=True)
        return

    async def fetchUncertainties(self):
        print("Fetching uncertainties of the targets - this may take a while. . .")
        post_params = {'mb': '-30', 'mf': '30', 'dl': '-90', 'du': '+90', 'nl': '0', 'nu': '100', 'sort': 'd',
                       'W': 'j',
                       'obj': 'P10POWX', 'Parallax': '1', 'obscode': self.obsCode, 'long': '',
                       'lat': '', 'alt': '', 'int': self.mpc.int, 'start': None, 'raty': self.mpc.raty, 'mot': self.mpc.mot,
                       'dmot': self.mpc.dmot, 'out': self.mpc.out, 'sun': self.mpc.supress_output, 'oalt': str(self.altitudeLimit)
                       }
        offsetDict = {} #desig:offsetURL
        imageDict = {} #for image maps, desig:mapURL

        #TODO: right now, this retrieves an ephemeris page for each object. should change it to do just one - can form take multiple objects in its header?
        #TODO: image maps
        for desig in self.filtDf.Temp_Desig:
            offsetDict[desig] = None #this will get changed to an error url, if we find one
            #make sure we're notstarting in the past
            start_at = 0
            now_dt = datetime.utcnow()
            if now_dt < self.startTime:
                start_at = round((self.startTime - now_dt).total_seconds() / 3600.) + 1

            post_params["start"] = start_at
            post_params["obj"] = desig
            try:
                mpc_request = await self.offsetClient.post(self.mpc.mpc_post_url, data=post_params)
            except (httpx.ConnectError, httpx.HTTPError) as err:
                self.logger.error('Failed to connect/retrieve data from MPC. Stopping')
                self.logger.error(err)
            else:
                if mpc_request.status_code == 200:
                    # extract 'pre' tags from reply
                    soup = BeautifulSoup(mpc_request.text, 'html.parser')
                    ephem = soup.find_all('pre')[0].contents
                    num_recs = len(ephem)

                    if num_recs == 1:
                        self.logger.warning('Target is not observable')

                    else:
                        ephem_entry_num = -1
                        for i in range(0, num_recs - 3, 4):

                            # keep a running count of ephem entries
                            ephem_entry_num += 1
                            errUrl = ephem[i + 3].get('href')
                            # imageUrl = ephem[i + 2].get('href')
                            offsetDict[desig] = errUrl
                            # imageDict[desig] = imageUrl
                            break
        for desig in offsetDict.keys():
            offsetLink = offsetDict[desig]
            if offsetLink is not None:
                offsetReq = await self.offsetClient.get(offsetLink)
                soup = BeautifulSoup(offsetReq.content, 'html.parser')
                offsetDict[desig] = soup
        self.filtDf["Uncertainty"] = self.filtDf.apply(lambda row: TargetSelector.extractUncertainty(row['Temp_Desig'], offsetDict,self.logger), axis=1)
    async def killClients(self):
        await self.offsetClient.aclose()

    def pruneByError(self):
        print("\033[1;32mUncertainties retrieved. Here are the targets that meet all criteria: \033[0;0m")
        self.filtDf = self.filtDf.loc[self.filtDf['Uncertainty'] <= self.errorRange]
        outputFilename = self.outputDir+"Targets.csv"
        self.filtDf.to_csv(outputFilename, index=False)
        print(self.filtDf.to_string())

    #this isn't terribly elegant
    #TODO: make this less hardcoded
    @staticmethod
    def findExposure(magnitude):
        if magnitude < 19.5:
            return "1.0|300.0"
        if magnitude < 20.5:
            return "1.0|600.0"
        if magnitude < 21.0:
            return "2.0|600.0"
        if magnitude < 21.5:
            return "3.0|600.0"

    @staticmethod
    def formatEphems(ephems,desig):
        #our goal here is to take an object returned from self.mpc.get_ephemeris() and convert it to the scheduler format
        ephemList = ["DateTime|Occupied|Target|Move|RA|Dec|ExposureTime|#Exposure|Filter|Description"]
        for i in ephems:
            #the dateTime in the ephems list is a Time object, need to convert it to string
            i[0].format = "fits"
            i[0].out_subfmt = "date_hms"
            date = i[0].value
            i[0].format = "iso"
            i[0].out_subfmt = "date_hm"
            inBetween = i[0].value
            dateTime = datetime.strptime(inBetween,"%Y-%m-%d %H:%M")
            #name
            target = desig
            #convert the skycoords object to decimal
            coords = i[1].to_string("decimal").replace(" ","|")

            vMag = i[2]
            #get the correct exposure string based on the vMag
            exposure = str(TargetSelector.findExposure(float(vMag)))

            dRa = i[3]
            dDec = i[4]

            #for the description, we need RA and Dec in sexagesimal
            sexagesimal = i[1].to_string("hmsdms").split(" ")
            #the end of the scheduler line must have a description that looks like this
            description = "\'MPC Asteroid " + target + ", UT: " + datetime.strftime(dateTime,"%H%M") + " RA: " + sexagesimal[0] +" DEC: " + sexagesimal[1] + " dRA: " + dRa + " dDEC: " + dDec + "\'"

            lineList = [date,"1",target,"1",coords,exposure,"CLEAR",description]
            expLine = "|".join(lineList)
            ephemList.append(expLine)

        return ephemList

    def saveFilteredEphemerides(self):
        print("Fetching and saving ephemeris for these targets. . .")
        for desig in self.filtDf.Temp_Desig:
            outFilename = self.ephemDir+desig+"_ephems.txt"
            ephems = self.mpc.get_ephemeris(desig,when=self.startTime.strftime('%Y-%m-%dT%H:%M'),altitude_limit=self.altitudeLimit,get_uncertainty=None)
            with open(outFilename,"w") as f:
                f.write('\n'.join(TargetSelector.formatEphems(ephems,desig)))
        print("Ephemeris saved! Find them in",self.ephemDir)



if __name__ == '__main__':
    # programStartTime = time.time()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    targetFinder = TargetSelector()
    targetFinder.makeMpcDataFrame()
    targetFinder.pruneMpcDf()
    loop.run_until_complete(targetFinder.fetchUncertainties())
    targetFinder.pruneByError()

    # partialDuration = time.time()-programStartTime
    # targetFinder.logger.info(f'\nFetched and filtered targets in %.2f seconds.' % partialDuration)

    loop.run_until_complete(targetFinder.killClients())

    targetFinder.saveFilteredEphemerides()

    # totalDuration = time.time() - programStartTime
    # targetFinder.logger.info(f'Completed with total runtime of %.2f seconds.' % totalDuration)




