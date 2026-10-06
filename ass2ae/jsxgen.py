"""Build the data object and embed it into the ES3 runtime."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from fractions import Fraction
from importlib import resources

import pysubs2

from . import __version__
from .fonts import FontFace, FontIndex
from .layout import color_rgb, get_style, placement, play_res, scaled_border
from .model import NEWLINE, Line, ParseResult, Syllable
from .timing import DEFAULT_FPS, frame_ceil, frame_to_time, layer_span

MARK = "[ass2ae]"
PLACEHOLDER = "/*@@DATA@@*/null"

# Expression Selector "Amount" (from SPEC.md): sweeps each syllable's characters
# evenly across the syllable's marker duration.
AMOUNT_EXPRESSION = """var acc = 0, amt = 0;
for (var k = 1; k <= marker.numKeys; k++) {
  var m = marker.key(k), n = m.comment.length;
  if (textIndex <= acc + n) {
    var s = m.time + m.duration * (textIndex - acc - 1) / n;
    amt = linear(time, s, s + m.duration / n, 0, 100);
    break;
  }
  acc += n;
}
amt;"""

STYLE_MODES = ("template", "ass")


@dataclass
class Options:
    fps: Fraction = DEFAULT_FPS
    offset: Fraction = Fraction(0)
    width: int | None = None
    height: int | None = None
    comp_name: str | None = None
    style_mode: str = "template"
    template: str = "KARA_TEMPLATE"
    with_animator: bool = True
    sung_color: list[float] | None = None
    newline_counts: bool = False
    font_scale: float = 0.7
    font_map: dict[str, str] = field(default_factory=dict)


def _num(x: Fraction | float | int) -> float | int:
    if isinstance(x, int):
        return x
    f = float(x)
    return int(f) if f.is_integer() else f


def marker_comment(text: str, newline_counts: bool) -> str:
    return text.replace(NEWLINE, "\r") if newline_counts else text.replace(NEWLINE, "")


def _furi_flags(f) -> str:
    return "<" if f.spillback else ("!" if f.isbreak else "")


def marker_params(syl: Syllable, line: Line, offset: Fraction) -> dict[str, str]:
    """Extra data stored with MarkerValue.setParameters (all values are strings)."""
    furi = [[f.text, _num(f.start + offset), _num(f.duration), _furi_flags(f)] for f in syl.furi]
    return {
        "kind": ",".join(h.kind or "" for h in syl.highlights),
        "tag": ",".join(h.tag or "" for h in syl.highlights),
        "cs": ",".join(str(_num(h.cs)) for h in syl.highlights),
        "furi": json.dumps(furi, ensure_ascii=False, separators=(",", ":")),
        "event": str(line.event_no),
        "fx": syl.inline_fx,
    }


def layer_name(n: int, text: str, length: int = 8) -> str:
    snippet = text.replace(NEWLINE, " ").replace(" ", " ").strip()[:length]
    return f"KARA_{n:04d}_{snippet}"


def _face_metrics(face: FontFace) -> dict:
    return {"em": round(face.em_ratio, 6), "asc": round(face.ascent / face.upm, 6),
            "desc": round(face.descent / face.upm, 6), "source": "fontTools"}


def style_data(name: str, st: pysubs2.SSAStyle, subs: pysubs2.SSAFile, opts: Options,
               fonts: FontIndex, font_metrics: dict, warnings: list[str]) -> dict:
    candidates = []
    face = fonts.find(st.fontname, st.bold, st.italic)
    if face:
        candidates.append({"ps": face.ps_name, "source": "fontTools"})
        font_metrics[face.ps_name] = _face_metrics(face)
    mapped = opts.font_map.get(st.fontname)
    if mapped:
        candidates.append({"ps": mapped, "source": "font-map"})
        mface = fonts.by_ps_name(mapped)
        if mface:
            font_metrics[mapped] = _face_metrics(mface)
    for label, c in (("PrimaryColour", st.primarycolor), ("SecondaryColour", st.secondarycolor),
                     ("OutlineColour", st.outlinecolor)):
        if c.a != 0:
            warnings.append(f"style {name}: {label} alpha {c.a:02X} is ignored (AE text colours are opaque)")
    if st.underline or st.strikeout:
        warnings.append(f"style {name}: underline/strikeout are not supported")
    if st.borderstyle == 3:
        warnings.append(f"style {name}: BorderStyle 3 (opaque box) is not supported; using an outline")
    if st.shadow:
        warnings.append(f"style {name}: Shadow is not converted")
    weight = face.weight if face else 400
    return {
        "family": st.fontname,
        "bold": bool(st.bold),
        "italic": bool(st.italic),
        "fauxBold": bool(st.bold) and weight < 600,
        "fauxItalic": bool(st.italic) and not (face and face.italic),
        "fonts": candidates,
        "size": _num(st.fontsize),
        "fill": color_rgb(st.secondarycolor),
        "stroke": color_rgb(st.outlinecolor),
        "sung": color_rgb(st.primarycolor),
        "outline": _num(st.outline),
        "scaledBorder": scaled_border(subs),
        "scaleX": _num(st.scalex),
        "scaleY": _num(st.scaley),
        "spacing": _num(st.spacing),
    }


def build_data(subs: pysubs2.SSAFile, result: ParseResult, opts: Options, source: str,
               fonts: FontIndex | None = None) -> dict:
    fonts = fonts or FontIndex()
    res = play_res(subs)
    width = opts.width or res[0]
    height = opts.height or res[1]
    warnings: list[str] = list(result.warnings)
    font_metrics: dict = {}

    styles: dict[str, dict] = {}
    lines_out: list[dict] = []
    max_t = Fraction(0)
    n = 0
    for line in result.lines:
        in_p, out_p = layer_span(line.start, line.end, opts.fps, opts.offset)
        if out_p <= in_p:
            warnings.append(f"event #{line.event_no}: shorter than one frame at this fps, skipped")
            continue
        n += 1
        st = get_style(subs, line.style)
        if line.style not in styles:
            styles[line.style] = style_data(line.style, st, subs, opts, fonts, font_metrics, warnings)
        place = placement(line, st, res)
        markers = []
        for syl in line.syllables:
            comment = marker_comment(syl.text, opts.newline_counts)
            if not comment:
                continue
            markers.append({"t": _num(syl.start + opts.offset), "d": _num(syl.duration), "c": comment,
                            "p": marker_params(syl, line, opts.offset)})
            max_t = max(max_t, syl.end + opts.offset)
        for w in line.warnings:
            warnings.append(f"event #{line.event_no}: {w}")
        if in_p < 0:
            warnings.append(f"event #{line.event_no}: starts before comp time 0")
        max_t = max(max_t, out_p)
        lines_out.append({
            "n": n,
            "event": line.event_no,
            "style": line.style,
            "name": layer_name(n, line.text),
            "comment": f"{MARK} line={n:04d} event={line.event_no} style={line.style}",
            "text": line.text.replace(NEWLINE, "\r"),
            "inPoint": _num(in_p),
            "outPoint": _num(out_p),
            "inFrame": frame_ceil(line.start + opts.offset, opts.fps),
            "outFrame": frame_ceil(line.end + opts.offset, opts.fps),
            "alignment": place.alignment,
            "justify": place.justify,
            "x": _num(place.x),
            "y": _num(place.y),
            "positioned": place.positioned,
            "angle": _num(st.angle),
            "markers": markers,
        })

    duration = frame_to_time(frame_ceil(max_t + 1, opts.fps), opts.fps)
    return {
        "tool": f"ass2ae {__version__}",
        "source": source,
        "mark": MARK,
        "playRes": list(res),
        "comp": {
            "name": opts.comp_name or source.rsplit(".", 1)[0],
            "width": width,
            "height": height,
            "fps": float(opts.fps),
            "fpsText": str(opts.fps),
            "duration": _num(duration),
        },
        "options": {
            "styleMode": opts.style_mode,
            "template": opts.template,
            "withAnimator": opts.with_animator,
            "newlineCounts": opts.newline_counts,
            "fontScale": opts.font_scale,
            "sungColor": opts.sung_color,
        },
        "amountExpression": AMOUNT_EXPRESSION,
        "fontMetrics": font_metrics,
        "styles": styles,
        "lines": lines_out,
        "warnings": warnings,
    }


def runtime_source() -> str:
    return resources.files("ass2ae").joinpath("runtime.jsx").read_text(encoding="utf-8")


def render(data: dict) -> str:
    """The JSX text. ensure_ascii turns every non-ASCII character into \\uXXXX,
    which also escapes U+2028/U+2029 (invalid in pre-ES2019 string literals)."""
    blob = json.dumps(data, ensure_ascii=True, allow_nan=False, indent=1)
    src = runtime_source()
    if PLACEHOLDER not in src:
        raise RuntimeError("runtime.jsx has no data placeholder")
    out = src.replace(PLACEHOLDER, blob)
    if not out.isascii():
        raise RuntimeError("generated JSX is not pure ASCII")
    return out

