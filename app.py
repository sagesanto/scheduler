import json
import random
import sys, os
import time

import pandas as pd
import pytz
from PyQt6 import QtGui, QtCore
from PyQt6.QtWidgets import QApplication, QWidget, QMainWindow, QTableWidget, \
    QTableWidgetItem as QTableItem, QLineEdit, QListView, QDockWidget, QComboBox, QPushButton
from PyQt6.QtCore import Qt, QItemSelectionModel, QDateTime
from MaestroCore.GUI.MainWindow import Ui_MainWindow
from scheduleLib import genUtils
from scheduleLib.candidateDatabase import Candidate, CandidateDatabase
from MaestroCore.utils.processes import ProcessModel, Process  # , ProcessDialog
from MaestroCore.utils.listModel import FlexibleListModel
from MaestroCore.utils.fileButton import FileSelectionButton
from datetime import datetime, timedelta

defaultSettings = {}  # don't know how this should be stored/managed/updated - should submodules be able to register their own settings? probably. that's annoying


class Settings:
    def __init__(self, settingsFilePath):
        self.path = settingsFilePath
        self._settings = {}
        self._linkBacks = []  # (settingName, writeFunction) tuples

    def loadSettings(self):
        with open(self.path, "r") as settingsFile:
            self._settings = json.load(settingsFile)

    def saveSettings(self):
        with open(self.path, "w") as settingsFile:
            json.dump(self._settings, settingsFile)

    def query(self, key):
        """
        Get the (value, type) pair associated with the setting with name key if such a pair exists, else None
        :param key:
        :return: tuple(value of setting,type of setting (string))
        """
        return self._settings[key] if key in self._settings.keys() else None

    def add(self, key, value, settingType):
        self._settings[key] = (value, settingType)
        self.saveSettings()

    def linkWatch(self, signal, key, valueSource, linkBack, datatype):
        """
        Link function signal to setting key such that setting key is set to the value from valueSource (can be a function) when signal is triggered
        :param signal: Qt signal
        :param key: string, name of existing setting
        :param valueSource: function or value

        """
        signal.connect(lambda: self.set(key, valueSource, datatype))
        self._linkBacks.append((key, (linkBack, datatype)))

    def update(self):
        for key, (func, datatype) in self._linkBacks:
            func(datatype(self._settings[key][0]))

    def set(self, key, value, datatype):
        if callable(value):
            value = value()
        if key in self._settings.keys():
            self._settings[key][0] = datatype(value)
            print(self.asDict())
            self.saveSettings()
            return
        raise ValueError("No such setting " + key)

    def reset(self):
        self._settings = defaultSettings
        self.saveSettings()

    def asDict(self):
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
    # dataframe.info()
    df = dataframe.copy()  # .reset_index()
    columnHeaders = df.columns
    numRows, numCols = len(df.index), len(columnHeaders)
    table.setRowCount(numRows)
    table.setColumnCount(numCols)
    # df.info()
    for i in range(numRows):
        for j in range(numCols):
            item = QTableItem(str(df.iloc[i][j]))
            table.setItem(i, j, item)
    table.resizeColumnsToContents()
    table.resizeRowsToContents()
    table.setHorizontalHeaderLabels(columnHeaders)


def comboValToIndex(comboBox: QComboBox, val):
    return comboBox.findText(val())


def datetimeToQDateTime(dt: datetime):
    return QDateTime.fromSecsSinceEpoch(int(dt.timestamp()))


