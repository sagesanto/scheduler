import json
import sys, os, keyring
from abc import abstractmethod

import pandas as pd
import pytz
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QMainWindow, QFileDialog, QButtonGroup, QTableWidget, \
    QTableWidgetItem as QTableItem, QListWidget, QLineEdit, QListView
from PyQt6.QtCore import Qt, pyqtSignal, QRunnable, QObject, QThreadPool, QProcess, QAbstractListModel
from PyQt6 import uic, QtCore
from MaestroCore.Qt.MainWindow import Ui_MainWindow
from MaestroCore.Qt.EphemDialog import Ui_Dialog as EphemPopup
from scheduleLib import genUtils, asyncUtils
from scheduleLib.candidateDatabase import Candidate, CandidateDatabase
from MaestroCore.Qt.processes import ProcessModel, Process
from MaestroCore.Qt.listModel import StringListModel
from datetime import datetime, timedelta


def getSelectedFromList(view: QListView):
    selectedIndexes = view.selectedIndexes()
    return [index.data(Qt.ItemDataRole.DisplayRole) for index in selectedIndexes]


def addLineContentsToList(lineEdit: QLineEdit, lis):
    lis.addItem(lineEdit.text())
    lineEdit.clear()


def getSelectedFromTable(table, colIndex):
    selected = []
    indexes = table.selectionModel().selectedRows(column=1)
    model = table.model()
    for index in indexes:
        selected.append(model.data(model.index(index.row(), colIndex)))
    return selected


