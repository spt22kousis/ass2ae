"""Build dist/ass2ae.exe with PyInstaller:  python tools/build/build_exe.py"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

args = [
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
    "--name", "ass2ae",
    "--distpath", str(ROOT / "dist"),
    "--workpath", str(ROOT / "build" / "pyinstaller"),
    "--specpath", str(ROOT / "build"),
    "--add-data", f"{ROOT / 'ass2ae' / 'runtime.jsx'};ass2ae",
    "--collect-submodules", "fontTools.ttLib.tables",
    "--exclude-module", "PIL",
    "--exclude-module", "pytest",
    str(ROOT / "tools" / "build" / "ass2ae_app.py"),
]
code = subprocess.call(args, cwd=ROOT)
if code == 0:
    shutil.copyfile(ROOT / "tools" / "build" / "使用說明.txt", ROOT / "dist" / "使用說明.txt")
sys.exit(code)
