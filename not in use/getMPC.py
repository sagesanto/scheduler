#---standard
import json, pandas as pd, time, os, asyncio, numpy as np

#---webtools
import httpx #this and selenium are our main tools for interacting with the web
from io import BytesIO # to support in saving images
from PIL import Image #to save uncertainty map images
from bs4 import BeautifulSoup #to parse html files

# --- Selenium allows us to control the browser
from selenium import webdriver
from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

#--- astronomy stuff
from astropy.time import Time
from astral import LocationInfo, zoneinfo
from datetime import datetime, timezone,timedelta
from astropy.coordinates import Angle

offsetClient = httpx.AsyncClient(follow_redirects=True,timeout=45.0) #client for uncertainty retrieval

saveImages = False
debug = True
headless = False

if saveImages:
    mapClient = httpx.AsyncClient(follow_redirects=True, timeout=45.0)  # web client for saving error maps

ERRORRANGE = 360
NOBSMAX = 100000000
VMAGMAX = 21.6
SCOREMIN = 50
MAXTRANSIT = 6.75 #maximum number of hours until object transits
MINTRANSIT = 0 #make negative to allow the object to have already transited
DECMAX = 65
DECMIN = -25


TMO = LocationInfo(name='TMO', region='CA, USA', timezone='UTC', latitude=34.36, longitude=-117.63)
sidereal = Time(datetime.utcnow(), scale='utc').sidereal_time(kind="apparent",longitude=TMO.longitude)
programStartTime = time.time()

#---start the selenium instance---
#had to switch from Firefox to Chrome because something (probably a Firefox update an hour previous) prompted selenium to start creating errors
# opts = webdriver.FirefoxOptions()
# if headless:
#     opts.headless = True
#browser = webdriver.Firefox(options=opts)

chrome_options = Options()
chrome_options.add_experimental_option("detach", True)
browser = webdriver.Chrome('drivers/chromedriver.exe', chrome_options=chrome_options)

async def saveHTML(url,filename):
    async with httpx.AsyncClient(follow_redirects=True) as client:
        rawFile = await client.get(url)
    open(filename, 'wb').write(rawFile.content)

async def saveMapImage(url,filePath):
    if debug:
        print("Starting async save for",filePath)
    name = filePath[31:]
    try:
        response = await mapClient.get(url)
    except httpx.TimeoutException:
        print("Timed out on url",url,"which corresponded to",name)
        open(filePath.replace(name,'')+"SAVE-FAILED-"+name+".txt", 'wb').write("The program timed out while trying to fetch this error map, which was last seen at "+url+" - be advised that these links expire quickly.")
        return tuple("Fail",name)

    soup = BeautifulSoup(response.text, 'html.parser')
    image = soup.find('img')
    image_url = "https://cgi.minorplanetcenter.net/"+image['src']

    async with httpx.AsyncClient(follow_redirects=True) as client:
        imgResponse = await client.get(image_url)
    img = Image.open(BytesIO(imgResponse.content))
    img.save(filePath)
    return tuple("Success",name)

# def flagTargetRemoved(df,conditionMask,removedReason):
#     return df.loc[(df['Score'] <= scoreMin)].copy().assign(removed='Score')
#     df["Desirable"] = np.where(df[row] != '[]', True, False)

def pullNEO():
    mpcJson = httpx.get("https://www.minorplanetcenter.net/Extended_Files/neocp.json").json()
    # print(mpcJson)
    # open('./neocp.json', 'wb').write(mpcJson)
    mpcDf = pd.json_normalize(mpcJson)
    print(mpcDf)
    return mpcDf

def timeUntilTransit(RA):
    RA = Angle(str(RA)+"h")
    return (RA-sidereal).hour

def slice(updatedTime):
    return updatedTime[-12:]

