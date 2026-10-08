"""Project builder (driver script, AE discovery, completion polling) without running AE."""
import json
import os
import time
from pathlib import Path

import pytest

from ass2ae import project
from ass2ae.jsxgen import Options

from .conftest import FIXTURES
from .test_es3 import HAVE_ACORN, NODE, check


@pytest.fixture
def job(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    video = tmp_path / "song.mp4"
    video.write_bytes(b"")
    return project.prepare(FIXTURES / "furigana_hash.ass", video, tmp_path / "out" / "song.aep",
                           Options(style_mode="ass"))


def driver_config(job) -> dict:
    src = job.driver.read_text(encoding="ascii")
    start = src.index("var CFG = ") + len("var CFG = ")
    return json.loads(src[start:src.index(";\n", start)])


def test_prepare_writes_lyrics_and_driver(job):
    assert job.lyrics.is_file() and job.driver.is_file()
    assert job.work.parent.name == "runs"
    cfg = driver_config(job)
    assert cfg["video"] == str(job.video) and cfg["aep"] == str(job.aep)
    assert cfg["lyrics"] == str(job.lyrics) and cfg["status"] == str(job.status)
    assert cfg["compName"] == "song"
    assert cfg["lyricsEnd"] == max(l["outPoint"] for l in job.data["lines"])
    assert job.driver.read_text(encoding="ascii").isascii()


@pytest.mark.skipif(not (NODE and HAVE_ACORN), reason="node + acorn not installed")
def test_driver_is_es3(job):
    r = check(job.driver)
    assert r.returncode == 0, r.stderr


def test_poll_reads_status(job):
    job.started = time.time()
    assert project.poll(job) is None
    job.aep.parent.mkdir(parents=True, exist_ok=True)
    job.aep.write_bytes(b"aep")
    job.status.write_text(json.dumps({"ok": True, "stage": "done", "warnings": ["w"],
                                      "summary": {"layers": 7, "furigana": 9, "markers": 20}}), encoding="utf-8")
    res = project.poll(job)
    assert res.ok and res.saved and res.summary["furigana"] == 9 and res.warnings == ["w"]


def test_poll_reports_errors(job):
    job.started = time.time()
    job.status.write_text(json.dumps({"ok": False, "stage": "import video", "error": "bad", "warnings": []}),
                          encoding="utf-8")
    res = project.poll(job)
    assert not res.ok and res.error == "bad" and res.stage == "import video" and not res.saved


def test_poll_without_status_file_uses_saved_project(job):
    job.started = time.time() - 30
    job.aep.parent.mkdir(parents=True, exist_ok=True)
    job.aep.write_bytes(b"aep")
    old = time.time() - 10
    os.utime(job.aep, (old, old))
    res = project.poll(job, grace=5)
    assert res.ok and res.saved and not res.status_written


def test_poll_ignores_an_older_project(job):
    job.aep.parent.mkdir(parents=True, exist_ok=True)
    job.aep.write_bytes(b"old")
    old = time.time() - 3600
    os.utime(job.aep, (old, old))
    job.started = time.time()
    assert project.poll(job) is None


@pytest.mark.parametrize("path,year", [
    (r"C:\Program Files\Adobe\Adobe After Effects 2025\Support Files\AfterFX.exe", 2025),
    (r"C:\Program Files\Adobe\Adobe After Effects CC 2019\Support Files\AfterFX.exe", 2019),
    (r"C:\Program Files\Adobe\Adobe After Effects (Beta)\Support Files\AfterFX.exe", None),
])
def test_ae_year(path, year):
    assert project.ae_year(path) == year


def test_find_afterfx_prefers_newest(tmp_path, monkeypatch):
    for name in ("Adobe After Effects 2024", "Adobe After Effects 2025", "Adobe After Effects CC 2019"):
        exe = tmp_path / "Adobe" / name / "Support Files" / "AfterFX.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"")
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    found = [p for p in project.find_afterfx() if str(p).startswith(str(tmp_path))]
    assert [project.ae_year(p) for p in found] == [2025, 2024, 2019]


def test_cli_style_mode_defaults_to_ass_with_video(monkeypatch, tmp_path):
    from ass2ae import cli

    seen = {}

    def fake_build(args, opts, styles):
        seen["mode"] = opts.style_mode
        return 0

    monkeypatch.setattr(cli, "build_project", fake_build)
    assert cli.main([str(FIXTURES / "en_spaces.ass"), "--video", str(tmp_path / "v.mp4")]) == 0
    assert seen["mode"] == "ass"
    assert cli.main([str(FIXTURES / "en_spaces.ass"), "--video", "v.mp4", "--style-mode", "template"]) == 0
    assert seen["mode"] == "template"
    out = tmp_path / "x.jsx"
    assert cli.main([str(FIXTURES / "en_spaces.ass"), "-o", str(out), "-q", "--no-font-scan"]) == 0
    assert '"styleMode": "template"' in out.read_text(encoding="ascii")


def test_frozen_entry_point_exists():
    assert (Path(__file__).resolve().parent.parent / "tools" / "build" / "ass2ae_app.py").is_file()


def test_launch_starts_afterfx_before_sending_the_script(job, monkeypatch):
    # cold-started with -r, AE quits after the script, so AE is started on its own first
    calls, ready = [], iter([False, False, True])
    monkeypatch.setattr(project, "afterfx_pids", lambda: [1] if calls else [])
    monkeypatch.setattr(project, "afterfx_ready", lambda: next(ready))
    monkeypatch.setattr(project, "spawn", calls.append)
    monkeypatch.setattr(project.time, "sleep", lambda s: None)
    project.launch(job, "AfterFX.exe")
    assert calls == [["AfterFX.exe"], ["AfterFX.exe", "-r", str(job.driver)]]
    assert job.started > 0


def test_launch_reuses_a_running_afterfx(job, monkeypatch):
    calls = []
    monkeypatch.setattr(project, "afterfx_pids", lambda: [42])
    monkeypatch.setattr(project, "spawn", calls.append)
    project.launch(job, "AfterFX.exe")
    assert calls == [["AfterFX.exe", "-r", str(job.driver)]]


def test_afterfx_pids_parses_tasklist(monkeypatch):
    out = '"AfterFX.exe","21332","Console","32","1,045,764 K"\r\n"AfterFX.exe","7","Console","32","9 K"\r\n'
    monkeypatch.setattr(project.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": out})())
    assert project.afterfx_pids() == [21332, 7]
    out = "INFO: No tasks are running which match the specified criteria.\r\n"
    assert project.afterfx_pids() == []
