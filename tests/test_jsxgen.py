"""JSX generator: data object, snapshots (UPDATE_SNAPSHOTS=1 to rewrite)."""
import json
import os
from fractions import Fraction as F
from pathlib import Path

import pytest

from ass2ae.fonts import FontFace, FontIndex
from ass2ae.jsxgen import AMOUNT_EXPRESSION, PLACEHOLDER, Options, build_data, render
from ass2ae.parser import load, parse_subs

from .conftest import FIXTURES

SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"
FIXTURE_NAMES = ["jp_kanji_kana.ass", "en_spaces.ass", "furigana_hash.ass", "templated.ass"]


def generate(name, opts=None, fonts=None):
    subs = load(str(FIXTURES / name))
    return build_data(subs, parse_subs(subs), opts or Options(), name, fonts)


def embedded_data(jsx: str) -> dict:
    start = jsx.index("var DATA = ") + len("var DATA = ")
    end = jsx.index(";\n", start)
    return json.loads(jsx[start:end])


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_snapshot(name):
    jsx = render(generate(name))
    snap = SNAPSHOTS / (Path(name).stem + ".jsx")
    if os.environ.get("UPDATE_SNAPSHOTS") or not snap.exists():
        snap.parent.mkdir(exist_ok=True)
        snap.write_text(jsx, encoding="ascii", newline="\n")
        if not os.environ.get("UPDATE_SNAPSHOTS"):
            pytest.skip(f"created {snap.name}")
    assert jsx == snap.read_text(encoding="ascii")


def test_output_is_ascii_and_data_round_trips():
    data = generate("jp_kanji_kana.ass")
    jsx = render(data)
    assert jsx.isascii()
    assert PLACEHOLDER not in jsx
    assert embedded_data(jsx) == json.loads(json.dumps(data))
    assert "\\u541b" in jsx  # 君


def test_line_and_marker_data():
    data = generate("jp_kanji_kana.ass")
    first = data["lines"][0]
    assert first["name"] == "KARA_0001_君の名前は"
    assert first["comment"] == "[ass2ae] line=0001 event=1 style=JP"
    assert first["inPoint"] == float(F(24 * 1001, 24000))
    assert first["outPoint"] == float(F(72 * 1001, 24000))
    assert (first["alignment"], first["x"], first["y"], first["justify"]) == (8, 960, 100, "center")
    assert [(m["t"], m["d"], m["c"]) for m in first["markers"]] == [
        (1, 0.2, "君"), (1.2, 0.3, "の"), (1.5, 0.25, "名"), (1.75, 0.25, "前"), (2, 0.5, "は")]
    p = first["markers"][2]["p"]
    assert p == {"kind": "kf", "tag": "kf", "cs": "25", "furi": "[]", "event": "1", "fx": ""}
    assert first["markers"][4]["p"]["tag"] == "K" and first["markers"][4]["p"]["kind"] == "kf"


def test_translation_line_has_no_markers():
    data = generate("jp_kanji_kana.ass")
    zh = next(l for l in data["lines"] if l["style"] == "ZH")
    assert zh["markers"] == [] and zh["text"] == "你的名字是"


def test_markers_increase_and_have_duration():
    for name in FIXTURE_NAMES:
        for line in generate(name)["lines"]:
            times = [m["t"] for m in line["markers"]]
            assert times == sorted(set(times))
            assert all(m["d"] > 0 for m in line["markers"])
            assert "".join(m["c"] for m in line["markers"]) in ("", line["text"].replace("\r", ""))


def test_newline_handling():
    line = next(l for l in generate("jp_kanji_kana.ass")["lines"] if "\r" in l["text"])
    assert line["text"] == "上の\r下だ"
    assert [m["c"] for m in line["markers"]] == ["上", "の", "下", "だ"]
    line = next(l for l in generate("jp_kanji_kana.ass", Options(newline_counts=True))["lines"] if "\r" in l["text"])
    assert [m["c"] for m in line["markers"]] == ["上", "の\r", "下", "だ"]


def test_furigana_params():
    line = generate("furigana_hash.ass")["lines"][1]
    head = line["markers"][0]
    assert head["c"] == "頭" and head["d"] == 0.35
    assert json.loads(head["p"]["furi"]) == [["あ", 2, 0.1, "<"], ["た", 2.1, 0.12, "<"], ["ま", 2.22, 0.13, "<"]]
    assert head["p"]["cs"] == "10,12,13" and head["p"]["fx"] == "A"


def test_offset_moves_everything():
    data = generate("en_spaces.ass", Options(offset=F(10), fps=F(30)))
    first = data["lines"][0]
    assert (first["inPoint"], first["outPoint"]) == (11, 12)
    assert first["markers"][0]["t"] == 11


def test_sub_frame_line_is_skipped():
    subs = load(str(FIXTURES / "en_spaces.ass"))
    res = parse_subs(subs)
    res.lines[0].start, res.lines[0].end = F(1001, 1000), F(1002, 1000)
    data = build_data(subs, res, Options(fps=F(24)), "x.ass")
    assert len(data["lines"]) == len(res.lines) - 1
    assert any("shorter than one frame" in w for w in data["warnings"])


def test_style_colours_and_options():
    data = generate("jp_kanji_kana.ass", Options(sung_color=[1, 0, 0], style_mode="ass"))
    jp = data["styles"]["JP"]
    assert jp["fill"] == [1.0, 1.0, 1.0]  # SecondaryColour = not yet sung
    assert jp["sung"] == [1.0, 0.0, 0.0]  # PrimaryColour &H000000FF -> red
    assert jp["stroke"] == [0.0, 0.0, 0.0]
    assert jp["outline"] == 3 and jp["scaledBorder"] is True
    assert data["options"]["sungColor"] == [1, 0, 0]
    assert data["options"]["styleMode"] == "ass"
    assert data["amountExpression"] == AMOUNT_EXPRESSION
    assert data["comp"]["fpsText"] == "24000/1001" and data["playRes"] == [1920, 1080]


def test_font_candidates_and_metrics():
    face = FontFace(path="x.otf", index=0, ps_name="NotoSansJP-Regular", families=["Noto Sans JP"],
                    full_names=["Noto Sans JP"], typo_families=["Noto Sans JP"], subfamily="Regular",
                    weight=400, italic=False, upm=1000, ascent=1160, descent=288)
    opts = Options(font_map={"Noto Sans JP": "Fallback-PS", "Microsoft JhengHei": "MSJH-PS"})
    data = generate("jp_kanji_kana.ass", opts, FontIndex([face]))
    assert data["styles"]["JP"]["fonts"] == [{"ps": "NotoSansJP-Regular", "source": "fontTools"},
                                             {"ps": "Fallback-PS", "source": "font-map"}]
    assert data["fontMetrics"]["NotoSansJP-Regular"]["em"] == pytest.approx(1000 / 1448, abs=1e-6)
    assert data["styles"]["ZH"]["fonts"] == [{"ps": "MSJH-PS", "source": "font-map"}]


def test_alpha_warning():
    data = generate("templated.ass")
    assert not any("alpha" in w for w in data["warnings"])  # BackColour alpha is not used
