import sys,os, flet as ft

#control = widget
# controls can contain other controls

#refs are basically forward declarations for controls - you can create a variable and have it store a ref.
# #you set the ref to a control later, and then the ref can be used to access the control.
# #this is useful for things like buttons, where you want to be able to access the button later to change its text or something
#access later with [ref name].current.[field] = [new value]
# #for example, if you want to change the text of a button, you can do something like this:
# #button_ref.current.text = "New text"
#on_click adds a handler
# page.update() batches changes and only updates things that have changed
# has some builtin icons - ft.IconButton(ft.icons.[icon name])
#can use autofocus to set focus to a control automatically and to move from one to the other

#if displaying a large list/grid of items, use listview/gridview to improve performance

#import fonts:
# https://flet.dev/docs/controls/page/#fonts


# def buttonClicked(e):
#     page.add(ft.Text("Clicked!"))
#
# # can also add keyboard shortcuts to controls
# def onKeyboard(e: ft.KeyboardEvent):
#     page.add(
#         ft.Text(
#             f"Key: {e.key}, Shift: {e.shift}, Control: {e.ctrl}, Alt: {e.alt}, Meta: {e.meta}"
#         )
#     )
# page.on_keyboard_event = onKeyboard # bind the on_keyboard function to the page
#
# t = ft.Text(value="Hello, world!", color="green")
# page.controls.append(t)
# page.add(ft.ElevatedButton(text="Click me", on_click=lambda a:page.add(ft.Text("Clicked!"))))     #page.add is a shortcut for page.controls.append and page.update in one line

# schedule box is a vertical container with the schedule title, a container holding each entry of the schedule, and a control box at the bottom containing buttons "Export" "Analyze" "Undo", and a trash icon button

# here's an example of a flet ElevatedButton with a blue background and white text:









def main(page: ft.Page):
    # using flet ("ft"), python port of flutter
    # colors
    blue = ft.colors.BLUE_600
    red = ft.colors.RED_400
    green = ft.colors.GREEN_400
    orange = ft.colors.ORANGE_800
    yellow = ft.colors.YELLOW_400
    white = ft.colors.WHITE

    page.bgcolor = white
    # styles
    titleText = lambda t,c: ft.Text(t, color=c, style=ft.TextThemeStyle.DISPLAY_MEDIUM, weight=ft.FontWeight.BOLD)
    headerText = lambda t,c: ft.Text(t, color=c, style=ft.TextThemeStyle.HEADLINE_LARGE, weight=ft.FontWeight.BOLD)
    bodyText = lambda t,c: ft.Text(t, color=c, style=ft.TextThemeStyle.BODY_LARGE, weight=ft.FontWeight.NORMAL)
    buttonStyle = lambda c: ft.ButtonStyle(color=ft.colors.WHITE,bgcolor=c)

    def containerize(content):
        return ft.Container(content)
    titleBox = ft.Row(
        controls=[
            titleText("The Scheduler", blue),
            containerize(ft.ElevatedButton(text="Import Folder", style=buttonStyle(blue))),
            ft.ElevatedButton(text="Help", style=buttonStyle(blue)),
            ft.ElevatedButton(text="Credits", style=buttonStyle(blue)),
            ft.ElevatedButton(text="Settings", style=buttonStyle(blue)),
        ],
        spacing=20
    )
    # page.add(titleBox)

    #use a container to add a border to titleBox:
    titleBoxContainer = ft.Container(titleBox, border=ft.border.all(2, blue), border_radius = ft.border_radius.all(5), margin=ft.margin.all(10), padding=ft.padding.all(10))
    page.add(titleBoxContainer)
    scheduleList = ft.ListView(expand=True, controls=[(bodyText("No Data",blue))], spacing=10)
    scheduleButtonRow = ft.Row(
        controls=[
                   ft.ElevatedButton(text="Export", style=buttonStyle(green)),
                   ft.ElevatedButton(text="Analyze", style=buttonStyle(blue)),
                   ft.ElevatedButton(text="Undo", style=buttonStyle(yellow)),
                   ft.ElevatedButton(text="Delete", style=buttonStyle(red))
                ],
                spacing=20
            )

    col = ft.Column(spacing=20, controls= [containerize(headerText("Schedule", blue)),containerize(scheduleList), containerize(scheduleButtonRow)])
    scheduleContainer = ft.Container(col, border=ft.border.all(2, blue), border_radius=10, margin=10, padding=10)
    # scheduleBox = ft.container(content=ft.Column(
    #     controls=[
    #         headerText("Schedule", blue),
    #         scheduleList,
    #         scheduleButtonRow
    #     ],
    #     alignment=ft.MainAxisAlignment.START,
    #     spacing=20
    # ))
    # page.add(scheduleBox)

    # page.add(scheduleContainer)

    # to the right of scheduleBox is a box called "Choose Next" that displays a horizontal list of possible observations, with a button to place each one
    chooseNextList = ft.ListView(expand=True, controls=[bodyText("Missing Data",blue)], spacing=10)
    chooseNextBox = ft.Column(
        controls=[
            containerize(headerText("Choose Next", blue)),
            containerize(chooseNextList)
        ],spacing=20
    )
    chooseNextContainer = ft.Container(chooseNextBox, border=ft.border.all(2, blue), border_radius=10, margin=10, padding=10)

    # the loadedFiles box is a vertical container to the right of schedule box with the title "Loaded Files" and a list of the files loaded into the program, half as tall as the other boxes
    loadedFiles = ft.ListView(expand=True, data=[], spacing=10)
    loadedFilesBox = ft.Column(
        controls=[
            headerText("Loaded Files", blue),
            loadedFiles
        ]
    )

    # the loaded objects box is below the loaded files box, with the title "Loaded Objects" and a list of the objects loaded from the files
    loadedObjects = ft.ListView(expand=True, data=[], spacing=10)
    loadedObjectsBox = ft.Column(
        controls=[
            headerText("Loaded Objects", blue),
            loadedObjects
        ]
    )

    loadedBox = ft.Column(controls=[loadedFilesBox, loadedObjectsBox])

    # page.add(chooseNextContainer)

    # page.add(loadedFilesBox)

    # page.add(loadedBox)
    # the windowsBox is a horizontal grid with the next observation window on the left and the candidate observation window on the right, then to the right is the loaded objects box at the top and the loaded files box at the bottom

    windowsRow = ft.Row(expand=True, controls=[scheduleContainer, chooseNextContainer], spacing=10)
    windowsBox = ft.Container(windowsRow, border=ft.border.all(2, blue), border_radius=10, margin=10, padding=10)
    page.add(windowsBox)

    page.update()


ft.app(target=main)
#running from command line like as follows allows hot reloading
os.system('flet run firstFlet.py -d')
