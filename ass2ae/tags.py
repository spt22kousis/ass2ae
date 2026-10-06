"""Override-block splitting, tag tokenizing and text escapes, following libass.

References (libass master): ass_render.c (text loop), ass_parse.c
(``ass_parse_tags``, ``ass_get_next_char``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from .model import NEWLINE

# Tag names in the order libass tests them. Matching is by prefix against the
# chunk between the backslash and the next "(" or "\", so order matters
# ("fscx" before "fs", "an" before "a", "kt"/"kf" before "k").
LIBASS_TAGS = (
    "xbord", "ybord", "xshad", "yshad", "fax", "fay", "iclip", "blur",
    "fscx", "fscy", "fsc", "fsp", "fs", "bord", "move", "frx", "fry", "frz",
    "fr", "fn", "alpha", "an", "a", "pos", "fade", "fad", "org", "t", "clip",
    "c", "1c", "2c", "3c", "4c", "1a", "2a", "3a", "4a", "r", "be", "b", "i",
    "kt", "kf", "K", "ko", "k", "shad", "s", "u", "pbo", "p", "q", "fe",
)

KARAOKE_TAGS = ("k", "K", "kf", "ko")
INLINE_FX = "-"  # karaskel's \-xxx inline-fx tag (ignored by renderers)
NBSP = " "

_NUM_RE = re.compile(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")


@dataclass(frozen=True)
class Tag:
    name: str  # entry of LIBASS_TAGS, INLINE_FX, or the raw chunk if unknown
    arg: str  # text after the name, up to "(" or "\"
    args: tuple[str, ...]  # parenthesised arguments
    raw: str
    known: bool


@dataclass(frozen=True)
class Segment:
    kind: str  # "text" or "tags"
    raw: str  # raw text, or the block content without braces
    tags: tuple[Tag, ...] = ()


def argtod(s: str) -> Fraction | None:
    """strtod-like: parse the leading number of ``s`` exactly, None if there is none."""
    m = _NUM_RE.match(s)
    if not m:
        return None
    return Fraction(m.group(1))


def _match_name(chunk: str) -> tuple[str, str, bool]:
    if chunk.startswith(INLINE_FX):
        return INLINE_FX, chunk[1:], True
    for name in LIBASS_TAGS:
        if chunk.startswith(name):
            return name, chunk[len(name):], True
    m = re.match(r"[A-Za-z0-9]*", chunk)
    name = m.group(0) or chunk
    return name, chunk[len(name):], False


def parse_override(block: str) -> list[Tag]:
    """Tokenize the inside of one {...} block the way ass_parse_tags does.

    Text that is not part of a tag (e.g. a {comment}) is ignored.
    """
    tags: list[Tag] = []
    n = len(block)
    i = 0
    while i < n:
        j = block.find("\\", i)
        if j < 0:
            break
        p = j + 1
        while p < n and block[p] in " \t":
            p += 1
        q = p
        while q < n and block[q] not in "(\\":
            q += 1
        if q == p:
            i = q
            continue
        chunk = block[p:q]
        args: list[str] = []
        if q < n and block[q] == "(":
            q += 1
            while True:
                while q < n and block[q] in " \t":
                    q += 1
                r = q
                while r < n and block[r] not in ",\\)":
                    r += 1
                if r < n and block[r] == ",":
                    args.append(block[q:r])
                    q = r + 1
                    continue
                if r < n and block[r] == "\\":
                    # backslash argument (\t(...\fs20)): swallow up to the ")"
                    paren = block.find(")", r)
                    r = paren if paren >= 0 else n
                args.append(block[q:r])
                q = r
                if q < n:
                    q += 1
                break
        name, arg, known = _match_name(chunk)
        tags.append(Tag(name, arg, tuple(args), block[j:q], known))
        i = q
    return tags


def split_segments(text: str) -> list[Segment]:
    """Split an event's text into plain-text runs and override blocks.

    libass only opens a block at "{" when a "}" follows; otherwise "{" is text.
    Escapes are kept raw here (see ``convert_text``), but a "\\{" escape never
    opens a block.
    """
    segs: list[Segment] = []
    buf: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "{":
            close = text.find("}", i + 1)
            if close >= 0:
                if buf:
                    segs.append(Segment("text", "".join(buf)))
                    buf = []
                inner = text[i + 1:close]
                segs.append(Segment("tags", inner, tuple(parse_override(inner))))
                i = close + 1
                continue
        if c == "\\" and i + 1 < n and text[i + 1] in "Nnh{}":
            buf.append(text[i:i + 2])
            i += 2
            continue
        buf.append(c)
        i += 1
    if buf:
        segs.append(Segment("text", "".join(buf)))
    return segs


def convert_text(raw: str, wrap_style: int) -> str:
    """Apply libass ass_get_next_char conversions to a plain-text run.

    \\N -> newline; \\n -> newline under WrapStyle 2, otherwise a space;
    \\h -> U+00A0; \\{ \\} -> literal braces; tab -> space.
    """
    out: list[str] = []
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if c == "\t":
            out.append(" ")
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            d = raw[i + 1]
            if d == "N" or (d == "n" and wrap_style == 2):
                out.append(NEWLINE)
                i += 2
                continue
            if d == "n":
                out.append(" ")
                i += 2
                continue
            if d == "h":
                out.append(NBSP)
                i += 2
                continue
            if d in "{}":
                out.append(d)
                i += 2
                continue
        out.append(c)
        i += 1
    return "".join(out)


def legacy_alignment_to_numpad(val: int) -> int:
    """Convert a VSFilter \\a value (1-11) to \\an numbering, with libass's quirks."""
    if (val & 3) == 0:  # illegal \a4 / \a8 behave like \a5
        val = 5
    col = val & 3  # 1 left, 2 center, 3 right
    if val & 4:
        return 6 + col  # top row
    if val & 8:
        return 3 + col  # middle row
    return col
