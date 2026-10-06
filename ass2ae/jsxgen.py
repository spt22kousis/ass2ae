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
    furigana: bool = True
    furi_scale: float = 0.5  # karaskel's default furigana size when there is no "<Style>-furigana"


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


_BASE_SPACE = " \t\u00a0\u3000\n"


def js_len(text: str) -> int:
    """Length in UTF-16 code units, i.e. JavaScript string indices."""
    return len(text.encode("utf-16-le")) // 2


def furi_markers(syl: Syllable, line: Line, offset: Fraction) -> list[dict]:
    """One marker per furigana part; zero-length parts join the next (or the previous) one."""
    out: list[dict] = []
    pending = ""
    for f in syl.furi:
        if not f.text:
            continue
        if f.duration <= 0:
            pending += f.text
            continue
        out.append({"t": _num(f.start + offset), "d": _num(f.duration), "c": pending + f.text,
                    "p": {"kind": "furi", "base": syl.text.strip(_BASE_SPACE), "event": str(line.event_no)}})
        pending = ""
    if pending and out:
        out[-1]["c"] += pending
    return out


def furi_groups(line: Line, n: int, style_key: str, offset: Fraction, warnings: list[str]) -> list[dict]:
    """Furigana layers for one line: text, the base range in the layer text (JS indices) and markers."""
    groups: list[dict] = []
    pos = 0
    for syl in line.syllables:
        text = "".join(f.text for f in syl.furi).replace(NEWLINE, "")
        if text:
            i, j = 0, len(syl.text)
            while i < j and syl.text[i] in _BASE_SPACE:
                i += 1
            while j > i and syl.text[j - 1] in _BASE_SPACE:
                j -= 1
            base = syl.text[i:j]
            if not base or NEWLINE in base:
                warnings.append(f"event #{line.event_no}: furigana {text!r} has no single-line base text, skipped")
            else:
                k = len(groups) + 1
                markers = furi_markers(syl, line, offset)
                groups.append({
                    "name": f"KARA_{n:04d}_F{k:02d}_{text[:6]}",
                    "comment": f"{MARK} furi line={n:04d} n={k:02d} event={line.event_no} style={style_key}",
                    "text": text,
                    "base": base,
                    "start": js_len(line.text[:pos + i]),
                    "end": js_len(line.text[:pos + j]),
                    "markers": markers,
                })
        pos += len(syl.text)
    return groups


def furi_style(name: str, subs: pysubs2.SSAFile, main: dict, opts: Options, fonts: FontIndex,
               font_metrics: dict, warnings: list[str]) -> dict:
    """"<Style>-furigana" if the script has it, else the main style scaled like karaskel does."""
    key = f"{name}-furigana"
    if key in subs.styles:
        return style_data(key, subs.styles[key], subs, opts, fonts, font_metrics, warnings)
    st = dict(main)
    for k in ("size", "outline", "spacing"):
        st[k] = _num(Fraction(str(main[k])) * Fraction(str(opts.furi_scale)))
    st["synthetic"] = True
    return st


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
        furi = []
        if opts.furigana and any(syl.furi for syl in line.syllables):
            fkey = f"{line.style}-furigana"
            if fkey not in styles:
                styles[fkey] = furi_style(line.style, subs, styles[line.style], opts, fonts, font_metrics, warnings)
            furi = furi_groups(line, n, fkey, opts.offset, warnings)
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
            "start": _num(line.start + opts.offset),
            "end": _num(line.end + opts.offset),
            "inFrame": frame_ceil(line.start + opts.offset, opts.fps),
            "outFrame": frame_ceil(line.end + opts.offset, opts.fps),
            "alignment": place.alignment,
            "justify": place.justify,
            "x": _num(place.x),
            "y": _num(place.y),
            "positioned": place.positioned,
            "angle": _num(st.angle),
            "markers": markers,
            "furiStyle": f"{line.style}-furigana" if furi else None,
            "furi": furi,
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
            "furiScale": opts.furi_scale,
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

