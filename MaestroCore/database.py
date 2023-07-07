import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
import pytz

ephemPrograms = {}
# print(sys.argv)


def generateNextRunTimestampString(delay):
    return (datetime.now() + timedelta(minutes=delay)).strftime("%m/%d %H:%M") + " local / " + (
                datetime.now(pytz.UTC) + timedelta(minutes=delay)).strftime(
        "%m/%d %H:%M") + " UTC"


try:
    root_directory = "./schedulerConfigs"  # Replace with the actual root directory path
    databasePrograms = {}

    for root, dirs, files in os.walk(root_directory):
        subdirectory = root.replace(root_directory, "").strip(os.sep)
        desired_files = [os.sep.join([root, f]) for f in files if
                         f.endswith(".py") and "database_" in f]
        if len(desired_files):
            databasePrograms[subdirectory.replace("_", " ")] = desired_files
    # sys.stdout.write("ephemPrograms:" + str(ephemPrograms))
    # sys.stdout.flush()
    # print("Db programs:", databasePrograms)
    settingsJstr = sys.argv[1]
    settings = json.loads(settingsJstr)
    waitTime = int(settings["databaseWaitTimeMinutes"])
    dbPath = settings["candidateDbPath"]

    while True:
        total = len(databasePrograms.keys())
        run = 0
        for name, program in databasePrograms.items():
            p = subprocess.Popen(['python', program[0], dbPath,
                                  settingsJstr])
            while p.poll() is None:
                l = sys.stdin.readline()
                if l == "Database: Ping!\n":
                    sys.stdout.flush()
                    sys.stdout.write("Database: Pong!")
                    sys.stdout.flush()
                    time.sleep(0.5)
            run += 1
            sys.stdout.write("Database: {}/{}: Run program {}. \n".format(str(run), str(total), name))
            sys.stdout.flush()
        sys.stdout.write(
            "Done coordinating database. Will run again at {}".format(generateNextRunTimestampString(waitTime)))
        sys.stdout.flush()
        time.sleep(0.5)
        sys.stdout.write("Database: Status:Waiting until {}".format(generateNextRunTimestampString(waitTime)))
        sys.stdout.flush()

        for i in range(waitTime*60):
            l = sys.stdin.readline()
            if l == "Database: Cycle\n":
                sys.stdout.flush()
                sys.stdout.write("Database: Status:Cycling")
                sys.stdout.flush()
                break
            time.sleep(1)


except Exception as e:
    sys.stderr.write("DATABASE ERROR: " + repr(e))
    raise e
