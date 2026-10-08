"""Run JSX in After Effects (Windows: AfterFX.exe -r) and wait for its results.

    python tools/ae/run_in_ae.py probe        # API probe -> tools/ae/out/probe_api.json
    python tools/ae/run_in_ae.py fixtures     # convert the fixtures, run them in AE, verify
    python tools/ae/run_in_ae.py fixtures --only kk_ass snooze_full   # the slow full-song cases
    python tools/ae/run_in_ae.py e2e          # build through the GUI, reopen, check the markers

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
    # real files (skipped when ass_example/ is absent); snooze_short.ass is a cut of snooze.ass
    ("snooze_template", "ass_example/snooze_short.ass", {"style_mode": "template", "sung_color": "#FF0000"}, "template"),
    ("snooze_ass", "ass_example/snooze_short.ass", {"style_mode": "ass", "sung_color": "&HFF7600&", "fps": "60"}, "new"),
    # full songs take minutes each: only run when named with --only
    ("kk_ass", "ass_example/kk.ass", {"style_mode": "ass", "sung_color": "#FF0000"}, "new"),
    ("snooze_full", "ass_example/snooze.ass", {"style_mode": "ass", "sung_color": "&HFF7600&", "fps": "60"}, "new"),
]
SLOW = {"kk_ass", "snooze_full"}


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


def furi_overlaps(line: dict, layers: dict) -> list[str]:
    """Furigana boxes of one line that overlap on the same text row (unrotated lines only)."""
    if line.get("angle"):
        return []
    boxes = []
    for g in line.get("furi", []):
        layer = layers.get(g["name"])
        if layer:
            (x0, y0), (x1, y1) = layer["comp"]["topLeft"][:2], layer["comp"]["bottomRight"][:2]
            boxes.append((x0, x1, (y0 + y1) / 2, y1 - y0, g["name"]))
    boxes.sort()
    errs = []
    for a, b in zip(boxes, boxes[1:]):
        same_row = abs(a[2] - b[2]) < min(a[3], b[3]) / 2
        if same_row and b[0] < a[1] - 2:  # ink may touch: 2 px tolerance
            errs.append(f"{a[4]} and {b[4]} overlap by {a[1] - b[0]:.1f} px")
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
        if result.get("comp") and run.get("activeAfter") != result["comp"]["name"]:
            errs.append(f"run {i + 1}: viewer shows {run.get('activeAfter')!r} afterwards, not the comp")
    if result.get("leftovers"):
        errs.append(f"temporary viewer comps left in the project: {result['leftovers']}")
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
        errs += furi_overlaps(line, layers)
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
        if (args.only and name not in args.only) or (not args.only and name in SLOW):
            continue
        if not (ROOT / fixture).is_file():
            print(f"{name}: {fixture} not found, skipped")
            continue
        data, jsx = build_case(name, fixture, opts)
        built[name] = data
        renders = [m["t"] + m["d"] / 2 for line in data["lines"] for m in line["markers"][:1]][:2]
        cases.append({"name": name, "jsx": str(jsx), "mode": mode, "runs": 2, "renderTimes": renders,
                      "duration": data["comp"]["duration"]})
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
        times = " + ".join(f"{r.get('seconds', 0):.0f}s" for r in result.get("runs", []))
        print(f"{c['name']}: {status} (runs {times})")
        for e in errs[:30]:
            print(f"   - {e}")
        failed += bool(errs)
    return 1 if failed else 0


# ----------------------------------------------------------------------- e2e

REOPEN = """(function () {
    var CFG = %s;
    $.evalFile(CFG.lib);
    var T = AETEST;
    var res = { layers: [] };
    try {
        var cur = app.project.file;
        if (!cur || cur.fsName.toLowerCase() !== File(CFG.aep).fsName.toLowerCase()) {
            throw new Error("the open project is not " + CFG.aep + " (it is " + (cur ? cur.fsName : "untitled") + ")");
        }
        app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);
        app.open(new File(CFG.aep));
        var comp = null;
        for (var i = 1; i <= app.project.numItems; i++) {
            var it = app.project.item(i);
            if (it instanceof CompItem && it.name === CFG.comp) { comp = it; }
        }
        if (!comp) { throw new Error("comp " + CFG.comp + " not found after reopening"); }
        for (var l = 1; l <= comp.numLayers; l++) {
            var layer = comp.layer(l);
            if (layer.comment.substr(0, 8) !== "[ass2ae]") { continue; }
            var mk = layer.property("ADBE Marker"), ms = [];
            for (var k = 1; k <= mk.numKeys; k++) {
                var v = mk.keyValue(k);
                ms.push({ t: mk.keyTime(k), d: v.duration, c: v.comment, params: v.getParameters() });
            }
            res.layers.push({ name: layer.name, parent: layer.parent ? layer.parent.name : null, markers: ms });
        }
    } catch (e) {
        res.error = e.toString();
    }
    T.writeText(CFG.out, T.toJson(res));
    T.writeText(CFG.done, "ok");
})();
"""


def drive_gui(ass: Path, video: Path, aep: Path, exe: str | None) -> dict:
    """Fill in the GUI and press its button in-process; returns what the GUI reported."""
    from ass2ae import gui

    state: dict = {"dialogs": []}
    for name in ("showwarning", "showerror", "showinfo"):  # record dialogs instead of blocking
        setattr(gui.messagebox, name, lambda title, msg, _n=name: state["dialogs"].append(f"{_n}: {msg}"))
    app = gui.App()
    app.ass.set(str(ass))
    app._load_styles(ass)
    app.video.set(str(video))
    app.aep.set(str(aep))
    app.aep_edited = True
    if exe:
        app.afterfx.set(exe)
    finish = app._finish

    def on_finish(res, job):
        state.update(res=res, job=job)
        finish(res, job)

    app._finish = on_finish

    def watch():
        if app.running:
            state["started"] = True
        elif state.get("started") or state["dialogs"]:
            state["status"] = app.status.cget("text")
            state["log"] = app.log.get("1.0", "end").strip()
            app.destroy()
            return
        app.after(500, watch)

    app.after(300, app.run_button.invoke)
    app.after(800, watch)
    app.mainloop()
    return state


def cmd_e2e(args) -> int:
    from ass2ae import project

    if project.afterfx_running():
        sys.exit("close After Effects first: the GUI opens a new project, and AE would ask about unsaved changes")
    OUT.mkdir(exist_ok=True)
    aep = OUT / "e2e.aep"
    if aep.exists():
        aep.unlink()
    t0 = time.time()
    state = drive_gui(ROOT / args.ass, ROOT / args.video, aep, args.afterfx)
    print(f"GUI: {state.get('status')} ({time.time() - t0:.0f}s)")
    print("\n".join("   | " + line for line in state.get("log", "").splitlines()))
    for d in state["dialogs"]:
        print(f"   dialog {d}")
    res, job = state.get("res"), state.get("job")
    if not (res and res.ok and res.saved):
        return 1

    # reopen the saved project and check that every marker kept its parameters
    out, done = OUT / "e2e_reopen.json", OUT / "e2e_reopen.done"
    cfg = {"lib": str(HERE / "lib.jsx"), "aep": str(aep), "comp": res.summary["comp"], "out": str(out), "done": str(done)}
    script = OUT / "e2e_reopen.jsx"
    script.write_text(REOPEN % json.dumps(cfg, ensure_ascii=True), encoding="ascii")
    run_jsx(script, done, timeout=args.timeout)
    got = json.loads(out.read_text(encoding="utf-8"))
    if got.get("error"):
        print(f"reopen: {got['error']}")
        return 1
    layers = {l["name"]: l for l in got["layers"]}
    expected = [(line, None) for line in job.data["lines"]]
    expected += [(g, line["name"]) for line in job.data["lines"] for g in line["furi"]]
    errs = []
    frame = 1 / job.data["comp"]["fps"]
    for item, parent in expected:
        layer = layers.get(item["name"])
        if not layer:
            errs.append(f"missing layer {item['name']}")
            continue
        if layer["parent"] != parent:
            errs.append(f"{item['name']}: parent {layer['parent']!r}")
        have = layer["markers"]
        if [m["c"] for m in have] != [m["c"] for m in item["markers"]]:
            errs.append(f"{item['name']}: marker comments differ")
            continue
        for want, m in zip(item["markers"], have):
            if m["params"] != want["p"]:
                errs.append(f"{item['name']}: params {m['params']!r} != {want['p']!r}")
            if abs(m["t"] - want["t"]) > max(frame / 1000, 1e-4):
                errs.append(f"{item['name']}: marker {want['c']!r} at {m['t']}, expected {want['t']}")
    n_markers = sum(len(l["markers"]) for l in got["layers"])
    print(f"reopen: {len(got['layers'])} layers, {n_markers} markers: " + ("OK" if not errs else f"{len(errs)} problem(s)"))
    for e in errs[:30]:
        print(f"   - {e}")
    return 1 if errs else 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Japanese text, also when redirected to a file
        stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe")
    f = sub.add_parser("fixtures")
    f.add_argument("--only", nargs="*")
    f.add_argument("--timeout", type=float, default=900)
    e = sub.add_parser("e2e", help="build a project through the GUI, then reopen it and check the markers")
    e.add_argument("--ass", default="ass_example/snooze_short.ass")
    e.add_argument("--video", default="ass_example/snooze.mp4")
    e.add_argument("--afterfx")
    e.add_argument("--timeout", type=float, default=600)
    args = p.parse_args()
    return {"probe": cmd_probe, "fixtures": cmd_fixtures, "e2e": cmd_e2e}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
