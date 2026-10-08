"""Find and dismiss After Effects' modal dialogs (Windows), so unattended AE runs do not hang.

A script that ends with an AE error ("internal verification failure"), or a render queue
asking before it overwrites a file, leaves a modal dialog that blocks every later script.
The test tools close such dialogs with Enter and report their text as failures.
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

from ass2ae import project

WM_GETTEXT, WM_GETTEXTLENGTH = 0x000D, 0x000E
WM_KEYDOWN, WM_KEYUP, VK_RETURN = 0x0100, 0x0101, 0x0D


def _user32():
    return ctypes.windll.user32


def _text(hwnd) -> str:
    u = _user32()
    n = u.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
    buf = ctypes.create_unicode_buffer(n + 1)
    u.SendMessageW(hwnd, WM_GETTEXT, n + 1, buf)
    return buf.value


def _class(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _user32().GetClassNameW(hwnd, buf, 256)
    return buf.value


def _children(hwnd) -> list:
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(child, _lparam):
        out.append(child)
        return True

    _user32().EnumChildWindows(hwnd, visit, 0)
    return out


def find() -> list[int]:
    """Visible message boxes of After Effects: #32770 windows with an Edit control.

    The "Executing Script…" progress window is a #32770 too, but without an Edit control
    (pressing Enter there could stop the running script)."""
    if sys.platform != "win32":
        return []
    pids = set(project.afterfx_pids())
    u = _user32()
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _lparam):
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if (pid.value in pids and u.IsWindowVisible(hwnd) and _class(hwnd) == "#32770"
                and any(_class(c) == "Edit" for c in _children(hwnd))):
            found.append(hwnd)
        return True

    if pids:
        u.EnumWindows(visit, 0)
    return found


def describe(hwnd) -> str:
    texts = [_text(c) for c in _children(hwnd)]
    return " | ".join(t for t in texts if t and not t.startswith("OS_")) or "(text not readable)"


def dismiss(hwnd) -> bool:
    """Press Enter in the dialog (its default button). True when it closed."""
    u = _user32()
    for target in [c for c in _children(hwnd) if _class(c) == "Edit"]:
        u.PostMessageW(target, WM_KEYDOWN, VK_RETURN, 0x001C0001)
        u.PostMessageW(target, WM_KEYUP, VK_RETURN, 0xC01C0001)
        time.sleep(1.0)
        if not (u.IsWindow(hwnd) and u.IsWindowVisible(hwnd)):
            return True
    return False


def sweep() -> list[str]:
    """Dismiss every AE dialog that is up; returns what they said."""
    seen = []
    for hwnd in find():
        text = describe(hwnd)
        closed = dismiss(hwnd)
        seen.append(text if closed else text + " (could not close it)")
    return seen


if __name__ == "__main__":  # watchdog: python tools/ae/dialogs.py
    while True:
        for msg in sweep():
            print(f"{time.strftime('%T')} dismissed AE dialog: {msg}", flush=True)
        time.sleep(1)
