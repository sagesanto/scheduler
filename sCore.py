import os, sys, fileinput
from datetime import datetime
from dateutil.relativedelta import relativedelta

class Observation:
    # hell on earth, preferred method is fromLine
    def __init__(self,startTime,targetName,RA,Dec,exposureTime,numExposures,duration,filter,dRA,dDec,description): #etc
        self.startTime, self.targetName, self.RA, self.Dec, self.exposureTime, self.numExposures, self.duration, self.filter, self.dRA, self.dDec,self.description = startTime,targetName,RA,Dec,exposureTime,numExposures,duration,filter,dRA, dDec,description
        self.endTime = self.startTime+relativedelta(seconds = float(self.duration))
    @classmethod
    def fromLine(cls, line): #this is bad but whatever
        try:
            rawText = line
            split = line.split('|')
            startTime = stringToTime(split[0])
            occupied = split[1] #probably always 1
            targetName = split[2][:-2] # the minus two gets rid of the '_1','_2' etc at end of names.
            move = split[3] #probably always 1
            RA = split[4]
            Dec = split[5]
            exposureTime = split[6]
            numExposures = split[7]
            duration = float(exposureTime)*float(numExposures) #seconds
            filter = split[8]
            description = split[9]
            descSplit = description.split(" ")
            dRA,dDec = descSplit[10],descSplit[12][:-1]
            return cls(startTime,targetName,RA,Dec,exposureTime,numExposures,duration,filter,dRA,dDec,description)
        except Exception as e:
            raise Exception("Failed to create observation from line \""+line+"\"")

    #generate a Scheduler.txt line
    def genLine(self,num):
        line = timeToString(self.startTime)
        attr = ["1",self.targetName+"_"+str(num),"1",self.RA,self.Dec,self.exposureTime,self.numExposures,self.filter,self.description]
        for attribute in attr:
            line = line + "|" + attribute
        return line

#this is an NEO or other target
class Target:
    def __init__(self, name):
        self.name = name
        self.observations = []
    def addObservation(self,obs):
        self.observations.append(obs)
        #add observations here, maybe in dictionary form with useful keyword?

class AutoFocus:
    def __init__(self, desiredStartTime):
        self.startTime = stringToTime.strftime(desiredStartTime) if isinstance(desiredStartTime,str) else desiredStartTime
        self.endTime = self.startTime+relativedelta(minutes=5)
    @classmethod
    def fromLine(cls, line):
        time = line.split('|')[0]
        time = stringToTime(time)
        return cls(time)

    # generate a line to put into the scheduler
    def genLine(self):
        return timeToString(self.startTime)+"|1|Focus|0|0|0|0|0|CLEAR|'Refocusing'"


class Schedule:
    def __init__(self, tasks=[],targets={}): #tasks are AutoFocus or Observation objects, targets is dict of target name to target object
        self.tasks = tasks
        self.targets = targets
    def appendTask(self,task):
        if isinstance(task,Observation):
            name = task.targetName
            if name not in self.targets.keys():
                self.targets[name] = Target(name)
            self.targets[name].addObservation(task) #make sure this actually works with scope n stuff

        self.tasks.append(task)
    def appendTasks(self,tasks):
        for task in tasks:
            self.appendTask(task)
    def addAutoFocus(self,desiredTime):
        self.appendTask(AutoFocus(desiredTime))
        #add an autoFocus loop to the schedule
    def toTxt(self):
        lines = "DateTime|Occupied|Target|Move|RA|Dec|ExposureTime|#Exposure|Filter|Description\n\n"
        namesDict = {} #map names of objects to the number of times theyve been observed
        for task in self.tasks:
            if isinstance(task, Observation):
                name = task.targetName
                if name not in namesDict.keys():
                    namesDict[name] = 1
                else:
                    namesDict[name] +=1
                lines += task.genLine(namesDict[name])+"\n"
            else:
                lines += "\n"+task.genLine()+"\n\n"


        print("Enter filename for outputted schedule:",end=" ")
        filename = input()
        with open(filename,"w") as f:
            f.write(lines)
            f.close()
        #add '_1','_2' etc at end of name
        # do the work of converting to usable txt file
        # don't forget to add the template at the top
        # convert time back from time object

    def summarize(self):
        summary = "Schedule with "+str(len(self.targets.keys()))+" targets\n"
        for target in self.targets.values():
            summary = summary + "Target: "+target.name+", "+str(len(target.observations))+" observations:\n"
            for obs in target.observations:
                summary = summary +"\t"+ timeToString(obs.startTime) + ", " + str(obs.duration) +" second duration\n"
        focusTimes = []
        for task in self.tasks:
            if isinstance(task,AutoFocus):
                focusTimes.append(task.startTime)
        summary += "Schedule has " + str(len(focusTimes)) + " AutoFocus loops:\n"
        for time in focusTimes:
            summary = summary +"\t"+ timeToString(time) + "\n"

        return summary

    #probably will want some helper functions

#take time as string from scheduler, return time object
def stringToTime(tstring): #example input: 2022-12-26T05:25:00.000
    return datetime.strptime(tstring,'%Y-%m-%dT%I:%M:%S.000')

def timeToString(time):
    return datetime.strftime(time,'%Y-%m-%dT%I:%M:%S.000')

#takes existing schedule file, returns schedule object
def readSchedule(filename):
    lines = []
    tasks = []
    with open(filename,'r') as f:
        lines = f.readlines()
    cleanedLines = [l.replace("\n",'') for l in lines if l !="\n"]

    for line in cleanedLines:
        if 'DateTime' in line: #ignore the template at the top
            continue
        if 'Refocusing' in line:
           tasks.append(AutoFocus.fromLine(line))
        else: #assume it's an observation
            tasks.append(Observation.fromLine(line))
    schedule = Schedule()
    schedule.appendTasks(tasks)
    return schedule

