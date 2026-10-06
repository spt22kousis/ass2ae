"""Optional font lookup with fontTools: ASS (GDI) family name -> PostScript name + metrics.

Only used to give the JSX a PostScript-name candidate and to convert the ASS
font size (ascent+descent, libass/VSFilter semantics) into an AE em size.
Everything degrades gracefully when fontTools is missing or the font is not found.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

FONT_EXTS = {".ttf", ".otf", ".ttc", ".otc"}
INDEX_VERSION = 2


@dataclass
class FontFace:
    path: str
    index: int  # face index inside a collection
    ps_name: str
    families: list[str]  # nameID 1 (GDI family) in every language, plus VF instance names
    full_names: list[str]  # nameID 4
    typo_families: list[str]  # nameID 16
    subfamily: str  # nameID 17 or 2 (English)
    weight: int
    italic: bool
    upm: int
    ascent: int  # GDI-style ascent/descent used by libass for the font size
    descent: int
    instance: str = ""  # variable-font named instance subfamily, if any

    @property
    def em_ratio(self) -> float:
        """AE em size per unit of ASS font size."""
        return self.upm / (self.ascent + self.descent)


@dataclass
class FontIndex:
    faces: list[FontFace] = field(default_factory=list)

    def find(self, name: str, bold: bool = False, italic: bool = False) -> FontFace | None:
        key = name.strip().lower()
        for attr in ("families", "full_names", "typo_families"):
            cands = [f for f in self.faces if key in (n.lower() for n in getattr(f, attr))]
            if cands:
                return _pick_style(cands, bold, italic)
        cands = [f for f in self.faces if f.ps_name.lower() == key]
        return cands[0] if cands else None

    def by_ps_name(self, ps_name: str) -> FontFace | None:
        key = ps_name.lower()
        for f in self.faces:
            if f.ps_name.lower() == key:
                return f
        return None


def _pick_style(cands: list[FontFace], bold: bool, italic: bool) -> FontFace:
    want_w = 700 if bold else 400

    def score(f: FontFace):
        return (f.italic != italic, abs(f.weight - want_w), f.instance != "")

    return min(cands, key=score)


def default_font_dirs() -> list[Path]:
    dirs: list[Path] = []
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        dirs.append(Path(windir) / "Fonts")
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    elif sys.platform == "darwin":
        dirs += [Path("/System/Library/Fonts"), Path("/Library/Fonts"), Path.home() / "Library" / "Fonts"]
    else:
        dirs += [Path("/usr/share/fonts"), Path.home() / ".fonts", Path.home() / ".local/share/fonts"]
    return [d for d in dirs if d.is_dir()]


def _cache_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "ass2ae" / "font-index.json"


def _names(name_table, name_id: int) -> list[str]:
    out = []
    for rec in name_table.names:
        if rec.nameID == name_id:
            try:
                s = rec.toUnicode().strip()
            except Exception:
                continue
            if s and s not in out:
                out.append(s)
    return out


def _english(name_table, name_id: int) -> str:
    rec = name_table.getName(name_id, 3, 1, 0x409) or name_table.getName(name_id, 1, 0, 0)
    if rec is None:
        names = _names(name_table, name_id)
        return names[0] if names else ""
    return rec.toUnicode().strip()


def _metrics(font) -> tuple[int, int]:
    """libass set_font_metrics: OS/2 win values, else typo, else hhea."""
    os2 = font["OS/2"] if "OS/2" in font else None
    if os2 is not None:
        a = _s16(os2.usWinAscent)
        d = _s16(os2.usWinDescent)
        if a + d != 0:
            return a, d
        if os2.sTypoAscender - os2.sTypoDescender != 0:
            return os2.sTypoAscender, -os2.sTypoDescender
    hhea = font["hhea"]
    return hhea.ascent, -hhea.descent


def _s16(v: int) -> int:
    return v - 0x10000 if v >= 0x8000 else v


def _read_faces(path: Path) -> list[FontFace]:
    from fontTools.ttLib import TTCollection, TTFont

    faces: list[FontFace] = []
    if path.suffix.lower() in (".ttc", ".otc"):
        fonts = list(enumerate(TTCollection(str(path), lazy=True).fonts))
    else:
        fonts = [(0, TTFont(str(path), lazy=True))]
    for idx, font in fonts:
        try:
            name = font["name"]
            os2 = font["OS/2"] if "OS/2" in font else None
            weight = os2.usWeightClass if os2 is not None else 400
            italic = bool(os2.fsSelection & 1) if os2 is not None else False
            ascent, descent = _metrics(font)
            base = FontFace(
                path=str(path), index=idx, ps_name=_english(name, 6),
                families=_names(name, 1), full_names=_names(name, 4),
                typo_families=_names(name, 16) or _names(name, 1),
                subfamily=_english(name, 17) or _english(name, 2),
                weight=weight, italic=italic, upm=font["head"].unitsPerEm,
                ascent=ascent, descent=descent)
            faces.append(base)
            if "fvar" in font:
                for inst in font["fvar"].instances:
                    sub = name.getDebugName(inst.subfamilyNameID) or ""
                    ps = name.getDebugName(inst.postscriptNameID) if inst.postscriptNameID not in (0, 0xFFFF) else None
                    fams = base.typo_families
                    ps = ps or (fams[0].replace(" ", "") + "-" + sub.replace(" ", "") if fams else "")
                    wght = int(inst.coordinates.get("wght", weight))
                    faces.append(FontFace(
                        path=str(path), index=idx, ps_name=ps,
                        families=[f"{fam} {sub}" for fam in fams] + ([] if sub not in ("Regular", "Italic") else fams),
                        full_names=[f"{fam} {sub}" for fam in fams], typo_families=fams,
                        subfamily=sub, weight=wght, italic="Italic" in sub, upm=base.upm,
                        ascent=ascent, descent=descent, instance=sub))
        except Exception:
            continue
        finally:
            font.close()
    return faces


def build_index(extra_dirs: list[str] | None = None, use_cache: bool = True) -> FontIndex:
    """Scan font directories (cached by path, size and mtime)."""
    try:
        import fontTools  # noqa: F401
    except ImportError:
        return FontIndex()
    cache_file = _cache_path()
    cache: dict = {}
    if use_cache and cache_file.is_file():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if data.get("version") == INDEX_VERSION:
                cache = data["files"]
        except (OSError, ValueError, KeyError):
            cache = {}
    dirs = [Path(d) for d in (extra_dirs or [])] + default_font_dirs()
    files: dict = {}
    faces: list[FontFace] = []
    for d in dirs:
        for p in sorted(d.rglob("*")):
            if p.suffix.lower() not in FONT_EXTS or not p.is_file():
                continue
            st = p.stat()
            stamp = [st.st_size, int(st.st_mtime)]
            entry = cache.get(str(p))
            if entry and entry["stamp"] == stamp:
                file_faces = [FontFace(**f) for f in entry["faces"]]
            else:
                try:
                    file_faces = _read_faces(p)
                except Exception:
                    file_faces = []
            files[str(p)] = {"stamp": stamp, "faces": [asdict(f) for f in file_faces]}
            faces.extend(file_faces)
    if use_cache:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps({"version": INDEX_VERSION, "files": files}), encoding="utf-8")
        except OSError:
            pass
    return FontIndex(faces)