def passOne(vMagMax, nObsMax, scoreMin):
    df = pullNEO().drop(labels=["Discovery_year", "Discovery_month", "Discovery_day"], axis=1)
    df['TransitDiff'] = df.apply(lambda row: timeUntilTransit(row['R.A.']), axis=1)
    original = len(df.index)
    # removed = pd.DataFrame(index=list(df.columns))
    print("Before pruning, we started with",original)

    conditions = [
        (df['Score'] <= scoreMin),
        (df['V'] >= vMagMax),
        (df['NObs'] >= nObsMax),
        (df['TransitDiff'] <= MINTRANSIT) | (df['TransitDiff'] >= MAXTRANSIT),
        (df['Decl.'] <= DECMIN) | (df['Decl.'] >= DECMAX)
    ]
    removedReasons = ["score","magnitude","nObs","RA","Declination"]
    df["removed"] = np.select(conditions,removedReasons)
    print("df:\n\n",df.to_string())
    filtDf = df.loc[(df["removed"] == "0")]
    print("Number desirable targets:",len(filtDf.index))

    for reason in removedReasons:
        print("Removed", len(df.loc[(df["removed"] == reason)].index), "targets because of their",reason)

    print("In total, removed",len(df.index)-len(filtDf.index),"targets.")
    # if debug:
        # print(filtDf)
        # print(filtDf.columns)

    # filtDf['Updated'] = filtDf.apply(lambda row: slice(row['Updated']), axis=1)

    filtDf = filtDf.sort_values(by=["TransitDiff"], ascending=True)
    return filtDf,df


def clickButton(browser, xpath, name, index=None):  # name is just for readability
    if index is not None:
        button = browser.find_elements(By.XPATH,xpath)[index] #note the plural of element
    else:
        button = browser.find_element(By.XPATH, xpath)
    # if debug:
    #     print("Clicked", name)
    button.click()


def generateEphemerides(designations):
    if headless:
        print("Launching headless browser")
    # get MPC website
    browser.get('https://minorplanetcenter.net/iau/NEO/toconfirm_tabular.html')
    # wait for it to load
    time.sleep(2)
    # ---find and check the boxes of all the neos we are interested in---
    failed = []
    i = 0
    numChecked = 0
    for name in designations:
        i += 1
        try:
            checkbox = browser.find_element(By.XPATH, "//input[@value='" + name + "']")
            if not checkbox.get_dom_attribute("checked") == "true":
                # if debug:
                #     print("[" + str(i) + "] Clicking for", name)
                    checkbox.click()
                    numChecked +=1
        except NoSuchElementException:
            print("Couldn't find element matching", name)
            failed.append(name)

    #remove the ones that failed.
    for n in failed:
        designations.remove(n)
    print("Fetching details for the following targets failed:",failed)
    print("Checked",numChecked,"targets.",len(designations),"are in the designations list. Hopefully those two numbers are equal.")
    # ---find and fill out the form at the bottom---
    # enter the obsCode
    obsCodeEntry = browser.find_element(By.XPATH, "//input[@name='obscode']")
    obsCodeEntry.clear()
    obsCodeEntry.click()
    obsCodeEntry.send_keys("654")
    # set ephemeris interval
    clickButton(browser, "//input[@name='int']", "10 Minute Ephemeris Interval",2)
    # set dmot
    clickButton(browser, "//input[@name='dmot']", "Separate R.A. and Decl. coordinate motions",1)
    # ---submit---
    clickButton(browser, "//input[@value=' Get ephemerides ']", "Submit")
    return designations

async def asyncOffsetProcessor(offsetDict): #offsetDict will come in {name:offsetUrl} and leave {name:soup}
    print("Beginning asyncOffsetProcessor")
    startTime = time.time()
    async with httpx.AsyncClient(follow_redirects=True,timeout=60.0) as client:
        for name in offsetDict.keys():
            offsetLink = offsetDict[name]
            offsetReq = await client.get(offsetLink)
            soup = BeautifulSoup(offsetReq.content, 'html.parser')
            offsetDict[name] = soup
    # with open("offsetDict.json","w") as f:
    #     json.dump(offsetDict,f)
    timeDifference = time.time() - startTime
    print(f'Offset processing took %.2f seconds.' % timeDifference)
    return offsetDict

