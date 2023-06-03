import asyncio, logging, sys, os
from datetime import datetime
from colorlog import ColoredFormatter
from scheduleLib import mpcTargetSelectorCore as targetCore

# --- set up logging ---
LOGFORMAT = "  %(log_color)s%(levelname)-8s%(reset)s | %(log_color)s%(message)s%(reset)s"
LOG_LEVEL = logging.ERROR
logging.root.setLevel(LOG_LEVEL)  # this may cause problems if used with other programs
formatter = ColoredFormatter(LOGFORMAT)
stream = logging.StreamHandler()
stream.setLevel(LOG_LEVEL)
stream.setFormatter(formatter)

# --- prepare ephem save ---
ephemDir = "testingOutputs/TargetSelect-" + datetime.now().strftime("%m_%d_%Y-%H_%M_%S") + "/ephemeridesDir/"
os.mkdir(ephemDir)

# --- prepare async event loop ---
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# --- initialize selector ---
targetFinder = targetCore.TargetSelector()
targetFinder.logger.addHandler(stream)

# --- perform selection ---
targetFinder.makeMpcDataframe()

targetFinder.pruneMpcDf()

loop.run_until_complete(targetFinder.fetchUncertainties())

print("\033[1;32mUncertainties retrieved:\033[0;0m")
print(targetFinder.filtDf.to_string())

targetFinder.pruneByError()

print("\033[1;32mHere are the targets that meet all criteria:\033[0;0m")
print(targetFinder.filtDf.to_string())

targetFinder.saveCSVs()

# --- save ---
print("Fetching and saving ephemeris for these targets. . .")
targetCore.saveEphemerides(targetFinder.fetchFilteredEphemerides(),ephemDir)

# --- clean up ---
loop.run_until_complete(targetFinder.killClients())
