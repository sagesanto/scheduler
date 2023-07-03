import json
import sys, os, keyring
from abc import abstractmethod

import pandas as pd
import pytz
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QMainWindow, QFileDialog, QButtonGroup, QTableWidget, \
    QTableWidgetItem as QTableItem, QListWidget, QLineEdit, QListView, QDockWidget, QDialog, QStatusBar
from PyQt6.QtCore import Qt, pyqtSignal, QRunnable, QObject, QThreadPool, QProcess, QAbstractListModel, \
    QItemSelectionModel
from PyQt6 import uic, QtCore, QtGui
from MaestroCore.GUI.MainWindow import Ui_MainWindow
from scheduleLib import genUtils, asyncUtils
from scheduleLib.candidateDatabase import Candidate, CandidateDatabase
from MaestroCore.MaestroUtils.processes import ProcessModel, Process, ProcessDialog
from MaestroCore.MaestroUtils.listModel import FlexibleListModel
from datetime import datetime, timedelta

defaultSettings = {}  # don't know how this should be stored/managed/updated - should submodules be able to register their own settings? probably. that's annoying


class Settings:
    def __init__(self, settingsFilePath):
        self.path = settingsFilePath
        self._settings = {}

    def loadSettings(self):
        with open(self.path, "r") as settingsFile:
            self._settings = json.load(settingsFile)

    def saveSettings(self):
        json.dump(self._settings, self.path)

    def query(self, key):
        """
        Get the (value, type) pair associated with the setting with name key if such a pair exists, else None
        :param key:
        :return: tuple(value of setting,type of setting (string))
        """
        return self._settings[key] if key in self._settings.keys() else None

    def add(self, key, value, settingType):
        self._settings[key] = (value, settingType)

    def linkWatch(self, signal, key, valueSource):
        """
        Link function signal to setting key such that setting key is set to the value from valueSource (can be a function) when signal is triggered
        :param signal: Qt signal
        :param key: string, name of existing setting
        :param valueSource: function or value
        """
        signal.connect(lambda: self.set(key, valueSource))

    def set(self, key, value):
        if callable(value):
            value = value()
        if key in self._settings.keys():
            self._settings[key][0] = value
            print(self.asDict())
            return
        raise ValueError("No such setting " + key)

    def reset(self):
        self._settings = defaultSettings
        self.saveSettings()

    def asDict(self):
        print(self._settings)
        return {k: v for k, [v, _] in self._settings.items()}


def getSelectedFromList(view: QListView):
    selectedIndexes = view.selectedIndexes()
    return [index.data(Qt.ItemDataRole.DisplayRole) for index in selectedIndexes]


def redock(dock: QDockWidget, window):
    dock.setParent(window)
    dock.setFloating(False)


def addLineContentsToList(lineEdit: QLineEdit, lis):
    lis.addItem(lineEdit.text())
    lineEdit.clear()


