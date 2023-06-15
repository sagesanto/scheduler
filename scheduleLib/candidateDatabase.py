import os, uuid, pytz
import sqlite3, logging
import sys
import time
from string import Template

from photometrics.sql_database import SQLDatabase
from datetime import datetime, timedelta

from scheduleLib import generalUtils

validFields = ["ID", "Author", "DateAdded", "DateLastEdited", "RemovedDt", "RemovedReason", "RejectedReason", 'Night',
               'Updated', 'StartObservability', 'EndObservability', 'RA', 'Dec', 'dRA', 'dDec', 'Magnitude', 'RMSE_RA',
               'RMSE_Dec', "Score", "nObs", 'ApproachColor', 'Scheduled', 'Observed', 'Processed', 'Submitted', 'Notes',
               'CVal1', 'CVal2', 'CVal3', 'CVal4', 'CVal5', 'CVal6', 'CVal7', 'CVal8', 'CVal9', 'CVal10']


def generateID(candidateName, candidateType, author):
    hashed = str(hash(candidateName + candidateType + author))
    return int(hashed)


def logAndPrint(msg, loggerMethod):
    loggerMethod(msg)  # logger method is a function like logger.info logger.error etc
    print(msg)


# noinspection PyUnresolvedReferences
class Candidate:
    def __init__(self, CandidateName: str, CandidateType: str, **kwargs):
        self.CandidateName = CandidateName
        self.CandidateType = CandidateType
        for key, value in kwargs.items():
            if key in validFields:
                self.__dict__[key] = str(value)
            else:
                raise ValueError(
                    "Bad argument: " + key + " is not a valid argument for candidate construction. Valid arguments are " + str(
                        validFields))

    def __str__(self):
        return str(dict(self.__dict__))

    def __repr__(self):
        return "Candidate " + self.asDict()[
            "CandidateName"] + " (" + self.CandidateType + ")"  # can't print self.CandidateName directly for whatever reason

    def asDict(self):
        return self.__dict__.copy()

    @classmethod
    def fromDatabaseEntry(cls, entry: dict):
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

        return cls(CandidateName, CandidateType, **entry)  # splat

    def hasField(self, field):
        return field in self.__dict__.keys()

    def isAfterStart(self, dt: datetime):
        """
        Is the provided time after the start time of this Candidate's observability window?
        :return: bool
        """
        dt = CandidateDatabase.stringToTime(dt)  # ensure that we have a datetime object
        if self.hasField("startObservability"):
            if dt > CandidateDatabase.stringToTime(self.startObservability):
                return True
        return False

    def isAfterEnd(self, dt: datetime):
        """
        Is the provided time after the end time of this Candidate's observability window?
        :return: bool
        """
        if self.hasField("endObservability"):
            if dt > CandidateDatabase.stringToTime(self.endObservability):
                return True
        return False

    def isObservableBetween(self, start, end, duration):
        """
        Is this Candidate observable between `start` and `end` for at least `duration` hours?
        :param start: datetime or valid string
        :param end: datetime or valid string
        :param duration: hours, float
        :return: bool
        """
        start, end = CandidateDatabase.stringToTime(start).replace(tzinfo=pytz.UTC), CandidateDatabase.stringToTime(
            end).replace(tzinfo=pytz.UTC)  # ensure we have datetime object


        print("start window:",start,"end window:",end)
        if self.hasField("StartObservability") and self.hasField("EndObservability"):
            startObs, endObs = CandidateDatabase.stringToTime(self.StartObservability).replace(tzinfo=pytz.UTC), CandidateDatabase.stringToTime(
                self.EndObservability).replace(tzinfo=pytz.UTC)
            print("start observability:", startObs, "end observability:", endObs)

            if start < endObs <= end or start < startObs <= end:  # the windows do overlap
                print("Within window")
                print(end-startObs)
                print(endObs-start)
                if min(end - startObs, endObs - start) >= timedelta(hours=duration):  # the window is longer than duration
                    return True
        return False


def _queryToDict(queryResults):
    dictionary = [dict(row) for row in queryResults if row]
    return [{k: v for k, v in a.items() if v is not None} for a in dictionary if a]


