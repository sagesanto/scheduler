#---standard
import json, pandas as pd, time, os, asyncio

#---webtools
import httpx #this and selenium are our main tools for interacting with the web
from io import BytesIO # to support in saving images
from PIL import Image #to save uncertainty map images
from bs4 import BeautifulSoup #to parse html files

# --- Selenium allows us to control the browser
from selenium import webdriver
from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By

#--- astronomy stuff
from astropy.time import Time
from astral import LocationInfo, zoneinfo
from datetime import datetime, timezone,timedelta
from astropy.coordinates import Angle

mapClient = httpx.AsyncClient(follow_redirects=True,timeout=45.0) #web client for saving error maps

saveImages = False
debug = True
headless = True

ERRORRANGE = 300
NOBSMAX = 100000000
VMAGMAX = 21
SCOREMIN = 50
MAXTRANSIT = 6 #maximum number of hours until object transits
MINTRANSIT = 0 #make negative to allow the object to have already transited

TMO = LocationInfo(name='TMO', region='CA, USA', timezone='UTC', latitude=34.36, longitude=-117.63)
sidereal = Time(datetime.utcnow(), scale='utc').sidereal_time(kind="apparent",longitude=TMO.longitude)

#---start the selenium instance---
opts = webdriver.FirefoxOptions()

programStartTime = time.time()
if headless:
    opts.headless = True
browser = webdriver.Firefox(options=opts)



async def saveHTML(url,filename):
    async with httpx.AsyncClient(follow_redirects=True) as client:
        rawFile = await client.get(url)
    open(filename, 'wb').write(rawFile.content)

async def saveMapImage(url,filePath):
    global mapClient
    if debug:
        print("Starting async save for",filePath)
    name = filePath[31:]
    try:
        response = await mapClient.get(url)
    except httpx.TimeoutException:
        print("Timed out on url",url,"which corresponded to",name)
        open(filePath.replace(name,'')+"SAVE-FAILED-"+name, 'wb').write("The program timed out while trying to fetch this error map, which was last seen at "+url+" - be advised that these links expire quickly.")
        return("Fail")

    soup = BeautifulSoup(response.text, 'html.parser')
    image = soup.find('img')
    image_url = "https://cgi.minorplanetcenter.net/"+image['src']

    async with httpx.AsyncClient(follow_redirects=True) as client:
        imgResponse = await client.get(image_url)
    img = Image.open(BytesIO(imgResponse.content))
    img.save(filePath)
    return("Success")

def pullNEO():
    global debug
    mpcJson = httpx.get("https://www.minorplanetcenter.net/Extended_Files/neocp.json").json()
    # print(mpcJson)
    # open('./neocp.json', 'wb').write(mpcJson)
    mpcDf = pd.json_normalize(mpcJson)
    print(mpcDf)
    return mpcDf

def timeUntilTransit(RA):
    global sidereal
    RA = Angle(str(RA)+"h")
    return (RA-sidereal).hour

def slice(updatedTime):
    return updatedTime[-12:]

def passOne(vMagMax, nObsMax, scoreMin):
    global NOBSMAX, VMAGMAX, MAXTRANSIT, MINTRANSIT
    df = pullNEO().drop(labels=["Discovery_year", "Discovery_month", "Discovery_day"], axis=1)
    filtDf = df.loc[(df['Score'] >= scoreMin) & (df['V'] <= vMagMax) & (df['NObs'] <= nObsMax)]
    filtDf['TransitDiff'] = filtDf.apply(lambda row: timeUntilTransit(row['R.A.']), axis=1)
    filtDf = filtDf.loc[(filtDf['TransitDiff'] >= MINTRANSIT) & (filtDf['TransitDiff'] <= MAXTRANSIT)]
    # if debug:
        # print(filtDf)
        # print(filtDf.columns)
    # filtDf['Updated'] = filtDf.apply(lambda row: slice(row['Updated']), axis=0)
    dfSort = filtDf.sort_values(by=["Updated"], ascending=True)
    return dfSort


