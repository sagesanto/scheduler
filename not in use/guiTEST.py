import sys

from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton

app = QApplication(sys.argv)
window = QWidget()
window.setWindowTitle('Schedule Builder')

events = ['Event 1', 'Event 2', 'Event 3', 'Event 4', 'Event 5']
selected_events = {}

layout = QVBoxLayout(window)
events_layout = QHBoxLayout()
event_list_widget = QListWidget()
event_list_widget.addItems(events)
add_button = QPushButton('Add')
remove_button = QPushButton('Remove')
schedule_list_widget = QListWidget()
add_button.clicked.connect(lambda: [schedule_list_widget.addItem(item.text()) or selected_events.update({item.text(): True}) for item in event_list_widget.selectedItems()])
remove_button.clicked.connect(lambda: [schedule_list_widget.takeItem(schedule_list_widget.row(item)) or selected_events.pop(item.text(), None) for item in schedule_list_widget.selectedItems()])
events_layout.addWidget(event_list_widget)
events_layout.addWidget(add_button)
events_layout.addWidget(remove_button)
layout.addLayout(events_layout)
layout.addWidget(schedule_list_widget)

window.show()
sys.exit(app.exec_())