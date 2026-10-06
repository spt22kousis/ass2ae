"""Styles, colours and positions: ASS script coordinates -> comp coordinates."""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

import pysubs2

from .model import Line


def play_res(subs: pysubs2.SSAFile) -> tuple[int, int]:
    """PlayResX/Y with libass's defaults for missing values."""
    def _int(key: str) -> int:
        try:
            return int(float(subs.info.get(key, 0)))
        except ValueError:
            return 0

    x, y = _int("PlayResX"), _int("PlayResY")
    if not x and not y:
        return 384, 288
    if not y:
        y = 1024 if x == 1280 else max(1, x * 3 // 4)
    elif not x:
        x = 1280 if y == 1024 else max(1, y * 4 // 3)
    return x, y


def scaled_border(subs: pysubs2.SSAFile) -> bool:
    return str(subs.info.get("ScaledBorderAndShadow", "")).strip().lower() == "yes"


def get_style(subs: pysubs2.SSAFile, name: str) -> pysubs2.SSAStyle:
    """libass falls back to "Default" (then the first style) for unknown names."""
    if name in subs.styles:
        return subs.styles[name]
    if "Default" in subs.styles:
        return subs.styles["Default"]
    if subs.styles:
        return next(iter(subs.styles.values()))
    return pysubs2.SSAStyle()


# --- colours -------------------------------------------------------------------

def color_rgb(c: pysubs2.Color) -> list[float]:
    """AE colour array (0..1). pysubs2 has already split &HAABBGGRR into r, g, b, a."""
    return [round(c.r / 255, 6), round(c.g / 255, 6), round(c.b / 255, 6)]


def color_opacity(c: pysubs2.Color) -> float:
    """ASS alpha 00 is opaque, FF transparent."""
    return round((255 - c.a) / 255, 6)


_HEX6 = re.compile(r"#?([0-9A-Fa-f]{6})")
_ASS = re.compile(r"&H([0-9A-Fa-f]{1,8})&?", re.I)


def parse_color(text: str) -> list[float]:
    """"#RRGGBB" / "RRGGBB" (web order) or "&HBBGGRR&" / "&HAABBGGRR" (ASS order)."""
    s = text.strip()
    m = _ASS.fullmatch(s)
    if m:
        v = int(m.group(1), 16)
        r, g, b = v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF
    else:
        m = _HEX6.fullmatch(s)
        if not m:
            raise ValueError(f"bad colour {text!r}; use #RRGGBB or &HBBGGRR&")
        v = int(m.group(1), 16)
        r, g, b = (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF
    return [round(r / 255, 6), round(g / 255, 6), round(b / 255, 6)]


# --- position ------------------------------------------------------------------

JUSTIFY = {1: "left", 2: "center", 0: "right"}  # by alignment % 3


@dataclass
class Placement:
    alignment: int  # numpad 1..9
    x: Fraction  # alignment point in script coordinates
    y: Fraction
    positioned: bool  # True when it came from \pos

    @property
    def justify(self) -> str:
        return JUSTIFY[self.alignment % 3]

    @property
    def vertical(self) -> str:
        return "bottom" if self.alignment <= 3 else "top" if self.alignment >= 7 else "middle"


def placement(line: Line, style: pysubs2.SSAStyle, res: tuple[int, int]) -> Placement:
    """Where libass puts the alignment point of the text box."""
    an = line.alignment or int(style.alignment)
    if not 1 <= an <= 9:
        an = 2
    if line.pos is not None:
        return Placement(an, line.pos[0], line.pos[1], True)
    ml = line.margins[0] or style.marginl
    mr = line.margins[1] or style.marginr
    mv = line.margins[2] or style.marginv
    rx, ry = res
    col = an % 3
    if col == 1:
        x = Fraction(ml)
    elif col == 0:
        x = Fraction(rx - mr)
    else:
        x = Fraction(ml + rx - mr, 2)
    if an <= 3:
        y = Fraction(ry - mv)
    elif an >= 7:
        y = Fraction(mv)
    else:
        y = Fraction(ry, 2)
    return Placement(an, x, y, False)