class CandidateDatabase(SQLDatabase):
    def __init__(self, dbPath, author):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.__author = author
        self.open(dbPath)
        if self.isConnected:
            self.logger.info("Connection confirmed")
        else:
            raise sqlite3.DatabaseError("Connection to candidate database failed")
        self.__existingIDs = []  # get and store a list of existing IDs. risk of collision low, so I'm not too worried about not calling this before making ids

    def __del__(self):
        try:
            self._releaseDatabase()  # commit anything that might be left if we crash
        except:
            pass
        self.close()

    @staticmethod
    def timeToString(dt, logger=None):
        try:
            if isinstance(dt,
                          str):  # if we get a string, check that it's valid by casting it to dt. If it isn't, we'll return None
                dt = CandidateDatabase.stringToTime(dt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            if logger:
                logger.error("Unable to coerce time from", dt)
            return None

    @staticmethod
    def stringToTime(timeString, logger=None):
        if isinstance(timeString, datetime):  # they gave us a datetime, return it back to them
            return timeString
        try:
            return datetime.strptime(timeString, "%Y-%m-%d %H:%M:%S")
        except:
            if logger:
                logger.error("Unable to coerce time from", timeString)
            return None

    @staticmethod
    def timestamp():
        # UTC time in YYYY-MM-DD HH:MM:SS format
        return CandidateDatabase.timeToString(datetime.utcnow())

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
            self.db_connection = sqlite3.connect(database=db_file, timeout=timeout, check_same_thread=check_same_thread,
                                                 detect_types=sqlite3.PARSE_DECLTYPES |
                                                              sqlite3.PARSE_COLNAMES)
            self.db_connection.row_factory = sqlite3.Row
        except sqlite3.DatabaseError as err:
            self.logger.error('Unable to open sqlite database %s' % db_file)
            self.logger.error('sqlite error : %s' % err)
            raise err
        else:
            self._db_name = os.path.splitext(db_file)[0]
            self.db_cursor = self.db_connection.cursor()
            self.db_cursor.execute('pragma busy_timeout=2000')  # try write commands with a 2-second busy timeout
            self._connected = True
            self.logger.info("Connected to candidate database")
        return

    def table_query(self, table_name, columns, condition, values, returnAsCandidates=False):
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
        returnAsCandidates: bool
            Results
        Return
        ------
        rows : dict
            Python list of dicts, indexed by column name, or list of Candidate objects
        """
        result = _queryToDict(super().table_query(table_name, columns, condition, values))
        if result:
            self.logger.info("Query: Retrieved " + str(len(result)) + " record(s) for candidates in response to query")
            if returnAsCandidates:
                result = [Candidate.fromDatabaseEntry(row) for row in result]
            return result
        self.logger.warning("Couldn't fetch response to query " + condition)
        return None

    def insertCandidate(self, candidate: Candidate):
        candidate = candidate.asDict()
        candidate["Author"] = self.__author
        candidate["DateAdded"] = CandidateDatabase.timestamp()
        id = generateID(candidate["CandidateName"], candidate["CandidateType"], self.__author)
        candidate["ID"] = id
        try:
            self.insert_records("Candidates", candidate)
        except:
            self.logger.error("Can't insert " + str(candidate) + ". PBCAK Error")
            return None
        self.logger.info(
            "Inserted " + candidate["CandidateType"] + " candidate \'" + candidate["CandidateName"] + "\' from " +
            candidate["Author"])
        return id

    def fetchIDs(self):
        self.__existingIDs = [row["ID"] for row in self.table_query("Candidates", "ID", '', []) if row]

    def isFieldProtected(self, field):
        return field in ["Author", "DateAdded", "ID"]

    def removeInvalidFields(self, dictionary):
        badKeys = []
        for key, value in dictionary.items():
            if key not in validFields or self.isFieldProtected(key):
                # self.logger.warning("Warning: Invalid field: can't edit field or add field \'"+key+"\'")
                badKeys.append(key)
        for key in badKeys:
            dictionary.pop(key)
        return dictionary

    def candidatesAddedSince(self, when):
        """
        Query the database for candidates added since 'when'
        :param when: datetime or string, PST
        :return: A list of Candidates, each constructed from a row in the dataframe, or None
        """
        when = self.timeToString(when)
        if when is None:
            return None
        queryResult = self.table_query("Candidates", "*", "DateAdded > ?", [when], returnAsCandidates=True)
        if queryResult:
            return queryResult
        else:
            self.logger.warning("Received empty query result for candidates added since " + when)
            return None

    def getCandidateByID(self, ID):
        return self.table_query("Candidates", "*", "ID = ?", [ID], returnAsCandidates=True)

    def editCandidateByID(self, ID, updateDict):
        updateDict = self.removeInvalidFields(updateDict)
        if len(updateDict):
            updateDict["DateLastEdited"] = CandidateDatabase.timestamp()

            self.table_update("Candidates", updateDict, "ID = " + str(ID))

    def _releaseDatabase(self):
        self.db_cursor.execute("COMMIT", [])

    def setFieldNullByID(self, ID, colName):
        value = None
        sql_template = Template('UPDATE Candidates SET $column_name = ? WHERE \"ID\" = $id')
        sql_statement = sql_template.substitute({'column_name': colName, 'id': str(ID)})
        self.db_cursor.execute(sql_statement, [value])

    def removeCandidateByID(self, ID: str, reason: str):
        candidate = self.getCandidateByID(ID)[0]
        if candidate:
            reason = self.__author + ": " + reason
            updateDict = {"RemovedDt": CandidateDatabase.timestamp(), "RemovedReason": reason,
                          "DateLastEdited": CandidateDatabase.timestamp()}
            self.table_update("Candidates", updateDict, "ID = " + str(ID))
            self.logger.info("Removed candidate " + candidate.CandidateName + " for reason " + reason)
        else:
            self.logger.error("Couldn't find target with ID " + ID + ". Can't update.")
            return None
        return ID


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', filename='libFiles/candidateDb.log',
                        encoding='utf-8', datefmt='%m/%d/%Y %H:%M:%S', level=logging.DEBUG)
    db = CandidateDatabase("../candidate database.db", "Sage")

    db.logger.addFilter(generalUtils.filter)

    candidate = Candidate("Test", "Test", Notes="test")
    ID = db.insertCandidate(candidate)
    db.removeCandidateByID(ID, "Because I want to !")
