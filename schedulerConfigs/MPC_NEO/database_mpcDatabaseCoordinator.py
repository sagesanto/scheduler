import asyncio
import logging
import sys, os
import time
from datetime import datetime as dt, timedelta

from colorlog import ColoredFormatter

from mpcCandidateLogger import runLogging
from mpcCandidateSelector import selectTargets

try:
    grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
    sys.path.append(
        grandparentDir)
    from scheduleLib import genUtils
    sys.path.remove(grandparentDir)
except:
    from scheduleLib import genUtils

dateFormat = '%m/%d/%Y %H:%M:%S'

LOGFORMAT = " %(asctime)s %(log_color)s%(levelname)-2s%(reset)s | %(log_color)s%(message)s%(reset)s"
colorFormatter = ColoredFormatter(LOGFORMAT, datefmt=dateFormat)
fileFormatter = formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-2s | %(message)s', datefmt=dateFormat)

stream = logging.StreamHandler()
stream.setFormatter(colorFormatter)
stream.setLevel(logging.INFO if len(sys.argv) == 1 else logging.ERROR)

fileHandler = logging.FileHandler("mpcCandidate.log")
fileHandler.setFormatter(fileFormatter)
fileHandler.setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)

logger.addHandler(fileHandler)
logger.addHandler(stream)

logger.setLevel(logging.DEBUG if len(sys.argv) == 1 else logging.ERROR)

logger.addFilter(genUtils.filter)

dbPath = sys.argv[1] if len(sys.argv) > 1 else "./candidate database.db"

interval = 15  # minutes between runs
lookback = 48  # edit targets that were added within [lookback] hours ago, add a duplicate for older

logger.info("---Starting cycle at "+ dt.now().strftime(dateFormat) + " PST")
try:
    asyncio.run(runLogging(logger,lookback, dbPath))
    logger.info("---Finished MPC logging without error at " + dt.now().strftime(dateFormat) + " PST")
except Exception:
    logger.exception("---Logging targets failed! Skipping.")

try:
    asyncio.run(selectTargets(logger,lookback, dbPath))
    logger.info("---Finished MPC selection without error at " + dt.now().strftime(dateFormat) + " PST")
except Exception:
    logger.exception("Selecting targets failed! Skipping.")

# logger.info("---Done. will run again at " + (dt.now() + timedelta(minutes=interval)).strftime(dateFormat) + " PST.")
logger.info("---Done---")
print("\n")
exit()
    # time.sleep(interval * 60)
