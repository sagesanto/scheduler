import asyncio
import json
import logging
import os
import sys, time
from mpcUtils import asyncMultiEphem
from photometrics.mpc_neo_confirm import MPCNeoConfirm
from datetime import datetime, timedelta
from scheduleLib.asyncUtils import AsyncHelper
import traceback

try:
    desigs, settings = sys.argv[1:3]
    desigs, settings = json.loads(desigs), json.loads(settings)
    print("MPC argv:", sys.argv)

    intervalDict = {0: 3, 1: 2, 2: 1, 3: 0}

    mpcInst = MPCNeoConfirm()
    interval = intervalDict[settings["ephemInterval"]]
    # interval = settings["ephemInterval"]
    mpcInst.int = interval
    asyncInst = AsyncHelper(True, timeout=int(settings["ephemTimeout"]))
    ephems = asyncio.run(
        asyncMultiEphem(desigs, datetime.utcnow() + timedelta(hours=int(settings["ephemStartDelayHrs"])), -15, mpcInst,
                        asyncInst, logger=logging.getLogger("__name__"),
                        autoFormat=settings["ephemFormat"] == 0, obsCode=settings["ephemsObsCode"]))

    print(len(ephems))
    print("Saving")
    sys.stdout.flush()
    for desig, ephDict in ephems.items():
        lines = [l for (_, l) in ephDict.items()] if settings["ephemFormat"] == 0 else [str(e) for e in ephDict]
        with open(settings["ephemsSavePath"] + os.sep + desig, "w") as f:
            f.write('\n'.join(lines))

except Exception as e:
    sys.stderr.write(repr(e))
    sys.stderr.write(traceback.format_exc())
    sys.stderr.flush()
