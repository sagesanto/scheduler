import asyncio
import logging
import sys
import time

from datetime import datetime as dt, timedelta

from colorlog import ColoredFormatter

from scheduleLib import mpcTargetSelectorCore as targetCore
from scheduleLib.candidateDatabase import CandidateDatabase, Candidate, generateID
from photometrics.mpc_neo_confirm import MPCNeoConfirm as mpcObj
from scheduleLib import mpcUtils, generalUtils, asyncUtils
from scheduleLib.mpcTargetSelectorCore import TargetSelector

# validFields = ["Author","DateAdded","DateLastEdited","ID",'Night', 'StartObservability', 'EndObservability', 'RA', 'Dec', 'dRA', 'dDec', 'Magnitude', 'RMSE_RA', 'RMSE_Dec', 'ApproachColor', 'Scheduled', 'Observed', 'Processed', 'Submitted', 'Notes', 'CVal1', 'CVal2', 'CVal3', 'CVal4', 'CVal5', 'CVal6', 'CVal7', 'CVal8', 'CVal9', 'CVal10']

lookback = 8  #max hours ago targets that we will edit could have been added
interval = 15  #minutes between running

def filter(record):
    info = sys.exc_info()
    if info[1]:
        logging.exception('Exception!',exc_info=info)
        print("---Exception!---",info)

    return True


def getVelocities(desig,mpc,logger):  #get dRA and dDec
    try:
        ephems = mpcUtils.pullEphem(mpc,desig,dt.utcnow(),0)
    except:
        generalUtils.logAndPrint("Encountered exception while trying to get ephems for "+desig,logger.exception)
    if ephems:
        first = ephems[0]
        return first[3],first[4]

    return None, None

def listEntryToCandidate(entry,db,mpc,logger):
    constructDict = {}
    CandidateName = entry.designation
    CandidateType = "MPC NEO"
    constructDict["RA"], constructDict["Dec"] = entry.ra, entry.dec
    constructDict["Magnitude"] = entry.vmag
    constructDict["Updated"] =  db.timeToString(mpcUtils.updatedStringToDatetime(entry.updated))
    dRA, dDec = getVelocities(CandidateName,mpc,logger)
    #currently, can't get nObs and Score from mpc_neo_confirm. not going to implement it myself - we'll go without
    if dRA and dDec:
        constructDict["dRA"], constructDict["dDec"] = dRA, dDec
    else:
        generalUtils.logAndPrint("Couldn't find velocities for "+CandidateName,logger.warning)
    return Candidate(CandidateName,CandidateType,**constructDict)

def candidateIsRemoved(candidate):
    return "RemovedDt" in candidate.asDict().keys()

def needsUpdate(listEntry, dbEntry, dbConnection:CandidateDatabase):
    return dbConnection.stringToTime(listEntry.Updated) > dbConnection.stringToTime(dbEntry.Updated)

def updateCandidate(dbCandidate:Candidate,listCandidate:Candidate,dbConnection:CandidateDatabase):
    id = dbCandidate.ID
    dbConnection.editCandidateByID(id,listCandidate.asDict())

