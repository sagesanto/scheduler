import asyncio
import json
import logging
import os
import sys, time
from mpcUtils import asyncMultiEphem
from photometrics.mpc_neo_confirm import MPCNeoConfirm
from datetime import datetime, timedelta
from scheduleLib.asyncUtils import AsyncHelper

try:
    desigs, settings = sys.argv[1:3]
    desigs, settings = json.loads(desigs), json.loads(settings)
    print("MPC argv:", sys.argv)

    intervalDict = {"1 minute": 3, "10 minutes": 2, "30 minutes": 1, "1 hour": 0}

    mpcInst = MPCNeoConfirm()
    interval = intervalDict[settings["ephemInterval"]]
    mpcInst.int = interval
    print(mpcInst.int)
    print(interval)
    print(settings["ephemInterval"])

    asyncInst = AsyncHelper(True, timeout=int(settings["ephemTimeout"]))
    ephems = asyncio.run(
        asyncMultiEphem(desigs, datetime.utcnow() + timedelta(hours=int(settings["ephemStartDelayHrs"])), -15, mpcInst,
                        asyncInst, logger=logging.getLogger("__name__"),
                        autoFormat=settings["ephemFormat"] == "Scheduler", obsCode=settings["ephemsObsCode"]))
    print(ephems)
    for desig, ephDict in ephems.items():
        lines = [l for (_,l) in ephDict.items()] if settings["ephemFormat"] == "Scheduler" else ephDict
        with open(settings["ephemsSavePath"]+os.sep+desig,"w") as f:
            f.write('\n'.join(lines))

except Exception as e:
    sys.stderr.write(repr(e))
    sys.stderr.flush()