def getSelectedFromTable(table, colIndex):
    selected = []
    indexes = table.selectionModel().selectedRows()
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
        self.setupUi(self)

        # initialize custom things
        self.dbConnection = CandidateDatabase("candidate database.db", "Maestro")
        self.processModel = ProcessModel(statusBar=self.statusBar())
        self.ephemListModel = FlexibleListModel()
        self.settings = Settings("./MaestroCore/settings.txt")

        # initialize misc things
        self.candidateDict = None
        self.indexOfIDColumn = None
        self.indexOfNameColumn = None
        self.sunriseUTC, self.sunsetUTC = genUtils.getSunriseSunset()
        self.sunriseUTC, self.sunsetUTC = genUtils.roundToTenMinutes(self.sunriseUTC), genUtils.roundToTenMinutes(
            self.sunsetUTC)
        self.sunriseUTC -= timedelta(hours=1)
        self.candidates = None
        self.candidateDf = None
        self.candidatesByID = None
        self.ephemProcess = None
        self.ephemProcessIDs = []

        # call setup functions
        self.setConnections()
        self.processesTreeView.setModel(self.processModel)
        self.ephemListView.setModel(self.ephemListModel)
        self.settings.loadSettings()
        self.processesTreeView.selectionModel().selectionChanged.connect(self.toggleProcessButtons)

    def setConnections(self):
        self.refreshCandButton.clicked.connect(lambda refresh: self.getTargets().displayCandidates())
        self.showRejectedCheckbox.stateChanged.connect(self.displayCandidates)
        self.showRemovedCheckbox.stateChanged.connect(self.displayCandidates)
        self.candidateEphemerisButton.clicked.connect(self.useCandidateTableEphemeris)
        self.getEphemsButton.clicked.connect(self.getEphemeris)
        self.ephemRemoveSelected.clicked.connect(
            lambda g: self.ephemListModel.removeSelectedItems(self.ephemListView))
        self.ephemNameEntry.returnPressed.connect(
            lambda: addLineContentsToList(self.ephemNameEntry, self.ephemListModel))
        self.processPauseButton.clicked.connect(self.pauseProcess)
        self.processResumeButton.clicked.connect(self.resumeProcess)
        self.processAbortButton.clicked.connect(self.abortProcess)
        self.processModel.rowsInserted.connect(lambda parent: self.processesTreeView.expandRecursively(parent))
        self.settings.linkWatch(self.intervalComboBox.currentTextChanged, "ephemInterval",
                                self.intervalComboBox.currentText)
        self.settings.linkWatch(self.obsCodeLineEdit.textChanged, "ephemsObsCode", self.obsCodeLineEdit.text)
        self.settings.linkWatch(self.ephemStartDelayHrsSpinBox.valueChanged, "ephemStartDelayHrs",
                                self.ephemStartDelayHrsSpinBox.value)
        self.settings.linkWatch(self.formatComboBox.currentTextChanged, "ephemFormat", self.formatComboBox.currentText)

    def toggleProcessButtons(self):
        self.processesTreeView.selectionModel().blockSignals(True)
        for button in [self.processAbortButton, self.processPauseButton, self.processResumeButton]:
            button.setDisabled(not bool(len(self.processesTreeView.selectedIndexes())))
        processItems = []
        for index in self.processesTreeView.selectedIndexes():
            if self.processModel.data(index.parent(), Qt.ItemDataRole.DisplayRole) is not None:
                if index.parent() not in processItems:
                    processItems.append(index.parent())
                continue
            processItems.append(index)
        self.processesTreeView.clearSelection()
        for index in processItems:
            self.processesTreeView.selectionModel().select(index,
                                                           QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        self.processesTreeView.selectionModel().blockSignals(False)

    def pauseProcess(self):
        if "win" not in sys.platform:
            for index in self.processesTreeView.selectedIndexes():
                index.internalPointer().tags["Process"].pause()
            return
        self.statusBar().showMessage("Not supported on Windows.", 5000)

    def resumeProcess(self):
        if "win" not in sys.platform:
            for index in self.processesTreeView.selectedIndexes():
                index.internalPointer().tags["Process"].resume()
            return
        self.statusBar().showMessage("Not supported on Windows.", 5000)

    def abortProcess(self):
        for index in self.processesTreeView.selectedIndexes():
            index.internalPointer().tags["Process"].abort()

    def useCandidateTableEphemeris(self):
        """
        Add the desigs of all selected candidates in the candidate table to the ephems list, then set the ephem tab as the active tab
        """
        candidates = [self.candidateDict[d] for d in getSelectedFromTable(self.candidateTable, self.indexOfNameColumn)]
        for candidate in candidates:
            self.ephemListModel.addItem(candidate)
        self.tabWidget.setCurrentWidget(self.tabWidget.findChild(QWidget, "ephemsTab"))

    def getTargets(self):
        print("get")
        self.candidates = self.dbConnection.table_query("Candidates", "*",
                                                        "DateAdded > ?",
                                                        [datetime.utcnow() - timedelta(hours=36)],
                                                        returnAsCandidates=True)
        if self.candidates:
            self.candidateDf = Candidate.candidatesToDf(self.candidates)
            self.candidatesByID = {c.ID: c for c in self.candidates}
            self.candidateDict = {c.CandidateName: c for c in self.candidates}
            self.indexOfIDColumn = self.candidateDf.columns.get_loc("ID")
            self.indexOfNameColumn = self.candidateDf.columns.get_loc("CandidateName")
        return self

    def getEntriesAsCandidates(self, entries, handleErrorFunc=None):
        # strings is a list of strings that can be resolved in this way
        print("Selected", entries)
        candidates = []
        for i in entries:
            try:
                if isinstance(i, Candidate):
                    candidates.append(i)
                    continue
                candidates.append(self.candidateDict[i])
            except:
                # TODO: Handle this
                if handleErrorFunc:
                    handleErrorFunc("Couldn't find candidate for entry " + i)
        return candidates

    def displayCandidates(self):
        """
        Load the stored candidates into the table. Fetches candidates if has None
        :return:
        """
        if self.candidates is None:
            self.getTargets()
        if self.candidates:
            dispDf = self.candidateDf.copy()
            if not self.showRejectedCheckbox.isChecked():
                dispDf = dispDf[dispDf["RejectedReason"].isna()]
            if not self.showRemovedCheckbox.isChecked() and "RemovedReason" in dispDf.columns:
                dispDf = dispDf[dispDf["RemovedReason"].isna()]
            loadDfInTable(dispDf, self.candidateTable)

        return self

    def getEphemeris(self):
        if self.ephemProcess is not None:
            if self.ephemProcess.isActive:
                print("Already getting.")
                return
            print("EphemProcess is not None and not active")
            self.ephemProcess.reset()

        candidatesToRequest = self.getEntriesAsCandidates(self.ephemListModel.data)
        if len(candidatesToRequest) == 0:
            print("No ephems to get.")
            return

        self.getEphemsButton.setDisabled(True)
        self.ephemProcess = Process("Ephemerides")
        self.ephemProcessIDs.append(id(self.ephemProcess))
        print(self.ephemProcessIDs)
        self.processModel.add(self.ephemProcess)
        # ephemPopUp = ProcessDialog("Ephemerides", process=self.ephemProcess, parent=self)
        self.ephemProcess.msg.connect(lambda message: print(message))
        self.ephemProcess.ended.connect(lambda: print(self.processModel.rootItem.__dict__))
        self.ephemProcess.ended.connect(lambda: self.getEphemsButton.setDisabled(False))
        targetDict = {
            candidate.CandidateType: [c.CandidateName for c in candidatesToRequest if
                                      c.CandidateType == candidate.CandidateType] for
            candidate in candidatesToRequest}
        print(targetDict)
        self.ephemProcess.start("python", ['./MaestroCore/ephemerides.py', json.dumps(targetDict),
                                           json.dumps(self.settings.asDict())])
        # ephemPopUp.exec()

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
