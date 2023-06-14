import asyncio
import logging
import sys
import time

from datetime import datetime as dt, timedelta
from scheduleLib import mpcTargetSelectorCore as targetCore
from scheduleLib.candidateDatabase import CandidateDatabase, Candidate, generateID
from photometrics.mpc_neo_confirm import MPCNeoConfirm as mpcObj
from scheduleLib import mpcUtils, generalUtils, asyncUtils
from scheduleLib.mpcTargetSelectorCore import TargetSelector


def filter(record):
    info = sys.exc_info()
    if info[1]:
        logging.exception('Exception!', exc_info=info)
        print("---Exception!---", info)

    return True

#pull MPC NEO candidates that are not removed and have been modified in the lookback time
#check if they have an observability window or a removal reason. if they do, ignore them
# if they don't, do the selection process. place the rejected reason in the CVal1 slot if rejected
async def selectTargets(logger):
    generalUtils.logAndPrint("--- Selecting ---",logger.info)
    lookback = 8
    mpc = mpcObj()

    dbConnection = CandidateDatabase("./candidate database.db", "MPC Selector")
    targetSelector = TargetSelector()

    candidates = dbConnection.table_query("Candidates","*","RemovedReason IS NULL AND CandidateType IS \"MPC NEO\" AND DateAdded > ?",[dt.now()-timedelta(hours=lookback)],returnAsCandidate=True)
    print(candidates)
    if candidates is None:
        generalUtils.logAndPrint("Candidate Selector: Didn't find any targets in need of updating. All set!",logger.info)
        del(dbConnection)  #explicitly deleting these to make sure they close nicely
        del(targetSelector)
        del(mpc)
        exit()
    else:
        generalUtils.logAndPrint("Finding observability and evaluating "+str(len(candidates))+" objects.",logger.info)

    designations = [candidate.CandidateName for candidate in candidates]
    candidateDict = dict(zip(designations,candidates))
    windows = await targetSelector.calculateObservability(designations)
    candidatesWithWindows = []
    rejected = []
    for desig, window in windows.items():
        if window:
            candidateDict[desig].StartObservability, candidateDict[desig].EndObservability = dbConnection.timeToString(window[0]), dbConnection.timeToString(window[1])
            print(candidateDict[desig])
            candidatesWithWindows.append(desig)
        else:
            candidateDict[desig].RejectedReason = "Observability"
            generalUtils.logAndPrint("Got None window for "+desig+". Rejected for Observability.",logger.info)


    for desig, candidate in candidateDict.items():
        if candidate.RMSE_RA is None or candidate.RMSE_Dec is None:
            generalUtils.logAndPrint("Retrying uncertainty on "+desig)
            offsetDict = await targetSelector.fetchUncertainties([desig])
            uncertainties = TargetSelector._extractUncertainty(desig, offsetDict, logger, graph=False,
                                                               savePath="testingOutputs/plots")  # why did i protect this? who knows
            if uncertainties is not None:
                candidateDict[desig].RMSE_RA, candidateDict[desig].RMSE_Dec = uncertainties
            else:
                generalUtils.logAndPrint("Uncertainty query for " + desig + " came back empty again.", logger.warning)
                generalUtils.logAndPrint("Rejected " + desig + " for incomplete information.", logger.info)
                candidateDict[desig].RejectedReason = "Incomplete"
                continue

        if float(candidate.Magnitude) > targetSelector.vMagMax:
            candidateDict[desig].RejectedReason = "vMag"
            rejected.append(desig)
            generalUtils.logAndPrint("Rejected "+desig+" for magnitude limit.",logger.info)
            continue
        if float(candidate.RMSE_RA) > targetSelector.raMaxRMSE or float(candidate.RMSE_Dec) > targetSelector.decMaxRMSE:
            rejected.append(desig)
            candidateDict[desig].RejectedReason = "RMSE"
            generalUtils.logAndPrint("Rejected "+desig+" for magnitude limit.",logger.info)
            continue


    for desig in candidatesWithWindows:  #if the candidates were rejected but aren't rejected this time through, we assume something has changed and they are now viable, so we remove their rejected reason
        candidate = candidateDict[desig]
        if desig not in rejected and candidate.hasField("RejectedReason"):
            delattr(candidate,"RejectedReason")
            dbConnection.setFieldNullByID(candidate.ID,"RejectedReason")

    for desig, candidate in candidateDict.items():
        dbConnection.editCandidateByID(candidate.ID, candidate.asDict())
        generalUtils.logAndPrint("Updated "+desig+".",logger.info)

    del dbConnection


if __name__ == '__main__':
    #set up the logger
    logger = logging.getLogger(__name__)
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', filename='mpcCandidate.log', encoding='utf-8',
                        datefmt='%m/%d/%Y %H:%M:%S', level=logging.INFO)
    logger.addFilter(filter)

    #run the program
    asyncio.run(selectTargets(logger))