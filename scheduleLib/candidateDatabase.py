import os, uuid
import sqlite3, logging
import sys
import time

from photometrics.sql_database import SQLDatabase
from datetime import datetime

validFields = ["ID","Author","DateAdded","DateLastEdited", "RemovedDt", "RemovedReason", "RejectedReason",'Night', 'Updated', 'StartObservability', 'EndObservability', 'RA', 'Dec', 'dRA', 'dDec', 'Magnitude', 'RMSE_RA', 'RMSE_Dec', "Score", "nObs", 'ApproachColor', 'Scheduled', 'Observed', 'Processed', 'Submitted', 'Notes', 'CVal1', 'CVal2', 'CVal3', 'CVal4', 'CVal5', 'CVal6', 'CVal7', 'CVal8', 'CVal9', 'CVal10']

def filter(record):
    info = sys.exc_info()
    if info[1]:
        logging.exception('Exception!',exc_info=info)
        print("---Exception!---",info)

    return True

def generateID(candidateName,candidateType,author):
    hashed = str(hash(candidateName+candidateType+author))
    return int(hashed)

def logAndPrint(msg,loggerMethod):
    loggerMethod(msg)  #logger method is a function like logger.info logger.error etc
    print(msg)

class Candidate:
    def __init__(self, CandidateName, CandidateType, **kwargs):
        self.CandidateName = CandidateName
        self.CandidateType = CandidateType
        for key, value in kwargs.items():
            if key in validFields:
                self.__dict__[key] = str(value)
            else:
                raise ValueError("Bad argument: "+key+" is not a valid argument for candidate construction. Valid arguments are "+ str(validFields))

    def __str__(self):
        return str(dict(self.__dict__))
    def __repr__(self):
        return "Candidate "+self.CandidateName +" ("+self.CandidateType+")"
    def asDict(self):
        return self.__dict__

    @classmethod
    def fromDatabaseEntry(cls,entry:dict):
        """
        Convert a returned database entry to a Candidate object
        :param entry: a dictionary returned (inside a list) from a database query
        :return: Candidate object
        """
        CandidateName, CandidateType = entry.pop("CandidateName"), entry.pop("CandidateType")
        d = {}
        for key, value in entry.items():
            if key in validFields:
                d[key] = value

        return cls(CandidateName,CandidateType, **entry)  #splat


def _queryToDict(queryResults):
    dictionary = [dict(row) for row in queryResults if row]
    return [{k: v for k, v in a.items() if v is not None} for a in dictionary if a]


