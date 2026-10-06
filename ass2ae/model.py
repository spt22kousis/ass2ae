"""Data model shared by the parser and the JSX generator.

All times are absolute ASS times in seconds, as ``fractions.Fraction``.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction

# \K is the same effect as \kf; markers keep the normalised kind, the raw tag is kept too.
K_KIND = {"k": "k", "K": "kf", "kf": "kf", "ko": "ko"}

NEWLINE = "\n"  # how \N (and \n under WrapStyle 2) is stored in display text


@dataclass
class Highlight:
    """One \\k unit as written (a syllable can own several through # continuations)."""

    tag: str | None  # "k", "K", "kf", "ko"; None for text before the first \k
    cs: Fraction  # raw value as written, in centiseconds
    start: Fraction
    duration: Fraction  # after truncation to the line end

    @property
    def kind(self) -> str | None:
        return K_KIND[self.tag] if self.tag else None


@dataclass
class Furi:
    """Furigana text with its own timing (karaskel semantics)."""

    text: str
    start: Fraction
    duration: Fraction
    isbreak: bool = False  # "!" or "<" prefix
    spillback: bool = False  # "<" prefix


@dataclass
class Syllable:
    text: str  # display text, exactly as it appears in the layer text
    start: Fraction
    duration: Fraction
    highlights: list[Highlight] = field(default_factory=list)
    furi: list[Furi] = field(default_factory=list)
    inline_fx: str = ""

    @property
    def end(self) -> Fraction:
        return self.start + self.duration


@dataclass
class Line:
    event_no: int  # 1-based row in [Events], same as Aegisub's grid number
    event_type: str  # "Dialogue" or "Comment"
    style: str
    start: Fraction
    end: Fraction
    text: str  # display text of the whole line
    syllables: list[Syllable]  # only syllables that become markers
    has_karaoke: bool
    alignment: int | None = None  # \an (or converted \a) override, None = use style
    pos: tuple[Fraction, Fraction] | None = None
    margins: tuple[int, int, int] = (0, 0, 0)  # event MarginL/R/V, 0 = use style
    tags: Counter = field(default_factory=Counter)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParseResult:
    lines: list[Line]
    tag_counts: Counter
    skipped: Counter  # reason -> count
    warnings: list[str]  # file-level warnings
