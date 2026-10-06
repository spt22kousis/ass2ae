"""Split one event's text into display text and karaoke syllables.

Syllable splitting follows Aegisub's AssKaraoke (what karaskel sees through
``aegisub.parse_karaoke_data``); furigana and "#" continuations follow
karaskel-auto4.lua ``preproc_line_text``.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction

from .model import Furi, Highlight, Syllable
from .tags import INLINE_FX, KARAOKE_TAGS, argtod, convert_text, legacy_alignment_to_numpad, split_segments
from .timing import fmt_time

_SPACE_SPLIT = re.compile(r"([ \t]*)(.*?)([ \t]*)\Z", re.S)
_HASH = ("#", "＃")  # "#" and fullwidth "＃"
_PIPE_FW = "｜"  # fullwidth "｜"
_FURI_BREAK = ("!", "！")
_FURI_SPILL = ("<", "＜")


class InvariantError(AssertionError):
    pass


@dataclass
class _Raw:
    tag: str | None
    cs: Fraction
    start: Fraction
    duration: Fraction
    text: str = ""
    inline_fx: str = ""


@dataclass
class TextParse:
    text: str
    syllables: list[Syllable]
    has_karaoke: bool
    alignment: int | None = None
    pos: tuple[Fraction, Fraction] | None = None
    tags: Counter = field(default_factory=Counter)
    warnings: list[str] = field(default_factory=list)


def parse_text(text: str, start: Fraction, end: Fraction, wrap_style: int = 0) -> TextParse:
    """Parse an event's Text field. ``start``/``end`` are the event times in seconds."""
    res = TextParse("", [], False)
    raws = _split_raw(text, start, wrap_style, res)
    if not res.has_karaoke:
        res.text = "".join(r.text for r in raws)
        res.warnings.extend(check_chars(res.text))
        return res
    grouped, line_text = _group(raws, res.warnings)
    res.text = line_text
    res.syllables = _finalize(grouped, end, res.warnings)
    check_invariants(line_text, res.syllables)
    res.warnings.extend(check_chars(line_text))
    return res


def _k_value(tag, warnings: list[str]) -> Fraction:
    src = tag.arg if tag.arg.strip() or not tag.args else tag.args[0]
    val = argtod(src)
    if val is None:
        warnings.append(f"{tag.raw} has no duration, treated as 0")
        return Fraction(0)
    if val < 0:
        warnings.append(f"{tag.raw} is negative, treated as 0")
        return Fraction(0)
    return val


def _split_raw(text: str, start: Fraction, wrap_style: int, res: TextParse) -> list[_Raw]:
    raws: list[_Raw] = []
    cur = _Raw(None, Fraction(0), start, Fraction(0))
    cur_fx = ""
    wrap = wrap_style
    moved = False
    block_no = 0
    for seg in split_segments(text):
        if seg.kind == "text":
            cur.text += convert_text(seg.raw, wrap)
            continue
        block_no += 1
        for tag in seg.tags:
            if tag.name in KARAOKE_TAGS:
                res.has_karaoke = True
                cs = _k_value(tag, res.warnings)
                cur.inline_fx = cur_fx
                # AssKaraoke drops syllables that have neither duration nor text
                if cur.duration > 0 or cur.text:
                    raws.append(cur)
                cur = _Raw(tag.name, cs, cur.start + cur.duration, cs / 100)
                continue
            res.tags[tag.name if tag.known else "?" + tag.name] += 1
            if tag.name == INLINE_FX:
                cur_fx = tag.arg
            elif tag.name == "kt":
                res.warnings.append(f"{tag.raw} (absolute karaoke timing) is not supported and was ignored")
            elif tag.name == "q":
                val = argtod(tag.arg)
                wrap = int(val) if val is not None and 0 <= val <= 3 else wrap_style
            elif tag.name in ("an", "a"):
                if res.alignment is None:
                    val = argtod(tag.arg)
                    ival = int(val) if val is not None else 0
                    if tag.name == "an":
                        res.alignment = ival if 1 <= ival <= 9 else 0
                    else:
                        res.alignment = legacy_alignment_to_numpad(ival) if 1 <= ival <= 11 else 0
                    if block_no > 1:
                        res.warnings.append(f"{tag.raw} is not in the first override block")
            elif tag.name == "pos":
                if res.pos is None and not moved and len(tag.args) == 2:
                    x, y = argtod(tag.args[0]), argtod(tag.args[1])
                    if x is not None and y is not None:
                        res.pos = (x, y)
                        if block_no > 1:
                            res.warnings.append(f"{tag.raw} is not in the first override block")
            elif tag.name == "move":
                if res.pos is None and not moved:
                    moved = True
                    res.warnings.append(f"{tag.raw} is not supported; using the static position")
    cur.inline_fx = cur_fx
    raws.append(cur)
    if res.alignment == 0:  # invalid value: libass falls back to the style
        res.alignment = None
    return raws


