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

def logAndPrint(msg,loggerMethod):
    loggerMethod(msg)  #logger method is a function like logger.info logger.error etc
    print(msg)

#pull MPC NEO candidates that are not removed and have been modified in the lookback time
#check if they have an observability window or a removal reason. if they do, ignore them
# if they don't, do the selection process. place the rejected reason in the CVal1 slot if rejected
async def main():
    lookback = 8

    dbConnection = CandidateDatabase("./candidate database.db", "MPC Selector")
    mpc = mpcObj()
    targetSelector = TargetSelector()

    candidates = dbConnection.table_query("Candidates","*","RemovedReason IS NULL AND StartObservability IS NULL AND RejectedReason IS NULL AND CandidateType IS \"MPC NEO\" AND DateAdded > ?",[dt.now()-timedelta(hours=lookback)],returnAsCandidate=True)
    print(candidates)

    designations = [candidate.CandidateName for candidate in candidates]
    candidateDict = dict(zip(designations,candidates))

    windows = await targetSelector.calculateObservability(designations)
    for desig, window in windows.items():
        if window:
            candidateDict[desig].StartObservability, candidateDict[desig].EndObservability = dbConnection.timeToString(window[0]), dbConnection.timeToString(window[1])
            print(candidateDict[desig])
        else:
            print("Couldn't get window for",desig)
            candidateDict[desig].RejectedReason = "Observability"

    



asyncio.run(main())