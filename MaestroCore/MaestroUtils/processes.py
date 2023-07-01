import pandas as pd
import pytz
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QMainWindow, QFileDialog, QButtonGroup, QTableWidget, \
    QTableWidgetItem as QTableItem, QListWidget, QLineEdit
from PyQt6.QtCore import Qt, pyqtSignal, QRunnable, QObject, QThreadPool, QProcess
from PyQt6 import QtCore
from datetime import datetime, timedelta


def generateTimestampString():
    return datetime.now().strftime("%m/%d %H:%M") + " local / " + datetime.now(pytz.UTC).strftime(
        "%m/%d %H:%M") + " UTC"


def decodeStdOut(p: QProcess):
    return bytes(p.readAllStandardOutput()).decode("utf-8")


def decodeStdErr(p: QProcess):
    return bytes(p.readAllStandardError()).decode("utf-8")


def interpretState(state):
    states = {
        QProcess.ProcessState.NotRunning: 'Not running',
        QProcess.ProcessState.Starting: 'Starting',
        QProcess.ProcessState.Running: 'Running',
    }
    return states[state]


class TreeItem(QObject):
    updated = pyqtSignal(QtCore.QModelIndex)
    # updated = pyqtSignal()

    def __init__(self, data, parent=None):
        super().__init__()
        self.parentItem = parent
        self.itemData = data
        self.index = None
        self.childItems = []

    def __repr__(self):
        return "Tree Item" + (": Root: " if self.parentItem is None else " ") + str(self.itemData)

    def setIndex(self,index:QtCore.QModelIndex):
        self.index = index
        print("Setting index")
        print(self.index)
        print(self.index.column())
        print(self.index.row())
        print(self.index.isValid())
        print(type(self.index))

    def appendChild(self, item):
        self.childItems.append(item)
        return self

    def child(self, row):
        return self.childItems[row]

    def childCount(self):
        return len(self.childItems)

    def columnCount(self):
        return len(self.itemData)

    def data(self, column):
        try:
            return self.itemData[column]
        except IndexError:
            return None

    @QtCore.pyqtSlot()
    def updateData(self, column, data):
        try:
            self.itemData[column] = data
            self.updated.emit(self.index)
        except IndexError:
            raise

    def parent(self):
        return self.parentItem

    def row(self):
        if self.parentItem:
            return self.parentItem.childItems.index(self)
        return 0