def _group(raws: list[_Raw], warnings: list[str]) -> tuple[list[Syllable], str]:
    """karaskel: strip spaces, handle "#" continuations and "|" furigana."""
    syls: list[Syllable] = []
    for r in raws:
        pre, body, post = _SPACE_SPLIT.match(r.text).groups()
        cont = body[:1] in _HASH and bool(syls)
        furi = None
        if "|" in body or _PIPE_FW in body:
            body = body.replace(_PIPE_FW, "|")
            body, ftext = body.split("|", 1)
            isbreak = spill = False
            if ftext[:1] in _FURI_BREAK:
                isbreak, ftext = True, ftext[1:]
            elif ftext[:1] in _FURI_SPILL:
                isbreak, spill, ftext = True, True, ftext[1:]
            furi = Furi(ftext, r.start, r.duration, isbreak, spill)
        hl = Highlight(r.tag, r.cs, r.start, r.duration)
        if cont:
            prev = syls[-1]
            prev.duration += r.duration
            prev.highlights.append(hl)
            if furi:
                prev.furi.append(furi)
            dropped = pre + body[1:] + post
            if dropped:
                warnings.append(f"text {dropped!r} after a '#' continuation is not displayed (karaskel behaviour)")
        else:
            syls.append(Syllable(pre + body + post, r.start, r.duration, [hl], [furi] if furi else [], r.inline_fx))
    return syls, "".join(s.text for s in syls)


def _clip(start: Fraction, duration: Fraction, limit: Fraction) -> Fraction:
    return max(Fraction(0), min(duration, limit - start))


def _finalize(syls: list[Syllable], line_end: Fraction, warnings: list[str]) -> list[Syllable]:
    # 1. truncate at the line end
    overrun = Fraction(0)
    truncated = 0
    for s in syls:
        if s.end > line_end:
            if s.duration > 0:
                truncated += 1
            overrun = max(overrun, s.end - line_end)
            s.duration = _clip(s.start, s.duration, line_end)
            for h in s.highlights:
                h.duration = _clip(h.start, h.duration, line_end)
            for f in s.furi:
                f.duration = _clip(f.start, f.duration, line_end)
    if truncated:
        warnings.append(f"karaoke runs {float(overrun):.3f}s past the line end ({fmt_time(line_end)}); "
                        f"{truncated} syllable(s) truncated")

    # 2. zero-duration syllables join the next timed one (the previous one at the end)
    out: list[Syllable] = []
    pending: list[Syllable] = []
    for s in syls:
        if s.duration == 0:
            pending.append(s)
            continue
        if pending:
            s.text = "".join(p.text for p in pending) + s.text
            s.highlights = [h for p in pending for h in p.highlights] + s.highlights
            s.furi = [f for p in pending for f in p.furi] + s.furi
            pending = []
        out.append(s)
    if pending:
        if not out:
            if any(p.text for p in pending):
                warnings.append("karaoke line has zero total duration; no markers")
            return []
        last = out[-1]
        last.text += "".join(p.text for p in pending)
        last.highlights += [h for p in pending for h in p.highlights]
        last.furi += [f for p in pending for f in p.furi]

    # 3. syllables without display text get no marker (times are absolute)
    return [s for s in out if s.text]


def check_invariants(line_text: str, syls: list[Syllable]) -> None:
    joined = "".join(s.text for s in syls)
    if syls and joined != line_text:
        raise InvariantError(f"syllable texts {joined!r} != line text {line_text!r}")
    for a, b in zip(syls, syls[1:]):
        if not a.start < b.start:
            raise InvariantError(f"marker times not increasing: {a.start} then {b.start}")
    for s in syls:
        if s.duration <= 0:
            raise InvariantError(f"syllable {s.text!r} has duration {s.duration}")


def check_chars(text: str) -> list[str]:
    """Characters where JS string length and AE's character count may disagree."""
    warnings = []
    astral = sorted({c for c in text if ord(c) > 0xFFFF})
    if astral:
        warnings.append("non-BMP characters " + " ".join(f"U+{ord(c):X}" for c in astral)
                        + ": JS length counts them as 2, AE may count 1")
    combining = sorted({c for c in text
                        if unicodedata.category(c) in ("Mn", "Me")
                        or 0xFE00 <= ord(c) <= 0xFE0F or c == "‍"})
    if combining:
        warnings.append("combining marks / variation selectors " + " ".join(f"U+{ord(c):04X}" for c in combining)
                        + ": AE may not count them as separate characters")
    return warnings
