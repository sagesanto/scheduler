import sys, os, flet as ft
from scheduleLib import sCoreCondensed as sc
from flet import (Column, ElevatedButton, FilePicker, FilePickerResultEvent, FilePickerUploadEvent, FilePickerUploadFile, Page, ProgressRing, Ref, Row, Text, icons)

def expandPath(workingDir, returner):
    if not os.path.isdir(workingDir):  # we're a file. append ourselves and return!
        returner.append(workingDir)
        return returner
    else:  # call our nodes
        for item in os.listdir(workingDir):
            returner = expandPath(workingDir + "/" + item, returner)
        return returner

schedule = sc.readSchedule("files/exampleSchedule.txt")
print(schedule.summarize())

#will take the following things as input: [1] path to a folder with lists of ephemerides for each object (filename should be [object name].txt),
#[2] preferred min time between observations, [3] preferred minimum time between observations of the same object, [4] start time in the format DD-MM-YYYY HH:MM:SS
if len(sys.argv)<5:
    raise Exception("Not enough arguments provided. Please provide the path to a folder with lists of ephemerides for each object (filename should be [object name].txt), preferred min time between observations (minutes), preferred minimum time between observations of the same object (minutes), and start time in the format DD-MM-YYYY HH:MM:SS")
# ephemsDir, minTimeBetween, minTimeBetweenSame, startTime = sys.argv[1:5]
startTime = datetime.strptime(startTime, "%d-%m-%Y %H:%M:%S")


loc = LocationInfo(name='TMO', region='CA, USA', timezone='UTC',
                   latitude=34.36, longitude=-117.63)
s = sun(loc.observer, date=datetime.now(timezone.utc), tzinfo=timezone.utc)
sunrise = s["sunrise"]

offsets = sc.obsTimeOffsets

class observationPackage:
    def __init__(self,obs):
        self.obs = obs
        self.objName = obs.targetName
        self.startRange = self.findStartTimeRange(self.obs)
    def findStartTimeRange(self): #given an observation, based on its length, center it and find the range of acceptable start times
        centered, offset, maxOffset, midPoint = sc.checkObservationOffset(self.obs)
        range = []
        for minute in maxOffset.minutes/60:
            range.append(midPoint - minute)
            range.append(midPoint + minute)
        return range.sort()

def loadPotentialObs(ephemsDir, startTime):
    potentialObs = {} #potential obs is a dictionary that has maps object names to a dictionary of {start times : observation packages}
    for file in os.listdir(ephemsDir):
        objObs = {} #dictionary of {start times : observation packages}
        with open(os.path.join(ephemsDir, file)) as f:
            for line in f:
                if line[0] == "\n":
                    continue
                else:
                    obs = sc.Observation.fromLine(line)
                    obsPack = observationPackage(obs)
                    if obs.range[-1] > startTime:
                        objObs[obs.range[0]] = obsPack
        potentialObs[obs.targetName] = objObs
    return potentialObs

def objNextObs(ObjPotentialObs,startTime):
    for time in ObjPotentialObs[startTime].startRange: #we're checking if the observation indicated by the provided start time can start at one of the times in its range start at any time in the range
        if time > startTime:
            pkg = ObjPotentialObs[startTime]
            pkg.obs.startTime = time
            pkg.obs.endTime = pkg.obs.startTime+pkg.obs.duration
            return pkg
    return None

class scheduleBuilder:
    def __init__(self):
        self.currentTime = startTime #this time will be updated as the schedule is built
        self.schedule = sc.Schedule()
    def placeObservation(self, obsPack,obsStartTime):
        obs = obsPack.obs
        obs.startTime, obs.endTime = obsStartTime, obsStartTime + relativedelta(seconds = float(obs.duration))
        schedule.appendTask(obs)
        self.currentTime = obs.endTime + relativedelta(minutes = float(minTimeBetween))
    def deleteObservation(self,obs): #deletes the given observation and all observations after it - probably better to use some graph structure here but whatever
        index = self.schedule.tasks.index(obs)
        while self.schedule.tasks[index]:
            self.schedule.deleteTask(index)
        self.currentTime = self.observations[index-1][0]
    def nextObservationCandidates(self, potentialObs, startTime): #my head hurts
        nextObs = {} #dictionary of {object : next observation package for that object}
        for obj in potentialObs.keys():
            target = self.schedule.targets[obj]
            lastStart = target.observations[-1].startTime
            for start in potentialObs[obj].keys():
                candidate = objNextObs(potentialObs[obj], max(start,lastStart+relativedelta(minutes = minTimeBetweenSame)))
                if candidate:
                    nextObs[obj] = candidate
                    break
        return nextObs
    def buildScheduleLoop(self, potentialObs):
        while True:
            nextObs = self.nextObservationCandidates(potentialObs, self.currentTime)
            if nextObs == {}:
                break
            else:
                nextToPlace = self.presentOptions(nextObs)
                self.placeObservation(nextToPlace, nextToPlace.obs.startTime)
    def presentOptions(self, nextObs): #this is where the GUI stuff will go
        for obj in nextObs.keys():
            print("Possible observation of "+obj+" at "+nextObs[obj].obs.startTime)
        print("Please enter the name of the object you would like to observe next.")
        choice = input()
        return nextObs[choice]