class Process(QProcess):
    deleted = pyqtSignal()
    logged = pyqtSignal(str)
    error = pyqtSignal(str)
    msg = pyqtSignal(str)
    lastLog = pyqtSignal(str)

    def __init__(self, name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name
        # self.id = QProcess.processId(self.process)
        self.startLocal = datetime.now()
        self.startUTC = datetime.now(pytz.UTC)
        self.startString = generateTimestampString()
        self.result = ""  # short string or error msg
        self.end = None
        self.log = []
        self.connect()

    def connect(self):
        self.readyReadStandardError.connect(lambda: self.writeToErrorLog(decodeStdErr(self)))
        self.readyReadStandardOutput.connect(lambda: self.writeToLog(decodeStdOut(self)))
        self.finished.connect(lambda: self.lastLog.emit(self.log[-1] if len(self.log) else ""))
        self.finished.connect(self.terminate)  # this might not be necessary

    def __del__(self):
        print("Deleting process", self.name, "with PID", self.processId())
        self.deleted.emit()
        self.terminate()
        del self

    def reset(self):
        print("Resetting")
        # self.deleted.emit()

    @property
    def status(self):
        return interpretState(self.state())

    @property
    def isActive(self):
        return self.state() != QProcess.ProcessState.NotRunning

    def writeToErrorLog(self, error):
        error = self.name + " encountered an error: " + error
        self.errorLog.append(error)
        self.error.emit(error)
        self.msg.emit(error)

    def writeToLog(self, content):
        self.log.append(content)
        self.logged.emit(content)
        self.msg.emit(content)


class ProcessModel(QtCore.QAbstractItemModel):
    updated = pyqtSignal()

    def __init__(self, processes=None, parent=None):
        # processes is a list of [(Name, QProcess)] pairs
        super(ProcessModel, self).__init__(parent)
        processes = processes or []
        self.rootItem = TreeItem(("Field", "Info"))
        for process in processes:
            self.add(process)

    def columnCount(self, parent):
        if parent.isValid():
            return parent.internalPointer().columnCount()
        else:
            return self.rootItem.columnCount()

    def data(self, index, role):
        if not index.isValid():
            return None
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        item = index.internalPointer()
        return item.data(index.column())

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def headerData(self, section, orientation, role):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.rootItem.data(section)
        return None

    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QtCore.QModelIndex()
        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()
        childItem = parentItem.child(row)
        if childItem:
            return self.createIndex(row, column, childItem)
        else:
            return QtCore.QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QtCore.QModelIndex()
        childItem = index.internalPointer()
        parentItem = childItem.parent()
        if parentItem == self.rootItem:
            return QtCore.QModelIndex()
        return self.createIndex(parentItem.row(), 0, parentItem)

    def rowCount(self, parent):
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()
        return parentItem.childCount()

    def emitDataChanged(self, index:QtCore.QModelIndex):
        print("updating items")
        self.dataChanged.emit(index,index)
        print("is valid index:",index.isValid())
        # try:
        print("Data:", self.data(index, Qt.ItemDataRole.DisplayRole))
        # except Exception as e:
        #     print(e)

        # startIndex = self.index(0, 0, QtCore.QModelIndex())
        # endIndex = self.index(len(self.rootItem.childItems) - 1, 1, QtCore.QModelIndex())
        # # print(startIndex,endIndex)
        # # # self.modelReset.emit()
        # # self.dataChanged.emit(startIndex, endIndex)
        # self.dataChanged.emit(QtCore.QModelIndex(), QtCore.QModelIndex())
        # print("Start:", self.data(startIndex, Qt.ItemDataRole.DisplayRole))
        # print("End:", self.data(endIndex, Qt.ItemDataRole.DisplayRole))

    def setData(self, index: QtCore.QModelIndex, newData):
        if not index.isValid():
            print("Index is not valid in setData")
            return False
        item = index.internalPointer()
        # item.
        self.dataChanged.emit(index, index) # <---

    def add(self, process: Process):
        self.beginInsertRows(QtCore.QModelIndex(),0,4)
        topItem = TreeItem([process.name, process.status], parent=self.rootItem)
        startItem = TreeItem(["Start", process.startString], topItem)
        endItem = TreeItem(["End", ""], topItem)
        locItem = TreeItem(["Location", str(id(process))], topItem)
        resultItem = TreeItem(["Result", ""], topItem)

        topItem.appendChild(startItem).appendChild(endItem).appendChild(resultItem).appendChild(locItem)
        self.rootItem.appendChild(topItem)

        topIndex = self.index(0,0,QtCore.QModelIndex())
        topItem.setIndex(topIndex)
        topItem.updated.connect(self.emitDataChanged)

        for i, item in enumerate([startItem, endItem, resultItem, locItem]):
            item.setIndex(self.index(i, 0, topIndex))
            item.updated.connect(self.emitDataChanged)

        process.stateChanged.connect(lambda state: topItem.updateData(1, interpretState(state)))
        process.deleted.connect(lambda: topItem.updateData(1, "Deleted"))
        # topIndex = self.createIndex(row, column, childItem)

        process.finished.connect(lambda: endItem.updateData(1, generateTimestampString()))
        process.errorOccurred.connect(lambda: endItem.updateData(1, generateTimestampString()))

        process.lastLog.connect(lambda msg: resultItem.updateData(1, msg))
        process.errorOccurred.connect(lambda: resultItem.updateData(1, process.error()))
        process.error.connect(lambda msg: resultItem.updateData(1, msg))

        self.endInsertRows()
        print("Done")
