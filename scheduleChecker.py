from sCore import *

class Error:
    def __init__(self,eType,lineNum,message,out=None): #out is a print or other output function
        self.eType, self.lineNum, self.message, self.output = eType,lineNum,message,out
    def out(self):
        if self.output is not None:
            return self.output()
        return self.eType+" encountered on line(s) " + str(self.lineNum) + " with message \"" + self.message + "\""

class Test:
    def __init__(self,name,function): #function returns a status code (0=success, 1=fail, -1=unknown) and an error if necessary
        self.name, self.function = name,function
    def run(self,schedule): #takes schedule object
        status,error = self.function(schedule)
        return self.name,status,error

def checkSchedule(schedule,tests):
    status = []
    for test in tests:
        status.append(test.run(schedule))
    for state in status:
        if state[1] != 0:
            print('\033[1;31m '+state[0]+' \033[0;0m',state[2].out())
        else:
            print('\033[1;32m '+state[0]+' \033[0;0m',"No Error!")
