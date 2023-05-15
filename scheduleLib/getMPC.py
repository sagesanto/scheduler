import json, requests, pandas as pd, time
from selenium import webdriver
from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from astropy.time import Time
from astral import LocationInfo, zoneinfo
from datetime import datetime, timezone,timedelta
from astropy.coordinates import Angle
debug = False

NOBSMAX = 25
VMAGMAX = 21
SCOREMIN = 85
MAXTRANSIT = 5 #maximum number of hours until object transits
MINTRANSIT = 0 #make negative to allow the object to have already transited

TMO = LocationInfo(name='TMO', region='CA, USA', timezone='UTC', latitude=34.36, longitude=-117.63)
sidereal = Time(datetime.utcnow(), scale='utc').sidereal_time(kind="apparent",longitude=TMO.longitude)
print(sidereal)

def pullNEO():
    global debug
    if debug:
        print("Reading from local file")
        return pd.read_csv("NEOs.csv").drop(labels=["Discovery_year", "Discovery_month", "Discovery_day"], axis=1)
    rawFile = requests.get("https://www.minorplanetcenter.net/Extended_Files/neocp.json")
    open('./neocp.json', 'wb').write(rawFile.content)
    mpcJson = json.loads(rawFile.content)
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
    df = pullNEO()
    filtDf = df.loc[(df['Score'] >= scoreMin) & (df['V'] <= vMagMax) & (df['NObs'] <= nObsMax)]
    filtDf['TransitDiff'] = filtDf.apply(lambda row: timeUntilTransit(row['R.A.']), axis=1)
    filtDf = filtDf.loc[(filtDf['TransitDiff'] >= MINTRANSIT) & (filtDf['TransitDiff'] <= MAXTRANSIT)]
    if debug:
        print(filtDf)
        print(filtDf.columns)
    # filtDf['Updated'] = filtDf.apply(lambda row: slice(row['Updated']), axis=0)
    dfSort = filtDf.sort_values(by=["Updated"], ascending=True)
    return dfSort


def clickButton(browser, xpath, name, index=None):  # name is just for readability
    global debug
    if index is not None: # is not None
        button = browser.find_elements(By.XPATH,xpath)[index]
    else:
        button = browser.find_element(By.XPATH, xpath)
    if debug:
        print("Clicked", name)
    button.click()



def navMPC(designations):
    # start selenium instance
    browser = webdriver.Firefox()
    # get MPC website
    browser.get('https://minorplanetcenter.net/iau/NEO/toconfirm_tabular.html')
    # wait for it to load
    time.sleep(2)

    # ---find and check the boxes of all the neos we are interested in---
    try:
        for name in designations:
            checkbox = browser.find_element(By.XPATH, "//input[@value='" + name + "']")
            if not checkbox.get_dom_attribute("checked") == "true":
                print("Clicking for", name)
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


# MPCObjectList = ["C3QUAM1"]
# with open("https __www.minorplanetcenter.net_iau_NEO_toconfirm_tabular.html") as f:
#     soup = BeautifulSoup(f,"html.parser")
# for tag in soup.find_all("td"):
#     # if tag.string in MPCObjectList:
#     print(str(tag))


# for checkbox in checkboxes:
#     if not checkbox.isSelected():
#         checkbox.click()
passOneDf = passOne(VMAGMAX, NOBSMAX, SCOREMIN)
if debug:
    print(passOneDf.to_string())
designations = passOneDf["Temp_Desig"].to_list()
print("The following objects meet the criteria:")
print("Designations:", designations)
navMPC(designations)
