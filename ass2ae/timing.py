"""Frame-rate parsing and exact time arithmetic."""
from __future__ import annotations

import math
import re
from fractions import Fraction

DEFAULT_FPS = Fraction(24000, 1001)

# Integer rates whose NTSC (x1000/1001) variant is auto-detected from decimals.
_NTSC_BASES = (24, 30, 48, 60, 120)


def parse_fps(text: str) -> Fraction:
    """Parse "24000/1001", "30", "23.976", "29.97" ...

    Decimal inputs within 0.005 of an NTSC rate map to the exact x1000/1001
    fraction, so "23.976" becomes 24000/1001.
    """
    s = text.strip()
    if "/" in s:
        num, den = s.split("/", 1)
        fps = Fraction(int(num), int(den))
    else:
        fps = Fraction(s)
        if fps.denominator != 1:
            for base in _NTSC_BASES:
                ntsc = Fraction(base * 1000, 1001)
                if abs(fps - ntsc) < Fraction(5, 1000):
                    fps = ntsc
                    break
    if fps <= 0:
        raise ValueError(f"fps must be positive: {text!r}")
    return fps


def parse_offset(text: str, fps: Fraction) -> Fraction:
    """Parse an offset: seconds ("12.5"), timecode ("1:02.5", "0:01:02.50") or frames ("300f")."""
    s = text.strip()
    sign = 1
    if s.startswith("-"):
        sign, s = -1, s[1:]
    elif s.startswith("+"):
        s = s[1:]
    if s.endswith("f"):
        return sign * Fraction(int(s[:-1])) / fps
    if ":" in s:
        parts = s.split(":")
        if len(parts) > 3 or not all(re.fullmatch(r"\d+(\.\d+)?", p) for p in parts):
            raise ValueError(f"bad offset: {text!r}")
        total = Fraction(0)
        for p in parts:
            total = total * 60 + Fraction(p)
        return sign * total
    return sign * Fraction(s)


def frame_ceil(t: Fraction, fps: Fraction) -> int:
    """Index of the first frame whose timestamp is >= t."""
    return math.ceil(t * fps)


def frame_to_time(frame: int, fps: Fraction) -> Fraction:
    return Fraction(frame) / fps


def layer_span(start: Fraction, end: Fraction, fps: Fraction, offset: Fraction = Fraction(0)) -> tuple[Fraction, Fraction]:
    """In/out points in comp time.

    libass shows an event on a frame at time t when start <= t < end, so the
    first visible frame is ceil(start*fps) and the first hidden one ceil(end*fps).
    """
    in_point = frame_to_time(frame_ceil(start + offset, fps), fps)
    out_point = frame_to_time(frame_ceil(end + offset, fps), fps)
    return in_point, out_point


def ms(ms_value: int) -> Fraction:
    return Fraction(ms_value, 1000)


def fmt_time(t: Fraction) -> str:
    """h:mm:ss.xx-style rendering for messages (not exact)."""
    neg = t < 0
    t = abs(t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = float(t % 60)
    return f"{'-' if neg else ''}{h}:{m:02d}:{s:06.3f}"
