"""Select events from an .ass file and parse them into ``Line`` objects."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

import pysubs2

from .karaoke import parse_text
from .model import Line, ParseResult
from .timing import ms


def load(path: str, encoding: str = "utf-8-sig") -> pysubs2.SSAFile:
    return pysubs2.load(path, encoding=encoding, format_="ass")


def wrap_style(subs: pysubs2.SSAFile) -> int:
    try:
        return int(subs.info.get("WrapStyle", 0))
    except ValueError:
        return 0


def select_reason(event: pysubs2.SSAEvent) -> str | None:
    """None if the event should be converted, otherwise why it is skipped."""
    effect = event.effect.strip().lower()
    if event.type == "Dialogue":
        return "Dialogue with Effect=fx" if effect == "fx" else None
    if event.type == "Comment":
        return None if effect == "karaoke" else "Comment"
    return event.type


def parse_subs(subs: pysubs2.SSAFile, styles: Iterable[str] | None = None) -> ParseResult:
    wanted = set(styles) if styles else None
    wrap = wrap_style(subs)
    lines: list[Line] = []
    tag_counts: Counter = Counter()
    skipped: Counter = Counter()
    warnings: list[str] = []
    missing_styles: set[str] = set()

    for event_no, ev in enumerate(subs.events, 1):
        reason = select_reason(ev)
        if reason is None and wanted is not None and ev.style not in wanted:
            reason = "style not selected"
        if reason is not None:
            skipped[reason] += 1
            continue
        start, end = ms(ev.start), ms(ev.end)
        if end <= start:
            skipped["zero or negative length"] += 1
            warnings.append(f"event #{event_no}: end <= start, skipped")
            continue
        if ev.style not in subs.styles:
            missing_styles.add(ev.style)
        tp = parse_text(ev.text, start, end, wrap)
        tag_counts.update(tp.tags)
        lines.append(Line(
            event_no=event_no,
            event_type=ev.type,
            style=ev.style,
            start=start,
            end=end,
            text=tp.text,
            syllables=tp.syllables,
            has_karaoke=tp.has_karaoke,
            alignment=tp.alignment,
            pos=tp.pos,
            margins=(ev.marginl, ev.marginr, ev.marginv),
            tags=tp.tags,
            warnings=tp.warnings,
        ))
    for name in sorted(missing_styles):
        warnings.append(f"style {name!r} is not defined; 'Default' (or the first style) is used")
    return ParseResult(lines, tag_counts, skipped, warnings)
