from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QPushButton, QFileDialog


class FileSelectionButton(QPushButton):
    chosen = pyqtSignal()

    def __init__(self, parent=None, default=None):
        super().__init__(parent)
        self.pattern = None
        self.prompt = None
        self.clicked.connect(self.chooseFile)
        self.path = None
        self.default = default
        self.dir = False

    def setText(self, text: str):  # if we don't have default text, make the first time our text is set the default
        if self.default is None:
            self.default = text
        super().setText(text)

    def updateFilePath(self, path):
        self.path = path
        self.setNameFromPath(path)

    def setNameFromPath(self, path):
        self.setText(path.split("/")[
                         -1])  # this was originally split by os.sep (\ on windows) but it seems to always come in with /

    def getPath(self): return self.path

    def setPrompt(self, prompt):
        self.prompt = prompt
        return self

    def setPattern(self, pattern):
        self.pattern = pattern
        return self

    def isDirectoryDialog(self,dir:bool):
        self.dir = dir

    def chooseFile(self):
        if self.dir:
            filepath = QFileDialog.getExistingDirectory(self, self.prompt)
        else:
            filepath = QFileDialog.getOpenFileName(self, self.prompt, self.path or "./", self.pattern)[
                           0]
        #         filepath = QFileDialog.getOpenFileName(self, 'Select Database File', "./", "Database File (*.db)")[
        #                        0] or self.default
        filepath = (self.default if self.path is None else self.path) if not filepath else filepath
        self.updateFilePath(filepath)
        print("Filepath:", filepath)
        self.chosen.emit()
