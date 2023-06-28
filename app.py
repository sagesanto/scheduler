import sys, os, keyring  # manage files, api key
from abc import abstractmethod

import pandas as pd
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QMainWindow, QFileDialog, QButtonGroup, QTableWidget, \
    QTableWidgetItem as QTableItem, QListWidget, QLineEdit
from PyQt6.QtCore import Qt, pyqtSignal, QRunnable, QObject, QThreadPool
from PyQt6 import uic, QtCore
from MainWindow import Ui_MainWindow
from scheduleLib import genUtils, mpcUtils, mpcTargetSelectorCore, asyncUtils
from scheduleLib.candidateDatabase import Candidate, CandidateDatabase
from datetime import datetime, timedelta


class Worker(QRunnable):
    @abstractmethod
    def __init__(self):
        super().__init__()
        self.finished = pyqtSignal()
        self.progress = pyqtSignal(int)

    @abstractmethod
    def run(self):
        self.progress.emit(1)
        self.finished.emit()


class Ephemerides(Worker):
    def __init__(self):
        super().__init__()
        self.finished = pyqtSignal()
        self.progress = pyqtSignal(int)
        self.error = pyqtSignal(str)

    def run(self):
        pass


def link(itemEvent, function):
    itemEvent.connect(function)


def removeSelectedItems(tableOrList):
    listItems = tableOrList.selectedItems()
    if not listItems: return
    for item in listItems:
        tableOrList.takeItem(tableOrList.row(item))


def addEntryToList(entry, list: QListWidget):
    list.addItem(entry)


def addLineContentsToList(lineEdit: QLineEdit, list: QListWidget):
    addEntryToList(lineEdit.text(), list)
    lineEdit.clear()



def getSelected(table, colIndex):
    selected = []
    indexes = table.selectionModel().selectedRows(column=1)
    model = table.model()
    for index in indexes:
        selected.append(model.data(model.index(index.row(), colIndex)))
    return selected


def loadDfInTable(dataframe: pd.DataFrame, table: QTableWidget, checkboxes=False):  # SHARED MUTABLE STATE!!!!! :D
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

    def useCandidateTableEphemeris(self):
        for desig in getSelected(self.candidateTable, 0):
            addEntryToList(desig, self.ephemList)
        self.tabWidget.setCurrentWidget(self.tabWidget.findChild(QWidget, "ephemsTab"))
        # add the desigs of all selected candidates in the candidate table to the ephem table
        # set the ephem tab as the active tab
        #

    # def initializeStates(self):

    def setConnections(self):
        self.refreshCandButtons.clicked.connect(lambda refresh: self.getTargets().displayCandidates())
        self.showRejectedCheckbox.stateChanged.connect(self.displayCandidates)
        self.showRemovedCheckbox.stateChanged.connect(self.displayCandidates)
        self.candidateEphemerisButton.clicked.connect(self.useCandidateTableEphemeris)
        self.ephemRemoveSelected.clicked.connect(lambda g: removeSelectedItems(self.ephemList))
        self.ephemNameEntry.returnPressed.connect(lambda: addLineContentsToList(self.ephemNameEntry, self.ephemList))

    def getTargets(self):
        print("get")
        self.candidates = self.dbConnection.table_query("Candidates", "*",
                                                        "DateAdded > ?",
                                                        [datetime.utcnow() - timedelta(hours=36)],
                                                        returnAsCandidates=True)
        self.candidateDf = Candidate.candidatesToDf(self.candidates)
        self.candidatesByID = {c.ID: c for c in self.candidates}
        return self

    def displayCandidates(self):
        if self.candidates is None:
            self.getTargets()
        dispDf = self.candidateDf.copy()
        if not self.showRejectedCheckbox.isChecked():
            dispDf = dispDf[dispDf["RejectedReason"].isna()]
        if not self.showRemovedCheckbox.isChecked() and "RemovedReason" in dispDf.columns:
            dispDf = dispDf[dispDf["RemovedReason"].isna()]
        loadDfInTable(dispDf, self.candidateTable, checkboxes=True)

        return self

    def getEphemeris(self):
        pass
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
