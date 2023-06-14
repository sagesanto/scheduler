import time, logging, sys, asyncio
from mpcCandidateLogger import runLogging
from mpcCandidateSelector import selectTargets
from scheduleLib import generalUtils
from datetime import datetime as dt, timedelta

def filter(record):
    info = sys.exc_info()
    if info[1]:
        logging.exception('Exception!',exc_info=info)
        print("---Exception!---",info)
    return True

dateFormat = '%m/%d/%Y %H:%M:%S'

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', filename='mpcCandidate.log', encoding='utf-8',
                    datefmt=dateFormat, level=logging.INFO)  #set to debug for more info
logger.addFilter(filter)

interval = 15

while True:
    try:
        asyncio.run(runLogging(logger))
        generalUtils.logAndPrint("Finished MPC logging without error at " + dt.now().strftime(dateFormat)+" PST",logger.info)
    except Exception as e:
        generalUtils.logAndPrint("Logging targets failed! Skipping.",logger.exception)

    print("Sleeping for thirty seconds...")
    time.sleep(30)
    try:
        asyncio.run(selectTargets(logger))
        generalUtils.logAndPrint("Finished MPC selection without error at " + dt.now().strftime(dateFormat)+" PST",logger.info)
    except Exception as e:
        generalUtils.logAndPrint("Selecting targets failed! Skipping.",logger.exception)

    generalUtils.logAndPrint("Done. will run again at "+ (dt.now()+timedelta(minutes=interval)).strftime(dateFormat)+" PST.",logger.info)
    print("\n")
    time.sleep(interval*60)

