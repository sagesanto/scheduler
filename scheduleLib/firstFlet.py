import sys,os, flet as ft

#control = widget
# controls can contain other controls

#refs are bassically forward declarations for controls - you can create a variable and have it store a ref. you set the ref to a control later, and then the ref can be used to access the control.
# #this is useful for things like buttons, where you want to be able to access the button later to change its text or something
#access later with [ref name].current.[field] = [new value]
# #for example, if you want to change the text of a button, you can do something like this:
# #button_ref.current.text = "New text"


def button_clicked(e):
    page.add(ft.Text("Clicked!"))

def main(page: ft.Page):
    t = ft.Text(value="Hello, world!", color="green")
    page.controls.append(t)
    page.add(ft.ElevatedButton(text="Click me", on_click=lambda:page.add(ft.Text("Clicked!"))))
    page.update()
    #page.add is a shortcut for page.controls.append and page.update in one line



ft.app(target=main)
os.system('flet run firstFlet.py -d')
