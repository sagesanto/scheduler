from PyQt6.QtCore import Qt, QAbstractListModel, QModelIndex
from PyQt6.QtWidgets import QApplication, QListView


class StringListModel(QAbstractListModel):
    def __init__(self, data=None):
        super().__init__()
        self._data = data or []

    def rowCount(self, parent=None):
        return len(self._data)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            return self._data[index.row()]

        return None

    def addItem(self, newItem):
        self.beginInsertRows(QModelIndex(), len(self._data), len(self._data))
        self._data.append(newItem)
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
            del self._data[row]
            self.endRemoveRows()
