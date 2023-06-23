import asyncio
import logging
import sys
import time

from datetime import datetime as dt, timedelta
from scheduleLib import mpcTargetSelectorCore as targetCore
from scheduleLib.candidateDatabase import CandidateDatabase, Candidate, generateID
from scheduleLib import mpcUtils, genUtils, asyncUtils
from scheduleLib.mpcTargetSelectorCore import TargetSelector


# pull MPC NEO candidates that are not removed and have been added in the last [lookback] hours
# check if they have a removal reason. if they do, ignore them
# if they don't, do the selection process, marking rejected reason if they're not observable by TMO

async def selectTargets(logger, lookback):
    logger.info("--- Selecting ---")

    dbConnection = CandidateDatabase("./candidate database.db", "MPC Selector")
    targetSelector = TargetSelector()

    candidates = dbConnection.table_query("Candidates", "*",
                                          "RemovedReason IS NULL AND CandidateType IS \"MPC NEO\" AND DateAdded > ?",
                                          [dt.utcnow() - timedelta(hours=lookback)], returnAsCandidates=True)
    if candidates is None:
        logger.info("Candidate Selector: Didn't find any targets in need of updating. All set!")
        del dbConnection  # explicitly deleting these to make sure they close nicely
        del targetSelector
        exit()
    else:
        logger.info("Finding observability and evaluating " + str(len(candidates)) + " objects.")

    designations = [candidate.CandidateName for candidate in candidates]
    candidateDict = dict(zip(designations, candidates))
    windows = await targetSelector.calculateObservability(designations)
    candidatesWithWindows = []
    rejected = []  # we're going to later wipe the rejected status of all candidates that are not marked rejected (in case they had been rejected in the past)
    for desig, window in windows.items():
        candidate = candidateDict[desig]
        if window:
            logger.debug("Found window for " + desig + "!")
            if not candidate.isAfterStart(dt.utcnow()) or candidate.isAfterEnd(dt.utcnow()):  # we don't want to change the start time of the window after it has started, unless the whole window is over (we can't generate ephems for the past so we would artificially shorten the window each time we run)
                candidateDict[desig].StartObservability = genUtils.timeToString(window[0])
            candidateDict[desig].EndObservability = genUtils.timeToString(window[1])
            candidatesWithWindows.append(desig)
        else:
            if not candidate.isAfterStart(dt.utcnow()):  # if the canidate has a window and it's already opened, don't mark it
                candidateDict[desig].RejectedReason = "Observability"
                logger.debug("Got None window for " + desig + ". Rejected for Observability.")
            elif candidate.hasField("RejectedReason"):
                rejected.append(candidate)  # we don't want to have the candidate's rejection status get wiped just because it's after the window has started
    logger.info("Rejecting targets")
    for desig, candidate in candidateDict.items():
        if not candidate.hasField("RMSE_RA") or not candidate.hasField("RMSE_Dec"):
            logger.info("Retrying uncertainty on " + desig)
            offsetDict = await targetSelector.fetchUncertainties([desig])
            uncertainties = list(TargetSelector.extractUncertainty(desig, offsetDict, logger, graph=False,
                                                                   savePath="testingOutputs/plots"))
            if None not in uncertainties:
                logger.info("Retry successful")
                candidateDict[desig].RMSE_RA, candidateDict[desig].RMSE_Dec = uncertainties[0], uncertainties[1]
                candidateDict[desig].ApproachColor = uncertainties[2]
            else:
                logger.warning("Uncertainty query for " + desig + " came back empty again.")
                logger.debug("Rejected " + desig + " for incomplete information.")
                candidateDict[desig].RejectedReason = "Incomplete"
                continue
        if float(candidate.Magnitude) > targetSelector.vMagMax:
            candidateDict[desig].RejectedReason = "vMag"
            rejected.append(desig)
            logger.debug("Rejected " + desig + " for magnitude limit.")
            continue
        if float(candidate.RMSE_RA) > targetSelector.raMaxRMSE or float(candidate.RMSE_Dec) > targetSelector.decMaxRMSE:
            rejected.append(desig)
            candidateDict[desig].RejectedReason = "RMSE"
            logger.debug("Rejected " + desig + " for error limit.")
            continue

    for desig in candidatesWithWindows:  # if the candidates were rejected before but aren't rejected this time through, we assume something has changed and they are now viable, so we remove their rejected reason
        candidate = candidateDict[desig]
        if desig not in rejected and candidate.hasField("RejectedReason"):
            delattr(candidate, "RejectedReason")
            dbConnection.setFieldNullByID(candidate.ID, "RejectedReason")
    logger.info("Updating database")
    for desig, candidate in candidateDict.items():
        dbConnection.editCandidateByID(candidate.ID, candidate.asDict())
        logger.debug("Updated " + desig + ".")
    del dbConnection


if __name__ == '__main__':
    # set up the logger
    logger = logging.getLogger(__name__)
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', filename='mpcCandidate.log', encoding='utf-8',
                        datefmt='%m/%d/%Y %H:%M:%S', level=logging.INFO)
    logger.addFilter(genUtils.filter)

    # run the program
    asyncio.run(selectTargets(logger, 24))
