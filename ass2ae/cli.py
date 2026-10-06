"""Command line: python -m ass2ae input.ass -o out.jsx [options]"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .fonts import FontIndex, build_index
from .jsxgen import STYLE_MODES, Options, build_data, render
from .layout import parse_color
from .parser import load, parse_subs
from .timing import parse_fps, parse_offset


def read_font_map(path: str) -> dict[str, str]:
    """JSON object {"ASS family": "PostScriptName"} or lines "ASS family=PostScriptName"."""
    text = Path(path).read_text(encoding="utf-8-sig")
    if text.lstrip().startswith("{"):
        data = json.loads(text)
        return {str(k): str(v) for k, v in data.items()}
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}: expected 'Family=PostScriptName', got {raw!r}")
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m ass2ae",
        description="Convert Aegisub karaoke (.ass with \\k tags) into an After Effects JSX that creates "
                    "one text layer per line and one layer marker per syllable.")
    p.add_argument("input", help=".ass file")
    p.add_argument("-o", "--output", help="output .jsx (default: next to the input)")
    p.add_argument("--styles", action="append", metavar="A,B",
                   help="only convert these styles (comma separated, repeatable)")
    p.add_argument("--fps", default="24000/1001",
                   help="comp frame rate: 24000/1001 (default), 23.976, 29.97, 30 ...")
    p.add_argument("--offset", default="0",
                   help="comp time of ASS 0:00:00.00: seconds, h:mm:ss.xx or frames like 48f (default 0)")
    p.add_argument("--width", type=int, help="new comp width (default PlayResX)")
    p.add_argument("--height", type=int, help="new comp height (default PlayResY)")
    p.add_argument("--comp-name", help="name of a newly created comp (default: input file name)")
    p.add_argument("--style-mode", choices=STYLE_MODES, default="template",
                   help="template: duplicate the KARA_TEMPLATE text layer; ass: build styling from ASS styles")
    p.add_argument("--template", default="KARA_TEMPLATE",
                   help="template layer name; <name>_<Style> is tried first (default KARA_TEMPLATE)")
    p.add_argument("--with-animator", action=argparse.BooleanOptionalAction, default=True,
                   help="add a fill-colour Text Animator driven by the markers (default on)")
    p.add_argument("--no-animator", dest="with_animator", action="store_false",
                   help="same as --no-with-animator")
    p.add_argument("--sung-color", help="sung colour, #RRGGBB or &HBBGGRR& (default: style PrimaryColour)")
    p.add_argument("--newline-counts", action=argparse.BooleanOptionalAction, default=False,
                   help="include line breaks in marker comments (if AE's textIndex counts them; default off)")
    p.add_argument("--font-map", metavar="FILE",
                   help='fallback font names: JSON {"ASS family": "PostScriptName"} or Family=PostScriptName lines')
    p.add_argument("--font-scale", type=float, default=0.7,
                   help="AE font size / ASS font size when the font file cannot be read (default 0.7)")
    p.add_argument("--font-dir", action="append", default=[], metavar="DIR",
                   help="extra directory to search for font files (repeatable)")
    p.add_argument("--no-font-scan", action="store_true", help="do not look up font files with fontTools")
    p.add_argument("--encoding", default="utf-8-sig", help="input encoding (default utf-8-sig)")
    p.add_argument("--dump-json", metavar="FILE", help="also write the embedded data object as JSON")
    p.add_argument("-q", "--quiet", action="store_true", help="only print errors")
    return p


def report(result, data, out_path: str, file=sys.stderr) -> None:
    lines = data["lines"]
    markers = sum(len(l["markers"]) for l in lines)
    print(f"wrote {out_path}", file=file)
    print(f"  layers: {len(lines)} ({sum(1 for l in lines if l['markers'])} with markers)  markers: {markers}",
          file=file)
    if result.skipped:
        print("  skipped events: " + ", ".join(f"{k} {v}" for k, v in sorted(result.skipped.items())), file=file)
    if result.tag_counts:
        tags = ", ".join(f"\\{k} x{v}" for k, v in sorted(result.tag_counts.items(), key=lambda kv: -kv[1]))
        print(f"  removed tags: {tags}", file=file)
    fonts = {name: (st["fonts"][0]["ps"] if st["fonts"] else None) for name, st in data["styles"].items()}
    for name, ps in fonts.items():
        fam = data["styles"][name]["family"]
        print(f"  style {name}: {fam!r} -> {ps or 'not found (AE will look it up)'}", file=file)
    if data["warnings"]:
        print(f"  warnings ({len(data['warnings'])}):", file=file)
        for w in data["warnings"]:
            print(f"    - {w}", file=file)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.getLogger("fontTools").setLevel(logging.ERROR)
    try:
        fps = parse_fps(args.fps)
        opts = Options(
            fps=fps,
            offset=parse_offset(args.offset, fps),
            width=args.width,
            height=args.height,
            comp_name=args.comp_name,
            style_mode=args.style_mode,
            template=args.template,
            with_animator=args.with_animator,
            sung_color=parse_color(args.sung_color) if args.sung_color else None,
            newline_counts=args.newline_counts,
            font_scale=args.font_scale,
            font_map=read_font_map(args.font_map) if args.font_map else {},
        )
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    in_path = Path(args.input)
    styles = [s.strip() for chunk in args.styles or [] for s in chunk.split(",") if s.strip()] or None
    subs = load(str(in_path), args.encoding)
    result = parse_subs(subs, styles)
    fonts = FontIndex() if args.no_font_scan else build_index(args.font_dir)
    data = build_data(subs, result, opts, in_path.name, fonts)
    out_path = Path(args.output) if args.output else in_path.with_suffix(".jsx")
    out_path.write_text(render(data), encoding="ascii", newline="\n")
    if args.dump_json:
        Path(args.dump_json).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    if not args.quiet:
        report(result, data, str(out_path))
    return 0
