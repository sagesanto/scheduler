import asyncio
import logging
import sys
import time

from datetime import datetime as dt, timedelta

from colorlog import ColoredFormatter

from scheduleLib import mpcTargetSelectorCore as targetCore
from scheduleLib.candidateDatabase import CandidateDatabase, Candidate, generateID
from photometrics.mpc_neo_confirm import MPCNeoConfirm as mpcObj
from scheduleLib import mpcUtils, genUtils, asyncUtils
from scheduleLib.mpcTargetSelectorCore import TargetSelector


async def getVelocities(desig, mpc, logger, targetSelector):  # get dRA and dDec
    try:
        ephems = await mpcUtils.asyncMultiEphem([desig], dt.utcnow(), 0, mpc, targetSelector.asyncHelper, logger,
                                                obsCode=500)
    except:
        logger.exception("Encountered exception while trying to get ephems for " + desig)
        return None, None
    if desig in ephems.keys():
        first = ephems[desig][0]
        return round(float(first[3]) * 60, 2), round(float(first[4]) * 60, 2)  # we want "/minute
    else:
        logger.info("Can't get velocity for " + desig + ": couldn't get ephemeris.")
    return None, None


async def listEntryToCandidate(entry, mpc, logger, targetSelector):
    constructDict = {}
    CandidateName = entry.designation
    CandidateType = "MPC NEO"
    constructDict["RA"], constructDict["Dec"] = entry.ra, entry.dec
    constructDict["Magnitude"] = entry.vmag
    constructDict["Updated"] = genUtils.timeToString(mpcUtils.updatedStringToDatetime(entry.updated))
    dRA, dDec = await getVelocities(CandidateName, mpc, logger, targetSelector)
    # currently, can't get nObs and Score from mpc_neo_confirm. not going to implement it myself - we'll go without
    if dRA and dDec:
        constructDict["dRA"], constructDict["dDec"] = dRA, dDec
    else:
        logger.warning("Couldn't find velocities for " + CandidateName)

    constructDict["TransitTime"] = genUtils.timeToString(genUtils.findTransitTime(genUtils.ensureAngle(str(constructDict["RA"])+"h"),targetSelector.observatory))
    return Candidate(CandidateName, CandidateType, **constructDict)


def candidateIsRemoved(candidate):
    return candidate.hasField("RemovedReason")


def needsUpdate(listEntry, dbEntry):
    return genUtils.stringToTime(listEntry.Updated) > genUtils.stringToTime(dbEntry.Updated)


def updateCandidate(dbCandidate: Candidate, listCandidate: Candidate, dbConnection: CandidateDatabase):
    id = dbCandidate.ID
    dbConnection.editCandidateByID(id, listCandidate.asDict())


# this is where everything happens
async def runLogging(logger, lookback):
    mpc = mpcObj()
    targetSelector = TargetSelector()
    dbConnection = CandidateDatabase("./candidate database.db", "MPCLogger")

    logger.info("--- Acquiring Candidates ---")
    currentCandidates = {}  # store desig:candidate for each candidate in the MPC's list of current candidates
    mpc.get_neo_list()  # prompt the mpc object to fetch the list
    logger.info("Constructing Candidates from MPC List")
    for entry in mpc.neo_confirm_list:  # access the list and create dict
        ent = await listEntryToCandidate(entry, mpc, logger, targetSelector)  # transform list entries to candidates
        currentCandidates[ent.CandidateName] = ent
    logger.info("Construction complete.")

    desigs = currentCandidates.keys()
    offsetDict = await targetSelector.fetchUncertainties(desigs)
    for desig in desigs:  # loop over the candidates and find their uncertainties, adding them to the candidate object
        uncertainties = list(TargetSelector.extractUncertainty(desig, offsetDict, logger, graph=False,
                                                               savePath="testingOutputs/plots"))  # why did i protect this? who knows
        if uncertainties is not None:
            currentCandidates[desig].RMSE_RA, currentCandidates[desig].RMSE_Dec = uncertainties[0:2]
            currentCandidates[desig].ApproachColor = uncertainties[-1]
        else:
            logger.warning("Uncertainty query for " + desig + " came back empty.")

    static = []
    updated = []  # candidates that appear in both the list and the database and may need to be updated
    new = []  # candidates that appear in the list but not in the database
    removed = []  # candidates that appear in the database but not in the list
    dbCandidates = dbConnection.candidatesAddedSince(
        dt.utcnow() - timedelta(hours=lookback))  # candidates added to the db in the last [lookback] hours

    if dbCandidates:
        dbCandidates = {a.CandidateName: a for a in dbCandidates if a.CandidateType == "MPC NEO"}
        for desig, candidate in currentCandidates.items():
            if desig in dbCandidates.keys():
                if candidateIsRemoved(dbCandidates[desig]):
                    logger.warning(
                        "That's odd. Candidate " + desig + " found in MPC table but marked as removed in database. Skipping and moving on.")
                    continue
                logger.debug("Checking for updates to" + desig)
                if needsUpdate(candidate, dbCandidates[desig]):
                    logger.info("Updating " + desig)
                    updateCandidate(dbCandidates[desig], candidate, dbConnection)
                    updated.append(candidate)
                else:
                    static.append(candidate)
                    logger.debug("None found")
                    continue
            else:
                new.append(candidate)
                continue

        for candidate in dbCandidates.values():
            if candidate.CandidateName not in currentCandidates.keys() and not candidateIsRemoved(
                    candidate):  # remove these candidates
                logger.info(
                    "Candidate " + candidate.CandidateName + " is in the database but not in the MPC table. Marking as removed.")
                ID = candidate.ID
                dbConnection.removeCandidateByID(ID, "Target removed from MPC list")
                removed.append(candidate)
    else:
        logger.info(
            "No candidates added in the last " + str(lookback) + " hours. Adding all targets in list.")
        new = list(currentCandidates.values())

    for candidate in new:  # add these
        newID = dbConnection.insertCandidate(candidate)
        logger.debug(
            "Created " + candidate.CandidateName + " with ID " + str(newID) + ".")

    logger.info("-Assessed Candidates")
    logger.info("New (" + str(len(new)) + ")")
    logger.debug(str(new))
    logger.info("Static (" + str(len(static)) + ")")
    logger.debug(str(static))
    logger.info("Updated (" + str(len(updated)) + ")")
    logger.debug(str(updated))
    logger.info("Removed (" + str(len(removed)) + ")")
    logger.debug(str(removed))

    # generalUtils.logAndPrint("Done. will run again at "+dbConnection.timeToString(dt.now()+timedelta(minutes=interval))+" PST.",logger.info)
    # print("\n")
    del dbConnection  # close the connection to unlock db


if __name__ == "__main__":
    LOGFORMAT = " %(asctime)s %(log_color)s%(levelname)-8s%(reset)s | %(log_color)s%(message)s%(reset)s"
    formatter = ColoredFormatter(LOGFORMAT)
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    stream.setLevel(logging.INFO)
    logger = logging.getLogger(__name__)
    logging.getLogger('').addHandler(stream)
    logging.basicConfig(filename='mpcCandidate.log', encoding='utf-8',
                        datefmt='%m/%d/%Y %H:%M:%S', level=logging.DEBUG)
    logging.getLogger('').addFilter(genUtils.filter)

    asyncio.run(runLogging(logger, 24))