def loadDfInTable(dataframe: pd.DataFrame, table: QTableWidget):  # SHARED MUTABLE STATE!!!!! :D
    df = dataframe.copy()  # .reset_index()
    columnHeaders = df.columns
    numRows, numCols = len(df.index), len(columnHeaders)
    table.setRowCount(numRows)
    table.setColumnCount(numCols)
    for i in range(numRows):
        for j in range(numCols):
            item = QTableItem(str(df.iloc[i][j]))
            table.setItem(i, j, item)
    table.resizeColumnsToContents()
    table.resizeRowsToContents()
    table.setHorizontalHeaderLabels(columnHeaders)


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.candidateDict = None
        self.indexOfIDColumn = None
        self.indexOfNameColumn = None
        self.setupUi(self)
        self.sunriseUTC, self.sunsetUTC = genUtils.getSunriseSunset()
        self.sunriseUTC, self.sunsetUTC = genUtils.roundToTenMinutes(self.sunriseUTC), genUtils.roundToTenMinutes(
            self.sunsetUTC)
        self.sunriseUTC -= timedelta(hours=1)
        self.dbConnection = CandidateDatabase("candidate database.db", "Maestro")
        self.candidates = None
        self.candidateDf = None
        self.setConnections()
        self.filterProxyModel = QtCore.QSortFilterProxyModel()
        self.candidatesByID = None
        self.pool = QThreadPool.globalInstance()
        self.maxThreads = self.pool.maxThreadCount()
        print("Max threads:", self.maxThreads)
        # self.p = None
        # self.p = QProcess()
        #
        # self.p.start("python", ['dummyScript.py'])
        # print(self.p.processId())
        self.processModel = ProcessModel()
        self.processesTreeView.setModel(self.processModel)
        self.ephemProcess = None
        self.gettingEphemeris = False
        self.ephemListModel = StringListModel()
        self.ephemListView.setModel(self.ephemListModel)

    def useCandidateTableEphemeris(self):
        for desig, ID in zip(getSelectedFromTable(self.candidateTable, self.indexOfNameColumn),
                             getSelectedFromTable(self.candidateTable, self.indexOfIDColumn)):
            self.ephemListModel.addItem(desig + "   ID " + ID)
        self.tabWidget.setCurrentWidget(self.tabWidget.findChild(QWidget, "ephemsTab"))
        # add the desigs of all selected candidates in the candidate table to the ephem table
        # set the ephem tab as the active tab

    # def initializeStates(self):

    def setConnections(self):
        self.refreshCandButtons.clicked.connect(lambda refresh: self.getTargets().displayCandidates())
        self.showRejectedCheckbox.stateChanged.connect(self.displayCandidates)
        self.showRemovedCheckbox.stateChanged.connect(self.displayCandidates)
        self.candidateEphemerisButton.clicked.connect(self.useCandidateTableEphemeris)
        self.getEphemsButton.clicked.connect(self.getEphemeris)
        self.ephemRemoveSelected.clicked.connect(lambda g: self.ephemListModel.removeSelectedItems(self.ephemListView))
        self.ephemNameEntry.returnPressed.connect(lambda: addLineContentsToList(self.ephemNameEntry, self.ephemListModel))

    def getTargets(self):
        print("get")
        self.candidates = self.dbConnection.table_query("Candidates", "*",
                                                        "DateAdded > ?",
                                                        [datetime.utcnow() - timedelta(hours=36)],
                                                        returnAsCandidates=True)
        self.candidateDf = Candidate.candidatesToDf(self.candidates)
        self.candidatesByID = {c.ID: c for c in self.candidates}
        self.candidateDict = {c.CandidateName: c for c in self.candidates}
        self.indexOfIDColumn = self.candidateDf.columns.get_loc("ID")
        self.indexOfNameColumn = self.candidateDf.columns.get_loc("CandidateName")
        return self

    def getStringsAsCandidates(self, strings, handleErrorFunc=None):
        # strings is a list of strings that can be resolved in this way
        print("Selected", strings)
        candidates = []
        for i in strings:
            try:
                if "ID" in i:
                    candidates.append(self.candidatesByID[i.split(" ")[-1]])
                    continue
                candidates.append(self.candidateDict[i])
            except:
                # TODO: Handle this
                if handleErrorFunc:
                    handleErrorFunc("Couldn't find candidate for entry " + i)
        return candidates
        # selectedIds = table.selectionModel().selectedRows(column=table.model().)

        # return {d:self.ca for c,d in }

    def displayCandidates(self):
        if self.candidates is None:
            self.getTargets()
        dispDf = self.candidateDf.copy()
        if not self.showRejectedCheckbox.isChecked():
            dispDf = dispDf[dispDf["RejectedReason"].isna()]
        if not self.showRemovedCheckbox.isChecked() and "RemovedReason" in dispDf.columns:
            dispDf = dispDf[dispDf["RemovedReason"].isna()]
        loadDfInTable(dispDf, self.candidateTable)

        return self

    def getEphemeris(self):
        if self.gettingEphemeris:
            print("Already getting.")
            return None
        if self.ephemProcess is not None:
            if self.ephemProcess.isActive:
                print("EPHEM PROCESS LEFT OPEN")
            del self.ephemProcess

        self.ephemProcess = Process("Ephemerides")

        ephemPopUp = EphemPopup()  # implement this - use progress bar
        self.ephemProcess.msg.connect(lambda message: print(message))
        self.processModel.add(self.ephemProcess)
        self.ephemProcess.finished.connect(lambda: print(self.ephemProcess.__dict__))
        print(self.ephemListModel.selectedRows(self.ephemListView))
        candidatesToRequest = self.getStringsAsCandidates(self.ephemListModel._data)
        print(candidatesToRequest)
        targetDict = {
            candidate.CandidateType: [c.CandidateName for c in candidatesToRequest if c.CandidateType == candidate.CandidateType] for
            candidate in candidatesToRequest}
        print(targetDict)
        self.ephemProcess.start("python", ['./MaestroCore/ephemerides.py', json.dumps(targetDict), "settings", "path"])

        # launch waiting window
        # gather the candidates indicated
        # read the specified ephem parameters
        # sort candidates by config
        # fire off (asynchronously) to their respective configs to get ephems, en masse
        # collect the results (lists of strings, each list being its own file, each string being its own line)
        # launch save window
        # save the files to the indicated location


app = QApplication([])

window = MainWindow()
window.displayCandidates()
window.show()

# start event loop
app.exec()
