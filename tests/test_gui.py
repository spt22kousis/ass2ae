"""GUI checks that need no window."""
import tkinter as tk

from ass2ae import gui


def test_app_does_not_shadow_tkinter_names():
    # App._options once hid tkinter's Misc._options, which every file, colour and message
    # dialog calls: the buttons silently did nothing in the windowed exe
    overrides = {"report_callback_exception"}
    clash = [n for n in vars(gui.App) if n in dir(tk.Tk) and not n.startswith("__") and n not in overrides]
    assert clash == []
