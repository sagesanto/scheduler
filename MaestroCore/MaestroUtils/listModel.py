from PyQt6.QtCore import Qt, QAbstractListModel, QModelIndex
from PyQt6.QtWidgets import QApplication, QListView
from scheduleLib.candidateDatabase import Candidate


class FlexibleListModel(QAbstractListModel):
    def __init__(self, data=None):
        super().__init__()
        self.data = data or []

    def rowCount(self, parent=None):
        return len(self.data)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            dat = self.data[index.row()]
            return dat.CandidateName if isinstance(dat, Candidate) else dat

        return None

    def addItem(self, newItem):
        self.beginInsertRows(QModelIndex(), len(self.data), len(self.data))
        self.data.append(newItem)
        self.endInsertRows()

    def selectedRows(self, view):
        selectedIndexes = view.selectedIndexes()
        return [index.row() for index in selectedIndexes]

    def removeSelectedItems(self, view):
        selectedRows = self.selectedRows(view)
        # Sort the rows in reverse order to avoid index shifting when removing items
        selectedRows.sort(reverse=True)

        for row in selectedRows:
            self.beginRemoveRows(QModelIndex(), row, row)
            del self.data[row]
            self.endRemoveRows()