class CandidateDatabase(SQLDatabase):
    def __init__(self,dbPath,author):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.__author = author

        self.open(dbPath)
        if self.isConnected:
            self.logger.info("Connection confirmed")
        else:
            raise sqlite3.DatabaseError("Connection to candidate database failed")
        self.__existingIDs = []  #get and store a list of existing IDs. risk of collision low, so I'm not too worried about not calling this before making ids

    def __del__(self):
        self.close()
    def timeToString(self,dt):
        try:
            if isinstance(dt,str):  # if we get a string, check that it's valid by casting it to dt and back. If it isn't, we'll return None
                dt = self.stringToTime(dt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            self.logger.error("Unable to coerce time from", dt)
            return None


    def stringToTime(self,timeString):
        if isinstance(timeString, datetime):
            return timeString
        try:
            return datetime.strptime(timeString, "%Y-%m-%d %H:%M:%S")
        except:
            self.logger.error("Unable to coerce time from", timeString)
            return None


    def timestamp(self):
        # Local time in YYYY-MM-DD HH:MM:SS.SSS. This may be dangerous if run from computers not in PST. What about daylight savings?
        return self.timeToString(datetime.now())


    def open(self, db_file, timeout=5, check_same_thread=False):
        """
        Establish connection to the candidate database
        :param db_file: Path to the candidate database SHOULD MAKE THIS INTERNAL
        :param check_same_thread: Check if the database should be read by only one thread
        """

        if not os.path.isfile(db_file):
            self.logger.error('Database file %s not found.' % db_file)
            raise ValueError("Database file not found")

        try:
            self.db_connection = sqlite3.connect(database=db_file, timeout=timeout, check_same_thread=check_same_thread, detect_types=sqlite3.PARSE_DECLTYPES |
                             sqlite3.PARSE_COLNAMES)
            self.db_connection.row_factory = sqlite3.Row
        except sqlite3.DatabaseError as err:
            self.logger.error('Unable to open sqlite database %s' % db_file)
            self.logger.error('sqlite error : %s' % err)
            raise err
        else:
            self._db_name = os.path.splitext(db_file)[0]
            self.db_cursor = self.db_connection.cursor()
            self._connected = True
            self.logger.info("Connected to candidate database")

        return


    def table_query(self, table_name, columns, condition, values,returnAsCandidate=False):
        """Query table based on condition. If no condition given, will return the whole table - if this isn't what you want, be careful!

        Parameters
        ----------
        table_name : str
            Database table name

        columns : str
            table columns to query

        condition : str
            sql conditional statement

        values : list or tuple
            List of values corresponding to conditional statement

        Return
        ------
        rows : dict
            Python list of lists containing column elements
        """
        result = _queryToDict(super().table_query(table_name,columns,condition,values))
        if result:
            self.logger.info("Query: Retrieved " + str(len(result)) + " record(s) for candidates in response to query")
            if returnAsCandidate:
                result = [Candidate.fromDatabaseEntry(row) for row in result]
            return result
        self.logger.warning("Couldn't fetch response to query "+condition)
        return None


    def insertCandidate(self,candidate:Candidate):
        candidate = candidate.asDict()
        candidate["Author"] = self.__author
        candidate["DateAdded"] = self.timestamp()
        id = generateID(candidate["CandidateName"],candidate["CandidateType"],self.__author)
        candidate["ID"] = id
        try:
            self.insert_records("Candidates", candidate)
        except:
            self.logger.error("Can't insert "+str(candidate)+". PBCAK Error")
            return None
        self.logger.info("Inserted " + candidate["CandidateType"] + " candidate \'"+candidate["CandidateName"] + "\' from "+candidate["Author"])
        return id

    def fetchIDs(self):
        self.__existingIDs = [row["ID"] for row in self.table_query("Candidates", "ID", '', []) if row]

    def isFieldProtected(self,field):
        return field in ["Author","DateAdded", "ID"]

    def removeInvalidFields(self,dictionary):
        badKeys = []
        for key, value in dictionary.items():
            if key not in validFields or self.isFieldProtected(key):
                logAndPrint("Warning: Invalid field: can't edit field or add field \'"+key+"\'",self.logger.warning)
                badKeys.append(key)
        for key in badKeys:
            dictionary.pop(key)
        return dictionary

    def candidatesAddedSince(self,when):
        """
        Query the database for candidates added since 'when'
        :param when: datetime or string, PST
        :return: A list of Candidates, each constructed from a row in the dataframe, or None
        """
        when = self.timeToString(when)
        if when is None:
            return None
        queryResult = self.table_query("Candidates","*","DateAdded > ?",[when],returnAsCandidate=True)
        if queryResult:
            return queryResult
        else:
            logAndPrint("Received empty query result for candidates added since "+when,self.logger.warning)
            return None

    def getCandidateByID(self,ID):
        return self.table_query("Candidates","*","ID = ?",[ID],returnAsCandidate=True)
    def editCandidateByID(self,ID,updateDict):
        updateDict = self.removeInvalidFields(updateDict)
        if len(updateDict):
            updateDict["DateLastEdited"] = self.timestamp()

            self.table_update("Candidates",updateDict,"ID = "+str(ID))

    def removeCandidateByID(self,ID:str,reason:str):
        candidate = self.getCandidateByID(ID)[0]
        if candidate:
            reason = self.__author+": "+reason
            updateDict = {"RemovedDt": self.timestamp(), "RemovedReason": reason, "DateLastEdited": self.timestamp()}
            self.table_update("Candidates", updateDict, "ID = " + str(ID))
            logAndPrint("Removed candidate "+candidate.CandidateName + " for reason "+reason, self.logger.info)
        else:
            logAndPrint("Couldn't find target with ID " + ID +". Can't update.",self.logger.error)
            return None
        return ID




if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',filename='candidateDb.log', encoding='utf-8', datefmt='%m/%d/%Y %H:%M:%S', level=logging.DEBUG)
    db = CandidateDatabase("../candidate database.db","Sage")

    db.logger.addFilter(filter)

    print(generateID("C440NCZ","MPC","MPClogger"))

    candidate = Candidate("Test","Test",Notes="test")
    ID = db.insertCandidate(candidate)
    db.removeCandidateByID(ID,"Because I want to !")
    #
    # db.fetchIDs()
    #
    # print(db.candidatesAddedSince("2023-05-09 12:17:28"))
    # db.editCandidateByID("203609125038556",{"CVal1":"Edit test"})

