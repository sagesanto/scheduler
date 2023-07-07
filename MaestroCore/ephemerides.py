import json
import os
import subprocess
import sys

ephemPrograms = {}
# print(sys.argv)

try:
    # i = 0
    # for root, directory, file in os.walk("./schedulerConfigs"):
    #     ephemPrograms[directory[i]] = [".".join([root.replace("./", "").replace("\\", "."), f]) for f in file if
    #                                  f.endswith(".py") and "ephemerides_" in f]
    #     i+=1
    root_directory = "./schedulerConfigs"  # Replace with the actual root directory path
    ephemPrograms = {}

    for root, dirs, files in os.walk(root_directory):
        subdirectory = root.replace(root_directory, "").strip(os.sep)
        desired_files = [os.sep.join([root, f]) for f in files if
                                      f.endswith(".py") and "ephemeris_" in f]
        ephemPrograms[subdirectory.replace("_", " ")] = desired_files
    # sys.stdout.write("ephemPrograms:" + str(ephemPrograms))
    # sys.stdout.flush()

    targetsDict = json.loads(sys.argv[1])
    settingsJstr = sys.argv[2]

    total = sum(len(value) for value in targetsDict.values())
    fetched = 0
    tasks = []
    for key in targetsDict.keys():
        if key in ephemPrograms.keys():
            desigs = targetsDict[key]
            # sys.stdout.write("Cmd: "+str(['python', ephemPrograms[key][0], json.dumps(desigs), settingsJstr,
            #                  ephemsSaveDir]))
            # sys.stdout.flush()
            subprocess.call(['python', ephemPrograms[key][0], json.dumps(desigs), settingsJstr])  # should probably switch to asyncio subprocesses at some point but whatever
            fetched += len(desigs)
            sys.stdout.write(" ".join(["Ephemeris: completed", str(fetched), "out of", str(total),"\n"]))
            sys.stdout.flush()
        else:
            sys.stdout.write("No configured ephemerides file for "+key)

    sys.stdout.flush()
    sys.stdout.write("Done fetching ephems.")
    sys.stdout.flush()


except Exception as e:
    sys.stderr.write("ERROR: "+repr(e))
    raise e