def qDateTimeToDatetime(t):
    # print("t in qdatetimetodatetime:", type(t.toSecsSinceEpoch()))
    return datetime.fromtimestamp(t.toSecsSinceEpoch())


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.setWindowIcon(QtGui.QIcon("MaestroCore/logosAndIcons/windowIcon.png"))  # ----
        self.setupUi(self)

        # initialize custom things
        self.dbConnection = CandidateDatabase("candidate database.db", "Maestro")
        self.processModel = ProcessModel(statusBar=self.statusBar())
        self.ephemListModel = FlexibleListModel()
        self.settings = Settings("./MaestroCore/settings.txt")
        self.chooseSchedSavePath.setPrompt("Choose Save Path").isDirectoryDialog(True)
        self.databasePathChooseButton.setPrompt("Select Database File").setPrompt("Database File (*.db)")
        self.ephemChooseSaveButton.setPrompt("Choose Save Path").isDirectoryDialog(True)

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
        self.databaseProcess = None
        self.scheduleProcess = None
        self.scheduleDf = None

        # call setup functions
        self.settings.loadSettings()
        self.setConnections()

        self.processesTreeView.setModel(self.processModel)
        self.ephemListView.setModel(self.ephemListModel)
        self.processesTreeView.selectionModel().selectionChanged.connect(self.toggleProcessButtons)
        self.startCoordinator()

    def setConnections(self):
        self.refreshCandButton.clicked.connect(lambda: self.getTargets().displayCandidates())
        self.showRejectedCheckbox.stateChanged.connect(self.displayCandidates)
        self.showRemovedCheckbox.stateChanged.connect(self.displayCandidates)
        self.candidateEphemerisButton.clicked.connect(self.useCandidateTableEphemeris)
        self.getEphemsButton.clicked.connect(self.getEphemeris)
        self.ephemRemoveSelected.clicked.connect(
            lambda: self.ephemListModel.removeSelectedItems(self.ephemListView))
        self.ephemNameEntry.returnPressed.connect(
            lambda: addLineContentsToList(self.ephemNameEntry, self.ephemListModel))
        self.processPauseButton.clicked.connect(self.pauseProcess)
        self.processResumeButton.clicked.connect(self.resumeProcess)
        self.processAbortButton.clicked.connect(self.abortProcess)
        self.processModel.rowsInserted.connect(lambda parent: self.processesTreeView.expandRecursively(parent))
        self.requestDbRestartButton.clicked.connect(self.startCoordinator)
        self.genScheduleButton.clicked.connect(self.runScheduler)
        self.pingButton.clicked.connect(self.pingProcess)
        self.requestDbCycleButton.clicked.connect(self.requestDbCycle)
        self.hardModeButton.clicked.connect(self.hardMode)
        self.allCandidatesCheckbox.stateChanged.connect(lambda: self.getTargets().displayCandidates())
        self.scheduleAutoTimeSetCheckbox.stateChanged.connect(lambda state: self.autoSetSchedulerTimes(state))
        self.scheduleAutoTimeSetCheckbox.stateChanged.connect(lambda state: self.scheduleStartTimeEdit.setDisabled(state))  # disable the time entry when auto is checked
        self.scheduleAutoTimeSetCheckbox.stateChanged.connect(lambda state: self.scheduleEndTimeEdit.setDisabled(state))
        self.scheduleEndTimeEdit.dateTimeChanged.connect(lambda Qdt: self.scheduleStartTimeEdit.setMaximumDateTime(Qdt))  # so start is always < end


        self.settings.linkWatch(self.intervalComboBox.currentTextChanged, "ephemInterval",
                                lambda: comboValToIndex(self.intervalComboBox, self.intervalComboBox.currentText),
                                self.intervalComboBox.setCurrentIndex, int)
        self.settings.linkWatch(self.obsCodeLineEdit.textChanged, "ephemsObsCode", self.obsCodeLineEdit.text,
                                self.obsCodeLineEdit.setText, str)
        self.settings.linkWatch(self.ephemStartDelayHrsSpinBox.valueChanged, "ephemStartDelayHrs",
                                self.ephemStartDelayHrsSpinBox.value, self.ephemStartDelayHrsSpinBox.setValue, int)
        self.settings.linkWatch(self.formatComboBox.currentTextChanged, "ephemFormat",
                                lambda: comboValToIndex(self.formatComboBox, self.formatComboBox.currentText),
                                self.formatComboBox.setCurrentIndex, int)
        self.settings.linkWatch(self.minutesBetweenCyclesSpinBox.valueChanged, "databaseWaitTimeMinutes",
                                self.minutesBetweenCyclesSpinBox.value, self.minutesBetweenCyclesSpinBox.setValue, int)
        self.settings.linkWatch(self.scheduleStartTimeEdit.dateTimeChanged, "scheduleStartTimeSecs",
                                lambda: self.scheduleStartTimeEdit.dateTime().toSecsSinceEpoch(),
                                lambda secs: self.scheduleStartTimeEdit.setDateTime(QDateTime.fromSecsSinceEpoch(secs)),
                                int)
        self.settings.linkWatch(self.scheduleEndTimeEdit.dateTimeChanged, "scheduleEndTimeSecs",
                                lambda: self.scheduleEndTimeEdit.dateTime().toSecsSinceEpoch(),
                                lambda secs: self.scheduleEndTimeEdit.setDateTime(QDateTime.fromSecsSinceEpoch(secs)),
                                int)

        self.settings.linkWatch(self.chooseSchedSavePath.chosen, "scheduleSaveDir", self.chooseSchedSavePath.getPath,
                                self.chooseSchedSavePath.updateFilePath, str)
        self.settings.linkWatch(self.ephemChooseSaveButton.chosen, "ephemsSavePath", self.ephemChooseSaveButton.getPath,
                                self.ephemChooseSaveButton.updateFilePath, str)
        self.settings.linkWatch(self.databasePathChooseButton.chosen, "candidateDbPath",
                                self.databasePathChooseButton.getPath,
                                self.databasePathChooseButton.updateFilePath, str)
        self.settings.linkWatch(self.allCandidatesCheckbox.stateChanged, "showAllCandidates", self.allCandidatesCheckbox.isChecked, self.allCandidatesCheckbox.setChecked, bool)
        self.settings.linkWatch(self.schedulerSaveEphemsBox.stateChanged, "schedulerSaveEphems", self.schedulerSaveEphemsBox.isChecked, self.schedulerSaveEphemsBox.setChecked, bool)
        self.settings.linkWatch(self.scheduleAutoTimeSetCheckbox.stateChanged, "autoSetScheduleTimes", self.scheduleAutoTimeSetCheckbox.isChecked, self.scheduleAutoTimeSetCheckbox.setChecked, bool)
        self.settings.update()

    def startCoordinator(self):
        if not os.path.exists(self.settings.query("candidateDbPath")[0]):
            self.statusBar().showMessage(
                "To run database coordination, choose a database under Database > Control, then press 'Request Restart'",
                10000)
        if self.databaseProcess is not None:
            if self.databaseProcess.isActive:  # run a restart
                print("Restarting database coordinator.")
                self.databaseProcess.abort()
                time.sleep(1)
                self.databaseProcess = None
                self.startCoordinator()
                return
        self.databaseProcess = Process("Database")
        self.processModel.add(self.databaseProcess)
        # self.databaseProcess.msg.connect(lambda message: print(message))
        self.databaseProcess.msg.connect(self.dbStatusChecker)
        self.databaseProcess.ended.connect(self.getTargets)

        self.databaseProcess.start("python", ['./MaestroCore/database.py', json.dumps(self.settings.asDict())])

    def runScheduler(self):
        self.genScheduleButton.setDisabled(True)
        if self.scheduleAutoTimeSetCheckbox.isChecked():
            self.autoSetSchedulerTimes()
        self.scheduleProcess = Process("Scheduler")
        self.processModel.add(self.scheduleProcess)
        self.scheduleProcess.msg.connect(lambda msg: print("Scheduler: ", msg))
        self.scheduleProcess.start("python", ["newScheduler.py", json.dumps(self.settings.asDict())])
        self.scheduleProcess.ended.connect(lambda: self.genScheduleButton.setDisabled(False))
        self.scheduleProcess.ended.connect(self.displaySchedule)

    def hardMode(self):
        buttons = [attr for attr in self.__dict__.values() if isinstance(attr, QPushButton) and not isinstance(attr, FileSelectionButton)]
        displayTexts = [button.text() for button in buttons]
        for b in buttons:
            while True:
                t = random.choice(displayTexts)
                if t != b.text() or len(displayTexts) == 1:
                    b.setText(t)
                    displayTexts.remove(t)
                    break

    def displaySchedule(self):
        basepath = self.settings.query("scheduleSaveDir")[0] + os.sep + "schedule"
        imgPath = basepath + ".png"
        csvPath = basepath + ".csv"
        if os.path.isfile(imgPath):
            imgProfile = QtGui.QImage(imgPath)  # QImage object
            imgProfile = imgProfile.scaled(self.scheduleImageDisplay.width(), self.scheduleImageDisplay.height(),
                                           aspectRatioMode=QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                           transformMode=QtCore.Qt.TransformationMode.SmoothTransformation)
            self.scheduleImageDisplay.setPixmap(QtGui.QPixmap.fromImage(imgProfile))
        else:
            print("Can't find saved image!")
        if os.path.isfile(csvPath):
            self.scheduleDf = pd.read_csv(csvPath)
            loadDfInTable(self.scheduleDf, self.scheduleTable)

    def autoSetSchedulerTimes(self, run=True):
        if run:
            print("auto")
            start = datetimeToQDateTime(max(self.sunsetUTC, pytz.UTC.localize(datetime.utcnow())))
            end = datetimeToQDateTime(self.sunriseUTC)

            self.scheduleStartTimeEdit.setDateTime(start)
            self.scheduleEndTimeEdit.setDateTime(end)

    def requestDbCycle(self):
        print("Requesting")
        self.databaseProcess.write("Database: Cycle\n")

    def dbStatusChecker(self, msg):
        if "Database: Status:" in msg:
            print("Db status received:", msg)
            self.databaseProcess.ended.emit(msg.replace("Database: Status:", ""))  # this is cheating

    def toggleProcessButtons(self):
        self.processesTreeView.selectionModel().blockSignals(True)
        for button in [self.processAbortButton, self.processPauseButton, self.processResumeButton, self.pingButton]:
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

    def pingProcess(self):
        for index in self.processesTreeView.selectedIndexes():
            index.internalPointer().tags["Process"].ping()

    def useCandidateTableEphemeris(self):
        """
        Add the desigs of all selected candidates in the candidate table to the ephems list, then set the ephem tab as the active tab
        """
        candidates = [self.candidateDict[d] for d in getSelectedFromTable(self.candidateTable, self.indexOfNameColumn)]
        for candidate in candidates:
            self.ephemListModel.addItem(candidate)
        self.tabWidget.setCurrentWidget(self.tabWidget.findChild(QWidget, "ephemsTab"))

    def getTargets(self):
        self.candidates = self.dbConnection.table_query("Candidates", "*",
                                                        "DateAdded > ?" if not self.settings.query("showAllCandidates")[0] else "1=1",
                                                        [datetime.utcnow() - timedelta(hours=36)] if not self.settings.query("showAllCandidates")[0] else [],
                                                        returnAsCandidates=True)
        if self.candidates:
            self.candidateDf = Candidate.candidatesToDf(self.candidates)
            self.candidatesByID = {c.ID: c for c in self.candidates}
            self.candidateDict = {c.CandidateName: c for c in self.candidates}
            self.indexOfIDColumn = self.candidateDf.columns.get_loc("ID")
            self.indexOfNameColumn = self.candidateDf.columns.get_loc("CandidateName")
        else:
            print("No candidates")
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
            except KeyError:
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
            if not self.showRejectedCheckbox.isChecked() and "RejectedReason" in dispDf.columns:
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
        self.processModel.add(self.ephemProcess)
        self.ephemProcess.ended.connect(lambda: print(self.processModel.rootItem.__dict__))
        self.ephemProcess.msg.connect(lambda msg: print(msg))
        self.ephemProcess.ended.connect(lambda: self.getEphemsButton.setDisabled(False))
        targetDict = {
            candidate.CandidateType: [c.CandidateName for c in candidatesToRequest if
                                      c.CandidateType == candidate.CandidateType] for
            candidate in candidatesToRequest}
        print(targetDict)
        self.ephemProcess.start("python", ['./MaestroCore/ephemerides.py', json.dumps(targetDict),
                                           json.dumps(self.settings.asDict())])
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