def clickButton(browser, xpath, name, index=None):  # name is just for readability
    global debug
    if index is not None:
        button = browser.find_elements(By.XPATH,xpath)[index] #note the plural of element
    else:
        button = browser.find_element(By.XPATH, xpath)
    if debug:
        print("Clicked", name)
    button.click()



def generateEphemerides(designations):
    global browser
    if headless:
        print("Launching headless browser")
    # get MPC website
    browser.get('https://minorplanetcenter.net/iau/NEO/toconfirm_tabular.html')
    # wait for it to load
    time.sleep(2)

    # ---find and check the boxes of all the neos we are interested in---
    try:
        i = 0
        for name in designations:
            i+=1
            checkbox = browser.find_element(By.XPATH, "//input[@value='" + name + "']")
            if not checkbox.get_dom_attribute("checked") == "true":
                if debug:
                    print("[" + str(i) + "] Clicking for", name)
                checkbox.click()
    except NoSuchElementException:
        print("Couldn't find element matching", name)

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
    global browser
    n = len(designations)
    dir = "OffsetMaps" + datetime.now().strftime("%m_%d_%Y-%H_%M_%S")
    os.mkdir(dir)
    offsetDict = {}
    startTime = time.time()
    tasks = []

    #---now, we're going to try to request each object's offsets and uncertainty map. we'll do this en masse, save the maps, then move on to process the uncertainty responses
    for i in range(n):
        # identify the object - the object's name is in /html/body/p[n]/b where n starts at 8 and increments by 4
        name = browser.find_element(By.XPATH, "/html/body/p["+str(8+4*i)+"]/b").text
        if debug:
            print("Retrieving uncertainty for",name)
        #find the links to the map and offset page for the object
        mapLink = browser.find_element(By.XPATH, "/html/body/pre["+str(i+1)+"]/a[1]").get_dom_attribute('href')
        offsetLink = browser.find_element(By.XPATH, "/html/body/pre["+str(i+1)+"]/a[2]").get_dom_attribute('href')

        #--- use the links we just found ---
        #asynchronously save the map as an image for observer use
        if saveImages:
            imageTask = asyncio.create_task(saveMapImage(mapLink,dir+"/"+name+"Map.png"))
            tasks.append(imageTask)
        else:
            print("saveImages is False, skipping save step")
        await mapClient.aclose()
        #store the urls - we'll process these in a moment
        offsetDict[name] = offsetLink

    offsetTask = asyncio.create_task(asyncOffsetProcessor(offsetDict))
    tasks.append(offsetTask)

    returner = await asyncio.gather(*tasks) #this return value stuff is dubious at best
    # if debug:
    #     typesList = [type(a) for a in returner]
    #     print("Returning types:",typesList)
    timeDifference = time.time() - startTime
    print(f'Scraping and saving took %.2f seconds.' % timeDifference)
    return offsetDict

def extractUncertainty(name, offsetDict):
    global debug
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
    print(raList,decList)
    maxRA = max(abs(min(raList)),abs(max(raList)))
    maxDec = max(abs(min(decList)), abs(max(decList)))

    return max(maxRA,maxDec)

## -- main --

targetDf = passOne(VMAGMAX, NOBSMAX, SCOREMIN)


if debug:
    print("Unfiltered targets:")
    print(targetDf.to_string())

designations = targetDf["Temp_Desig"].to_list()
print("The following", len(designations), "objects meet the criteria:")
print(designations)

generateEphemerides(designations)

loop = asyncio.get_event_loop()
offsetDict = loop.run_until_complete(navigateEphemerides(designations))

targetDf["Uncertainty"] = targetDf.apply(lambda row: extractUncertainty(row['Temp_Desig'],offsetDict), axis=1)

#filter out the high uncertainty targets. should log somewhere along here! then can use log to detect new targets
# targetDf =

if debug:
    print(" \n\nUncertainties found:\n\n"+targetDf.to_string())

totalDuration = time.time() - programStartTime
print(f'\nCompleted with total runtime of %.2f seconds.' % totalDuration)