#by the time we call this function, we will have already retrieved the initial ephemeris. what we need to do now is navigate the epehemeris so we are later in a place to prune out the ones with the high uncertainty maps.
async def navigateEphemerides(designations):
    n = len(designations)
    dir = "OffsetMaps" + datetime.utcnow().strftime("%m_%d_%Y-%H_%M_%S")
    os.mkdir(dir)
    offsetDict = {}
    mapDict = {}
    startTime = time.time()
    failedList = []
    #---now, we're going to try to request each object's offsets and uncertainty map. we'll do this en masse, save the maps, then move on to process the uncertainty responses
    for i in range(n):
        failed = False
        # identify the object - the object's name is in /html/body/p[n]/b where n starts at 8 and increments by 4
        name = browser.find_element(By.XPATH, "/html/body/p["+str(8+4*i)+"]/b").text
        #find the links to the map and offset page for the object
        try:
            mapLink = browser.find_element(By.XPATH, "/html/body/pre["+str(i+1)+"]/a[1]").get_dom_attribute('href')
            offsetLink = browser.find_element(By.XPATH, "/html/body/pre["+str(i+1)+"]/a[2]").get_dom_attribute('href')
        except NoSuchElementException as e:
            print("Couldn't find links for "+name+". moving on")
            if debug:
                print(name,"had xpath","/html/body/p["+str(8+4*i)+"]/b")
                print("Exception raised:", e.msg)
            failed = True
            failedList.append(name)

        #store the urls - we'll process these in a moment
        if not failed:
            offsetDict[name] = offsetLink
            mapDict[name] = mapLink

    offsetDict = await asyncOffsetProcessor(offsetDict)
    timeDifference = time.time() - startTime
    print(f'Scraping and reading offsets took %.2f seconds.' % timeDifference)
    return offsetDict, mapDict, failedList

def extractUncertainty(name, offsetDict):
    if name not in offsetDict.keys():
        if debug:
           print("Couldn't find",name,"in offsetDict")
        return None
    soup = offsetDict[name]
    for a in soup.findAll('a', href=True):
        a.extract()
    text = soup.findAll('pre')[0].get_text()
    textList = text.replace("!",'').replace("+",'').split("\n")
    splitList = [[x for x in a.split(" ") if x] for a in textList if a]
    splitList = [a for a in splitList if len(a)==2]
    # print("strippedList:",splitList)
    raList = [int(a[0]) for a in splitList]
    decList = [int(a[1]) for a in splitList]
    maxRA = max(abs(min(raList)),abs(max(raList)))
    maxDec = max(abs(min(decList)), abs(max(decList)))

    return max(maxRA,maxDec)

async def saveMaps(mapDict):
    tasks = []
    if saveImages:
        for name in mapDict.keys():
            imageTask = asyncio.create_task(saveMapImage(mapDict[name], dir + "/" + name + "Map.png"))
            tasks.append(imageTask)
    else:
        print("saveImages is False, skipping save step")
        return ["Skip"]

    return await asyncio.gather(*tasks)

## -- main --

targetDf,originalDf = passOne(VMAGMAX, NOBSMAX, SCOREMIN)

#can graph originalDf obs (that aren't in targetDf) as X's with color by value of "removed" column, then graph filtDf over that

designations = targetDf["Temp_Desig"].to_list()
print("The following", len(designations), "objects meet the criteria:")
print(designations)

availableDesig = generateEphemerides(designations)

print(availableDesig)
print(("C97XCV2" in availableDesig))

loop = asyncio.get_event_loop()
offsetDict, mapDict, failedList = loop.run_until_complete(navigateEphemerides(availableDesig))

print("Failed to get uncertainties for",len(failedList),"listed below:")
print(failedList)

targetDf["Uncertainty"] = targetDf.apply(lambda row: extractUncertainty(row['Temp_Desig'],offsetDict), axis=1)

#filter out the high uncertainty targets. should log somewhere along here! then can use log to detect new targets
targetDf = targetDf.loc[targetDf['Uncertainty'] <= ERRORRANGE]
outputFilename = "Targets " + datetime.utcnow().strftime("%m_%d_%Y-%H_%M_%S")+".csv"
targetDf.to_csv(outputFilename,index=False)

mapStatuses = loop.run_until_complete(saveMaps(mapDict))
if saveImages:
    mapClient.aclose()
print("Map statuses:",mapStatuses)

if debug:
    print(" \n\nUncertainties found:\n\n"+targetDf.to_string())

totalDuration = time.time() - programStartTime
browser.quit()
print(f'\nCompleted with total runtime of %.2f seconds.' % totalDuration)