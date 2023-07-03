import os
import signal
import sys

import pandas as pd
import pytz
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QMainWindow, QFileDialog, QButtonGroup, QTableWidget, \
    QTableWidgetItem as QTableItem, QListWidget, QLineEdit, QDialog, QDialogButtonBox, QVBoxLayout, QLabel, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal, QRunnable, QObject, QThreadPool, QProcess
from PyQt6.QtGui import QIcon
from PyQt6 import QtCore, QtWidgets
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

    def __init__(self, data, parent=None, tags=None):
        super().__init__()
        self.parentItem = parent
        self.itemData = data
        self.index = None
        self.childItems = []
        self.tags = tags or {}

    def __repr__(self):
        return "Tree Item" + (": Root: " if self.parentItem is None else " ") + str(self.itemData)

    def setIndex(self, index: QtCore.QModelIndex):  # don't think this is very pythonic
        self.index = index

    def addTag(self, key, value):
        self.tags[key] = value

    def appendChild(self, item):
        self.childItems.insert(0, item)
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
    errorSignal = pyqtSignal(str)
    msg = pyqtSignal(str)
    lastLog = pyqtSignal(str)
    paused = pyqtSignal()
    resumed = pyqtSignal()
    ended = pyqtSignal(str)

    def __init__(self, name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name
        self.startLocal = datetime.now()
        self.startUTC = datetime.now(pytz.UTC)
        self.startString = generateTimestampString()
        self.result = ""  # short string or error msg
        self.end = None
        self.log = []
        self.errorLog = []
        self.isPaused = False
        self.connect()

    def connect(self):
        self.readyReadStandardError.connect(lambda: self.writeToErrorLog(decodeStdErr(self)))
        self.readyReadStandardOutput.connect(lambda: self.writeToLog(decodeStdOut(self)))
        self.finished.connect(lambda: self.lastLog.emit(self.log[-1] if len(self.log) else ""))
        self.finished.connect(self.terminate)  # this might not be necessary
        self.finished.connect(lambda exitCode: self.ended.emit("Finished" if not exitCode else "Error"))

        self.errorOccurred.connect(lambda: self.ended.emit("Error"))

    def __del__(self):
        print("Deleting process", self.name, "with PID", self.processId())
        self.ended.emit("Deleted")
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

    def pause(self):
        """
        Attempt to pause this process. If it has subprocesses of its own, pausing may not acheive complete stoppage
        """
        if not self.isPaused and self.isActive:
            print("Pausing", self.name)
            self.paused.emit()
            self.isPaused = True
            os.kill(self.processId(), signal.SIGSTOP)
            return

    def resume(self):
        if self.paused:
            print("Resuming", self.name)
            self.resumed.emit()
            self.isPaused = False
            os.kill(self.processId(), signal.SIGCONT)

    def writeToErrorLog(self, error):
        error = self.name + " encountered an error: " + error
        self.errorLog.append(error)
        self.errorSignal.emit(error)
        self.msg.emit(error)

    def writeToLog(self, content):
        self.log.append(content)
        self.logged.emit(content)
        self.msg.emit(content)

    def abort(self):
        if self.isActive:
            self.writeToErrorLog("User Abort")
            self.ended.emit("Aborted")
            self.kill()
            self.blockSignals(True)


class ProcessModel(QtCore.QAbstractItemModel):
    updated = pyqtSignal()

    def __init__(self, processes=None, parent=None, statusBar=None):
        super(ProcessModel, self).__init__(parent)
        processes = processes or []
        self.rootItem = TreeItem(("Process", "Status"))
        for process in processes:
            self.add(process)
        self.statusBar = statusBar

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

    def emitDataChanged(self, index: QtCore.QModelIndex):
        self.dataChanged.emit(index, index)

    def setData(self, index: QtCore.QModelIndex, newData):
        if index.isValid():
            item = index.internalPointer()
            item.updateData(1, newData)
            self.dataChanged.emit(index, index)  # <---

    def add(self, process: Process):
        self.beginInsertRows(QtCore.QModelIndex(), 0, 4)
        topItem = TreeItem([process.name, process.status], parent=self.rootItem, tags={"Process":process})
        startItem = TreeItem(["Start", process.startString], topItem)
        endItem = TreeItem(["End", ""], topItem)
        resultItem = TreeItem(["Result", ""], topItem)
        locItem = TreeItem(["PID", str(process.processId())], topItem)

        topItem.appendChild(locItem).appendChild(resultItem).appendChild(endItem).appendChild(startItem)
        self.rootItem.appendChild(topItem)

        topIndex = self.index(0, 0, QtCore.QModelIndex())
        topItem.setIndex(topIndex)
        topItem.updated.connect(self.emitDataChanged)

        for i, item in enumerate([startItem, endItem, resultItem, locItem]):
            item.setIndex(self.index(i, 0, topIndex))
            item.updated.connect(self.emitDataChanged)

        process.stateChanged.connect(lambda state: self.setData(locItem.index, process.processId()))
        process.stateChanged.connect(lambda state: self.setData(topItem.index, interpretState(state)))
        process.ended.connect(lambda msg: self.setData(topItem.index, msg))
        process.paused.connect(lambda: self.setData(topItem.index, "Paused"))
        process.resumed.connect(lambda state: self.setData(topItem.index, interpretState(state)))

        process.ended.connect(lambda: self.setData(endItem.index, generateTimestampString()))

        process.lastLog.connect(lambda msg: self.setData(resultItem.index, msg))
        process.errorOccurred.connect(lambda: self.setData(resultItem.index, process.error()))
        process.errorSignal.connect(lambda msg: self.setData(resultItem.index, msg))

        if self.statusBar is not None:
            process.ended.connect(lambda msg: self.statusBar.showMessage("Process '{}' ended with status '{}'".format(process.name,msg), 10000))
        self.endInsertRows()
        print("Done")


class ProcessDialog(QDialog):
    def __init__(self, windowName, process: Process, parent=None):
        super().__init__(parent)
        self.setWindowTitle(windowName)
        self.abortButton = QPushButton("Abort")
        self.layout = QVBoxLayout()
        message = QLabel("Fetching Ephemerides")
        self.progressBar = QtWidgets.QProgressBar(parent=self)
        self.layout.addWidget(message)
        self.layout.addWidget(self.progressBar)
        self.layout.addWidget(self.abortButton)
        self.setLayout(self.layout)
        self.abortButton.clicked.connect(process.abort)
        self.abortButton.clicked.connect(self.close)
        process.finished.connect(self.close)
        process.errorOccurred.connect(self.close)
