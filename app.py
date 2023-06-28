import sys, os, keyring  # manage files, api key

import pandas as pd
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QMainWindow, QFileDialog, QButtonGroup, QTableWidget, \
    QTableWidgetItem as QTableItem, QListWidget, QLineEdit
from PyQt6.QtCore import Qt
from PyQt6 import uic, QtCore
from PyQt6.QtCore import QObject
from MainWindow import Ui_MainWindow
from scheduleLib import genUtils, mpcUtils, mpcTargetSelectorCore, asyncUtils
from scheduleLib.candidateDatabase import Candidate, CandidateDatabase
from datetime import datetime, timedelta


def link(itemEvent, function):
    itemEvent.connect(function)


def removeSelectedItems(tableOrList):
    listItems = tableOrList.selectedItems()
    if not listItems: return
    for item in listItems:
        tableOrList.takeItem(tableOrList.row(item))


def addEntryToList(entry, list: QListWidget):
    list.addItem(entry)

def addLineContentsToList(lineEdit:QLineEdit,list:QListWidget):
    addEntryToList(lineEdit.text(), list)
    lineEdit.clear()

def getSelected(table, colIndex):
    print("getting")
    selected = []
    indexes = table.selectionModel().selectedRows(column=1)
    model = table.model()
    for index in indexes:
        selected.append(model.data(model.index(index.row(), colIndex)))
    print(selected)
    return selected


def loadDfInTable(dataframe: pd.DataFrame, table: QTableWidget, checkboxes=False):  # SHARED MUTABLE STATE!!!!! :D
    df = dataframe.copy()  # .reset_index()
    columnHeaders = df.columns
    numRows, numCols = len(df.index), len(columnHeaders)
    print(numRows, numCols)
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


    # def useSelectedEphemeris(self):
    #
    #
    # def initializeStates(self):


    def setConnections(self):
        self.refreshCandButtons.clicked.connect(lambda refresh: self.getTargets().displayCandidates())
        # self.candidateTable.horizontalHeader().sectionClicked.connect(lambda c: print("clicked"))
        self.showRejectedCheckbox.stateChanged.connect(self.displayCandidates)
        self.showRemovedCheckbox.stateChanged.connect(self.displayCandidates)
        self.candidateEphemerisButton.clicked.connect(lambda f: getSelected(self.candidateTable, 0))
        self.ephemRemoveSelected.clicked.connect(lambda g: removeSelectedItems(self.ephemList))
        self.ephemNameEntry.returnPressed.connect(lambda: addLineContentsToList(self.ephemNameEntry, self.ephemList))
        # , QtCore.PYQT_SIGNAL("sectionClicked()"), lambda c: print("clicked"))
        # self.candidateTable.selectionModel().selectionChanged.connect(
        #     self.tableSelectionChanged
        # )
        # self.candidateTable.clicked.connect(self.tableSingleClicked)

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
