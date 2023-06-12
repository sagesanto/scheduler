import asyncio
import logging
import sys

from datetime import datetime as dt, timedelta
from scheduleLib import mpcTargetSelectorCore as targetCore
from scheduleLib.candidateDatabase import CandidateDatabase, Candidate, generateID
from photometrics.mpc_neo_confirm import MPCNeoConfirm as mpcObj
from scheduleLib import mpcUtils, generalUtils, asyncUtils
from scheduleLib.mpcTargetSelectorCore import TargetSelector

# validFields = ["Author","DateAdded","DateLastEdited","ID",'Night', 'StartObservability', 'EndObservability', 'RA', 'Dec', 'dRA', 'dDec', 'Magnitude', 'RMSE_RA', 'RMSE_Dec', 'ApproachColor', 'Scheduled', 'Observed', 'Processed', 'Submitted', 'Notes', 'CVal1', 'CVal2', 'CVal3', 'CVal4', 'CVal5', 'CVal6', 'CVal7', 'CVal8', 'CVal9', 'CVal10']

def filter(record):
    info = sys.exc_info()
    if info[1]:
        logging.exception('Exception!',exc_info=info)
        print("---Exception!---",info)

    return True

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', filename='mpcCandidate.log', encoding='utf-8',
                    datefmt='%m/%d/%Y %H:%M:%S', level=logging.INFO)
logger.addFilter(filter)

def listEntryToCandidate(entry,db):
    constructDict = {}
    CandidateName = entry.designation
    CandidateType = "MPC NEO"
    constructDict["RA"], constructDict["Dec"] = entry.ra, entry.dec
    constructDict["Magnitude"] = entry.vmag
    constructDict["Updated"] =  db.timeToString(mpcUtils.updatedStringToDatetime(entry.updated))
    return Candidate(CandidateName,CandidateType,**constructDict)

async def main():
    #use all this helpful infrastructure !
    dbConnection = CandidateDatabase("./candidate database.db","MPCLogger")
    mpc = mpcObj()
    targetSelector = TargetSelector()

    lastCandidates = {}
    currentCandidates = {}
    mpc.get_neo_list()  #prep the list

    for entry in mpc.neo_confirm_list:
        ent = listEntryToCandidate(entry,dbConnection)
        currentCandidates[ent.CandidateName] = ent

    desigs = currentCandidates.keys()
    offsetDict = await targetSelector.fetchUncertainties(desigs)
    extractedDict = {}
    for desig in desigs:
        uncertainties = TargetSelector._extractUncertainty(desig, offsetDict,logger,graph=False,savePath="testingOutputs/plots")
        if uncertainties is not None:
            currentCandidates[desig].RMSE_RA, currentCandidates[desig].RMSE_Dec  = uncertainties
    print(list(currentCandidates.values())[0])

    dbCandidates = dbConnection.candidatesAddedSince(dt.now()-timedelta(hours=8))
    if dbCandidates:
        dbCandidates = {a.CandidateName:a for a in dbCandidates if a}

    print(dbCandidates)



    #fetch the list of targets, then
        #determine which ones are new and add them
        #determine which were in the last list but aren't in this one
            #mark them as removed and give a reason
        #determine which have been updated since the last list, and edit them


asyncio.run(main())

