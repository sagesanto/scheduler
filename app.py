import sys, os, keyring  # manage files, api key

import pandas as pd
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QMainWindow, QFileDialog, QButtonGroup, QTableWidget, \
    QTableWidgetItem as QTableItem
from PyQt6.QtCore import Qt
from PyQt6 import uic, QtCore
from PyQt6.QtCore import QObject
from MainWindow import Ui_MainWindow
from scheduleLib import genUtils, mpcUtils, mpcTargetSelectorCore, asyncUtils
from scheduleLib.candidateDatabase import Candidate, CandidateDatabase
from datetime import datetime, timedelta


def link(itemEvent, function):
    itemEvent.connect(function)


def getSelected(table,colIndex):
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
    checkBoxes = {}
    for i in range(numRows):
        for j in range(numCols):
            item = QTableItem(str(df.iloc[i][j]))
            # if j == 0 and checkboxes:
            #     item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            #     item.setCheckState(Qt.CheckState.Unchecked)
            #     checkBoxes[df.iloc[i][j]] = item
            table.setItem(i, j, item)
    table.resizeColumnsToContents()
    table.resizeRowsToContents()
    table.setHorizontalHeaderLabels(columnHeaders)
    return checkBoxes


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.setupUi(self)
        self.sunriseUTC, self.sunsetUTC = genUtils.getSunriseSunset()
        self.sunriseUTC, self.sunsetUTC = genUtils.roundToTenMinutes(self.sunriseUTC), genUtils.roundToTenMinutes(
            self.sunsetUTC)
        self.sunriseUTC -= timedelta(hours=1)
        self.dbConnection = CandidateDatabase("candidate database.db", "App")
        self.candidates = None
        self.candidateDf = None
        self.setConnections()
        self.filterProxyModel = QtCore.QSortFilterProxyModel()
        self.selectedCandidates = []
        self.candidatesByID = None

    def candidateSelected(self, ID):
        print(ID, "toggled")
        c = self.candidatesByID[ID]
        if c not in self.selectedCandidates:
            self.selectedCandidates.append(c)
        else:
            self.selectedCandidates.remove(c)

    # def useSelectedEphemeris(self):
    #
    #
    # def initializeStates(self):


    def setConnections(self):
        self.refreshCandButtons.clicked.connect(lambda refresh: self.getTargets().displayCandidates())
        self.candidateTable.horizontalHeader().sectionClicked.connect(lambda c: print("clicked"))
        self.showRejectedCheckbox.stateChanged.connect(self.displayCandidates)
        self.showRemovedCheckbox.stateChanged.connect(self.displayCandidates)
        self.candidateEphemerisButton.clicked.connect(lambda g: getSelected(self.candidateTable, 1))
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
        checkBoxes = loadDfInTable(dispDf, self.candidateTable, checkboxes=True)
        # # for key, box in checkBoxes.items():
        # #     box.stateChange.connect(lambda click: print("c"))
        return self

    def tableSelectionChanged(
            self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection
    ):
        """Catch Selection changed behaviour"""

        for index in selected.indexes():
            # self.filterProxyModel.setData(index, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
            print("selected", index)
        for index in deselected.indexes():
            print("deselected", index)
            # self.filterProxyModel.setData(index, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)

    def tableSingleClicked(self, modelIndex: QtCore.QModelIndex):
        # print(modelIndex)
        checkState = self.filterProxyModel.itemData(modelIndex).get(10)
        if (checkState == 2 and modelIndex not in self.candidateTable.selectedIndexes()) \
                or (checkState == 0 and modelIndex in self.candidateTable.selectedIndexes()):
            self.candidateTable.selectionModel().select(modelIndex, QtCore.QItemSelectionModel.SelectionFlag.Toggle)
            print(modelIndex)


app = QApplication([])

window = MainWindow()
window.displayCandidates()
window.show()

# start event loop
app.exec()
