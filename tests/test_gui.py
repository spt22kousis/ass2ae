"""GUI checks that need no window."""
import tkinter as tk

from ass2ae import gui


def test_app_does_not_shadow_tkinter_names():
    # App._options once hid tkinter's Misc._options, which every file, colour and message
    # dialog calls: the buttons silently did nothing in the windowed exe
    overrides = {"report_callback_exception"}
    clash = [n for n in vars(gui.App) if n in dir(tk.Tk) and not n.startswith("__") and n not in overrides]
    assert clash == []


def test_both_colours_reach_the_options():
    app = gui.App()
    try:
        app.use_style_colour.set(False)
        app.unsung.set("#00FF00")
        app.sung.set("#FF0000")
        opts, _styles = app._job_options()
        assert opts.unsung_color == [0, 1, 0] and opts.sung_color == [1, 0, 0]
        app.use_style_colour.set(True)
        opts, _styles = app._job_options()
        assert opts.unsung_color is None and opts.sung_color is None
    finally:
        app.destroy()