#this is where everything happens
async def runLogging(logger):
    mpc = mpcObj()
    targetSelector = TargetSelector()
    dbConnection = CandidateDatabase("./candidate database.db", "MPCLogger")

    generalUtils.logAndPrint("--- Grabbing ---",logger.info)
    currentCandidates = {}  # store desig:candidate for each candidate in the MPC's list of current candidates
    mpc.get_neo_list()  #prompt the mpc object to fetch the list
    generalUtils.logAndPrint("Constructing Candidates from MPC List",logger.info)
    for entry in mpc.neo_confirm_list:  #access the list and create dict
        ent = listEntryToCandidate(entry,dbConnection,mpc,logger)  #transform list entries to candidates
        currentCandidates[ent.CandidateName] = ent
    generalUtils.logAndPrint("Construction complete.",logger.info)

    desigs = currentCandidates.keys()
    offsetDict = await targetSelector.fetchUncertainties(desigs)
    for desig in desigs:  #loop over the candidates and find their uncertainties, adding them to the candidate object
        uncertainties = TargetSelector._extractUncertainty(desig, offsetDict,logger,graph=False,savePath="testingOutputs/plots")  #why did i protect this? who knows
        if uncertainties is not None:
            currentCandidates[desig].RMSE_RA, currentCandidates[desig].RMSE_Dec  = uncertainties
        else:
            generalUtils.logAndPrint("Uncertainty query for "+desig+" came back empty.",logger.warning)


    static = []
    updated = []  #candidates that appear in both the list and the database and may need to be updated
    new = []  #candidates that appear in the list but not in the database
    removed = []  #candidates that appear in the database but not in the list
    dbCandidates = dbConnection.candidatesAddedSince(dt.now()-timedelta(hours=lookback))  #candidates added to the db in the last [lookback] hours
    if dbCandidates:
        dbCandidates = {a.CandidateName:a for a in dbCandidates if a.CandidateType == "MPC NEO"}
        for desig, candidate in currentCandidates.items():
            if desig in dbCandidates.keys():
                if candidateIsRemoved(dbCandidates[desig]):
                    generalUtils.logAndPrint("That's odd. Candidate "+desig+" found in MPC table but marked as removed in database. Skipping and moving on.",logger.warning)
                    continue
                generalUtils.logAndPrint("A candidate matching "+desig+" was found in the database. Will check for updates.",logger.debug)
                if needsUpdate(candidate,dbCandidates[desig],dbConnection):
                    generalUtils.logAndPrint("Updating "+desig,logger.info)
                    updateCandidate(dbCandidates[desig],candidate,dbConnection)
                    updated.append(candidate)
                else:
                    static.append(candidate)
                    generalUtils.logAndPrint("Candidate "+desig+" did not need to be updated. Continuing.",logger.debug)
                    continue
            else:
                new.append(candidate)
                continue

        for candidate in dbCandidates.values():
            if candidate.CandidateName not in currentCandidates.keys() and not candidateIsRemoved(
                    candidate):  # remove these candidates
                generalUtils.logAndPrint(
                    "Candidate " + candidate.CandidateName + " is in the database but not in the MPC table. Marking as removed.",
                    logger.info)
                ID = candidate.ID
                dbConnection.removeCandidateByID(ID, "Target removed from MPC list")
                removed.append(candidate)
    else:
        generalUtils.logAndPrint("No candidates added in the last "+str(lookback)+" hours. Adding all targets in list.",logger.info)
        new = list(currentCandidates.values())

    for candidate in new:  # add these
        newID = dbConnection.insertCandidate(candidate)
        generalUtils.logAndPrint("Created new candidate with desig "+candidate.CandidateName+" and ID "+str(newID)+".",logger.debug)

    print("New ("+str(len(new))+"):",new)
    print("Static ("+str(len(static))+"):",static)
    print("Updated ("+str(len(updated))+"):",updated)
    print("Removed ("+str(len(removed))+"):",removed)

    # generalUtils.logAndPrint("Done. will run again at "+dbConnection.timeToString(dt.now()+timedelta(minutes=interval))+" PST.",logger.info)
    # print("\n")
    del dbConnection  #close the connection to unlock db

if __name__ == "__main__":
    LOGFORMAT = " %(asctime)s %(log_color)s%(levelname)-8s%(reset)s | %(log_color)s%(message)s%(reset)s"
    formatter = ColoredFormatter(LOGFORMAT)
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger = logging.getLogger(__name__)
    logging.basicConfig(filename='mpcCandidate.log', encoding='utf-8',
                        datefmt='%m/%d/%Y %H:%M:%S', level=logging.INFO)
    logger.addFilter(filter)

    asyncio.run(runLogging(logger))