###### GUI ########
#using flet ("ft"), python port of flutter
#colors
blue = ft.colors.BLUE_400
red = ft.colors.RED_400
green = ft.colors.GREEN_400
orange = ft.colors.ORANGE_800
yellow = ft.colors.YELLOW_400

# styles
titleStyle = lambda c: ft.TextStyle(color=c, fontSize=30, fontWeight=ft.FontWeight. BOLD)
headerStyle = lambda c: ft.TextStyle(color=c, fontSize=20, fontWeight=ft.FontWeight. BOLD)
bodyStyle = lambda c: ft.TextStyle(color=c, fontSize=15, fontWeight=ft.FontWeight.normal)
buttonStyle = lambda c: ft.ButtonStyle(color=c, fontSize=15, fontWeight=ft.FontWeight.BOLD)

def main(sch,page: Page):

    # variables ####

    nextObs = []
    candidateObsObjects={}
    placedObsObjects={}

    ephemsDir = ""
    potentialObs = ""
    selectedFiles = ft.Text(value="No files selected", style=headerStyle(blue))

    # functions ###

    def onDirectoryChosen(e: ft.FilePickerResultEvent):
        selectedFiles.value = (
            ", ".join(expandPath(e.files[0].path,[])) if e.files else "Cancelled!"
        )
        # fileList.join(expandPath(e.files[0].path,[]))
        selectedFiles.update()
        ephemsDir = e.files[0].path
    # def onFilesChosen(e: ft.FilePickerResultEvent):
    #     #append all the paths to fileList
    #     selectedFiles.value = selectedFiles.value.join([i.path for i in e.files] if e.files else "Cancelled!")
    #     fileList.join([i.path for i in e.files])
    #     selectedFiles.update()

    def loadEphems():
        filePicker = ft.get_directory_path(on_result=onDirectoryChosen)
        potentialObs = loadPotentialObs(ephemsDir, startTime)
        page.update()
    # def addEphems():
    #     filePicker = ft.get_directory_path(on_result=onFilesChosen)
    #     potentialObs loadPotentialObs(ephemsDir, startTime)
    #     page.update()

    def placeObs(obsPack):
        obj = placedObservation(obsPack)
        scheduleList.controls.append(obj)
        sch.scheduleBuilder.placeObservation(obsPack, obsPack.obs.startTime)
        nextObs = sch.nextObservationCandidates(potentialObs, sch.currentTime)
        page.update()


        # title box is a horizontal container with the title text and four buttons: Import Folder, Help, Credits, Settings
    titleBox = ft.Row(
        [
            ft.Text(value="The Scheduler", style=titleStyle(blue)),
            ft.Button(value="Import Folder", style=buttonStyle(blue), on_click=loadEphems),
            ft.Button(value="Help", style=buttonStyle(blue)),
            ft.Button(value="Credits", style=buttonStyle(blue)),
            ft.Button(value="Settings", style=buttonStyle(blue)),
        ],
        mainAxisAlignment=ft.MainAxisAlignment.spaceBetween,
        crossAxisAlignment=ft.CrossAxisAlignment.left,
    )
    page.add(titleBox)

    # a placedObservation is a container with the object name, start time, duration, and a button to remove it from the schedule. this is a function to create one from an obsPack object
    def placedObservation(obsPack):
        return ft.Container(
            [
                ft.Text(value=obsPack.obs.target.name, style=bodyStyle(blue)),
                ft.Text(value=obsPack.obs.startTime, style=bodyStyle(blue)),
                ft.Text(value=obsPack.obs.duration, style=bodyStyle(blue)),
                ft.Button(value="Delete", style=buttonStyle(red)),
            ],
            data = obsPack,
            mainAxisAlignment=ft.MainAxisAlignment.spaceBetween,
            crossAxisAlignment=ft.CrossAxisAlignment.left,
        )

    def observationCandidate(obsPack):
        return ft.Container(
            [
                ft.Text(value=obsPack.obs.target.name, style=bodyStyle(blue)),
                ft.Text(value=obsPack.obs.startTime, style=bodyStyle(blue)),
                ft.Text(value=obsPack.obs.duration, style=bodyStyle(blue)),
                ft.Button(value="Place", style=buttonStyle(green), on_click=placeObs(obsPack)),
            ],
            data = obsPack,
            mainAxisAlignment=ft.MainAxisAlignment.spaceBetween,
            crossAxisAlignment=ft.CrossAxisAlignment.left,
        )


    #schedule box is a vertical container with the schedule title, a container holding each entry of the schedule, and a control box at the bottom containing buttons "Export" "Analyze" "Undo", and a trash icon button
    scheduleList = ft.ListView(expand=True, data = [], spacing=10)

    scheduleBox = ft.Column(
        [
            ft.Text(value="Schedule:", style=headerStyle(blue)),
            scheduleList,
            ft.Row(
                [
                    ft.Button(value="Export", style=buttonStyle(green)),
                    ft.Button(value="Analyze", style=buttonStyle(blue)),
                    ft.Button(value="Undo", style=buttonStyle(yellow)),
                    ft.Button(value="Delete", style=buttonStyle(red)),
                ],
                mainAxisAlignment=ft.MainAxisAlignment.spaceBetween,
                crossAxisAlignment=ft.CrossAxisAlignment.center,
            ),
        ],
        mainAxisAlignment=ft.MainAxisAlignment.start,
        crossAxisAlignment=ft.CrossAxisAlignment.start
    )


    #to the right of scheduleBox is a box called "Choose Next" that displays a horizontal list of possible observations, with a button to place each one
    chooseNextList = ft.ListView(expand=True, data = [], spacing=10)
    chooseNextBox = ft.Column(
        [
            ft.Text(value="Choose Next", style=headerStyle(blue)),
            chooseNextList
        ]
    )

    #the loadedFiles box is a vertical container to the right of schedule box with the title "Loaded Files" and a list of the files loaded into the program, half as tall as the other boxes
    loadedFiles = ft.ListView(expand=True, data = [], spacing=10)
    loadedFilesBox = ft.Column(
        [
            ft.Text(value="Loaded Files", style=headerStyle(blue)),
            loadedFiles
        ]
    )

    # the loaded objects box is below the loaded files box, with the title "Loaded Objects" and a list of the objects loaded from the files
    loadedObjects = ft.ListView(expand=True, data = [], spacing=10)
    loadedObjectsBox = ft.Column(
        [
            ft.Text(value="Loaded Objects", style=headerStyle(blue)),
            loadedObjects
        ]
    )

    loadedBox = ft.Column([loadedFilesBox, loadedObjectsBox])

    # the windowsBox is a horizontal grid with the next observation window on the left and the candidate observation window on the right, then to the right is the loaded objects box at the top and the loaded files box at the bottom
    windowsBox = ft.Row(scheduleBox, chooseNextBox, loadedBox, spacing=10)
    page.add(windowsBox)



    
    page.controls.append(ft.Text(value="Possible Observations:", style=titleStyle))
    for obj in nextObs.keys():
        page.controls.append(ft.Text(value="Possible observation of " + obj + " at " + nextObs[obj].obs.startTime, style=bodyStyle))
        page.controls.append(ft.ElevatedButton(text="Place observation", on_click=buttonClicked))

    t = ft.Text(value="Hello, world!", color="green")
    page.controls.append(t)
    page.add(ft.ElevatedButton(text="Click me", on_click=lambda a:page.add(ft.Text("Clicked!"))))     #page.add is a shortcut for page.controls.append and page.update in one line
    page.update()



ft.app(target=main)
#running from command line like as follows allows hot reloading
os.system('flet run firstFlet.py -d')

