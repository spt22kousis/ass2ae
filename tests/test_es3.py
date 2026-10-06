"""Generated JSX must parse as ECMAScript 3 (acorn) and avoid ES5+ APIs.

Needs node and `npm install` in tests/js; skipped otherwise.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

from ass2ae.jsxgen import Options, render

from .test_jsxgen import FIXTURE_NAMES, generate

JS_DIR = Path(__file__).resolve().parent / "js"
NODE = shutil.which("node")
HAVE_ACORN = (JS_DIR / "node_modules" / "acorn").is_dir() and (JS_DIR / "node_modules" / "acorn-walk").is_dir()

pytestmark = pytest.mark.skipif(not (NODE and HAVE_ACORN), reason="node + acorn not installed (npm install in tests/js)")


def check(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run([NODE, str(JS_DIR / "check_es3.js"), str(path)], capture_output=True, text=True)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
@pytest.mark.parametrize("opts", [Options(), Options(style_mode="ass", with_animator=False, newline_counts=True)],
                         ids=["default", "ass-mode"])
def test_generated_jsx_is_es3(name, opts, tmp_path):
    out = tmp_path / "out.jsx"
    out.write_text(render(generate(name, opts)), encoding="ascii")
    r = check(out)
    assert r.returncode == 0, r.stderr


def test_checker_rejects_es5(tmp_path):
    bad = tmp_path / "bad.jsx"
    bad.write_text("var a = [1, 2].map(function (x) { return x; });\n")
    assert check(bad).returncode != 0
    bad.write_text("let a = 1;\n")
    assert check(bad).returncode != 0
