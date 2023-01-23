from sCore import *

class Error:
    def __init__(self,eType,lineNum,message,out=None): #out is a print or other output function
        self.eType, self.lineNum, self.message = eType,lineNum,message
    def out(self):
        if self.out == self.out:
            return self.out(self)
        message = self.type+" encountered on line(s) " + str(self.lineNum)

class Test:
    def __init__(self,name,function,errors=[]): #function returns a status code (0=success, 1=fail, -1=unknown) and a list of errors
        self.name, self.function, self.errors = name,function,errors
    def run(self,schedule): #takes schedule object
        status,errors = self.function(schedule)
        return self.name,status,errors

def checkSchedule(schedule):
    tests = []
    errors = []
    for test in tests:
        errors.append()