"""Run JSX in After Effects (Windows: AfterFX.exe -r) and wait for its results.

    python tools/ae/run_in_ae.py probe        # API probe -> tools/ae/out/probe_api.json
    python tools/ae/run_in_ae.py fixtures     # convert the fixtures, run them in AE, verify

AE must allow scripts to write files:
Edit > Preferences > Scripting & Expressions > Allow Scripts to Write Files and Access Network.
If AE is not running it is started (and left running); scripts never save or close projects.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = HERE / "out"
sys.path.insert(0, str(ROOT))

DEFAULT_AFTERFX = r"C:\Program Files\Adobe\Adobe After Effects 2025\Support Files\AfterFX.exe"


def afterfx() -> str:
    exe = os.environ.get("AFTERFX", DEFAULT_AFTERFX)
    if not Path(exe).is_file():
        sys.exit(f"AfterFX.exe not found: {exe} (set AFTERFX)")
    return exe


def run_jsx(script: Path, done: Path, timeout: float = 600) -> None:
    if done.exists():
        done.unlink()
    subprocess.Popen([afterfx(), "-r", str(script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    while not done.exists():
        if time.time() - t0 > timeout:
            sys.exit(f"timed out waiting for {done.name}; is the 'Allow Scripts to Write Files' preference on?")
        time.sleep(1)
    print(f"{script.name}: finished in {time.time() - t0:.0f}s")


def js_string(s: str) -> str:
    return json.dumps(s, ensure_ascii=True)


# --------------------------------------------------------------------- probe

def cmd_probe(_args) -> int:
    OUT.mkdir(exist_ok=True)
    run_jsx(HERE / "probes" / "probe_api.jsx", OUT / "probe_api.done")
    print(f"results: {OUT / 'probe_api.json'}")
    return 0


# ------------------------------------------------------------------ fixtures

CASES = [
    # name, fixture, cli-like options, mode
    ("jp_ass", "tests/fixtures/jp_kanji_kana.ass", {"style_mode": "ass", "sung_color": "#FF0000"}, "new"),
    ("jp_template", "tests/fixtures/jp_kanji_kana.ass", {"style_mode": "template", "sung_color": "#FF0000"}, "template"),
    ("en_ass", "tests/fixtures/en_spaces.ass", {"style_mode": "ass", "sung_color": "#FF0000"}, "new"),
    ("furi_ass", "tests/fixtures/furigana_hash.ass", {"style_mode": "ass", "sung_color": "#FF0000"}, "new"),
    ("templated_ass", "tests/fixtures/templated.ass", {"style_mode": "ass", "sung_color": "#FF0000"}, "new"),
    # real files (skipped when ass_example/ is absent)
    ("kk_ass", "ass_example/kk.ass", {"style_mode": "ass", "sung_color": "#FF0000"}, "new"),
    ("snooze_template", "ass_example/snooze.ass", {"style_mode": "template", "sung_color": "#FF0000"}, "template"),
    ("snooze_ass", "ass_example/snooze.ass", {"style_mode": "ass", "sung_color": "&HFF7600&", "fps": "60"}, "new"),
]


def build_case(name: str, fixture: str, opts: dict):
    from ass2ae.fonts import build_index
    from ass2ae.jsxgen import Options, build_data, render
    from ass2ae.layout import parse_color
    from ass2ae.parser import load, parse_subs
    from ass2ae.timing import parse_fps

    o = dict(opts, comp_name=f"ass2ae_test_{name}")
    if "sung_color" in o:
        o["sung_color"] = parse_color(o["sung_color"])
    if "fps" in o:
        o["fps"] = parse_fps(o["fps"])
    subs = load(str(ROOT / fixture))
    data = build_data(subs, parse_subs(subs), Options(**o), Path(fixture).name, build_index())
    jsx = OUT / f"{name}.jsx"
    jsx.write_text(render(data), encoding="ascii", newline="\n")
    return data, jsx


def verify_furi(group: dict, line: dict, main: dict, furi: dict | None) -> list[str]:
    tag = group["name"]
    if furi is None:
        return [f"missing furigana layer {tag}"]
    errs = []
    if furi["parent"] != line["name"]:
        errs.append(f"{tag}: parent {furi['parent']!r}")
    if furi["text"] != group["text"]:
        errs.append(f"{tag}: text {furi['text']!r}")
    if [m["c"] for m in furi["markers"]] != [m["c"] for m in group["markers"]]:
        errs.append(f"{tag}: markers {[m['c'] for m in furi['markers']]}")
    for key in ("inPoint", "outPoint"):
        if abs(furi[key] - main[key]) > 1e-9:
            errs.append(f"{tag}: {key} differs from its line")
    # sits above the line and horizontally inside it
    ax, ay = furi["comp"]["anchor"][:2]
    left, top = main["comp"]["topLeft"][:2]
    right = main["comp"]["bottomRight"][0]
    if not left - 1 <= ax <= right + 1:
        errs.append(f"{tag}: x {ax:.1f} outside its line [{left:.1f}, {right:.1f}]")
    if ay > top + 1:
        errs.append(f"{tag}: bottom {ay:.1f} below the line top {top:.1f}")
    return errs


def verify(name: str, data: dict, result: dict) -> list[str]:
    errs: list[str] = []
    runs = result.get("runs", [])
    for i, run in enumerate(runs):
        if run.get("error"):
            errs.append(f"run {i + 1}: {run['error']}")
        rr = run.get("result") or {}
        for w in rr.get("aeWarnings") or []:
            errs.append(f"run {i + 1} AE warning: {w}")
    layers = {l["name"]: l for l in result.get("layers", []) if l.get("generated")}
    expected = len(data["lines"]) + sum(len(l.get("furi", [])) for l in data["lines"])
    if len(layers) != expected:
        errs.append(f"{len(layers)} generated layers after {len(runs)} runs, expected {expected}")
    for keep in result.get("mustSurvive", []):
        if keep not in [l["name"] for l in result.get("layers", [])]:
            errs.append(f"layer {keep!r} was removed")
    for line in data["lines"]:
        layer = layers.get(line["name"])
        if not layer:
            errs.append(f"missing layer {line['name']}")
            continue
        tag = line["name"]
        for group in line.get("furi", []):
            errs += verify_furi(group, line, layer, layers.get(group["name"]))
        if layer["comment"] != line["comment"]:
            errs.append(f"{tag}: comment {layer['comment']!r}")
        if abs(layer["startTime"]) > 1e-9:
            errs.append(f"{tag}: startTime {layer['startTime']}")
        frame = 1 / result["comp"]["frameRate"]
        tol = max(frame / 1000, 1e-4)
        for key, fkey in (("inPoint", "inFrame"), ("outPoint", "outFrame")):
            if abs(layer[key] / frame - line[fkey]) > 0.01:
                errs.append(f"{tag}: {key} {layer[key]} is not frame {line[fkey]}")
        if layer["text"] != line["text"]:
            errs.append(f"{tag}: text {layer['text']!r} != {line['text']!r}")
        got = layer["markers"]
        if len(got) != len(line["markers"]):
            errs.append(f"{tag}: {len(got)} markers, expected {len(line['markers'])}")
            continue
        for want, have in zip(line["markers"], got):
            # AE rounds times to 1/(1000*fps) s and loses a little more precision after ~2 minutes
            if abs(want["t"] - have["t"]) > tol or abs(want["d"] - have["d"]) > tol:
                errs.append(f"{tag}: marker {want['c']!r} at {have['t']}+{have['d']}, expected {want['t']}+{want['d']}")
            if want["c"] != have["c"]:
                errs.append(f"{tag}: marker comment {have['c']!r} != {want['c']!r}")
            if want["p"] != have["params"]:
                errs.append(f"{tag}: params {have['params']!r} != {want['p']!r}")
        if line["markers"] and data["options"]["withAnimator"]:
            sels = layer.get("selectors") or []
            if sels != ["ADBE Text Expressible Selector"]:
                errs.append(f"{tag}: selectors {sels}")
            if layer.get("amountError"):
                errs.append(f"{tag}: expression error {layer['amountError']}")
    return errs


def cmd_fixtures(args) -> int:
    OUT.mkdir(exist_ok=True)
    cases = []
    built = {}
    for name, fixture, opts, mode in CASES:
        if args.only and name not in args.only:
            continue
        if not (ROOT / fixture).is_file():
            print(f"{name}: {fixture} not found, skipped")
            continue
        data, jsx = build_case(name, fixture, opts)
        built[name] = data
        renders = [m["t"] + m["d"] / 2 for line in data["lines"] for m in line["markers"][:1]][:2]
        cases.append({"name": name, "jsx": str(jsx), "mode": mode, "runs": 2, "renderTimes": renders})
    driver = OUT / "harness_driver.jsx"
    driver.write_text(
        "$.global.ASS2AE_HARNESS = " + json.dumps({"outDir": str(OUT), "cases": cases}, ensure_ascii=True) + ";\n"
        "$.evalFile(" + js_string(str(HERE / "harness.jsx")) + ");\n", encoding="ascii")
    for old in OUT.glob("*_[0-9]_*.png"):
        old.unlink()
    run_jsx(driver, OUT / "harness.done", timeout=args.timeout)
    failed = 0
    for c in cases:
        result = json.loads((OUT / f"{c['name']}.result.json").read_text(encoding="utf-8"))
        errs = verify(c["name"], built[c["name"]], result)
        status = "OK" if not errs else f"{len(errs)} problem(s)"
        print(f"{c['name']}: {status}")
        for e in errs[:30]:
            print(f"   - {e}")
        failed += bool(errs)
    return 1 if failed else 0


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe")
    f = sub.add_parser("fixtures")
    f.add_argument("--only", nargs="*")
    f.add_argument("--timeout", type=float, default=900)
    args = p.parse_args()
    return {"probe": cmd_probe, "fixtures": cmd_fixtures}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
