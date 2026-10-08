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


# --- furigana layers ---------------------------------------------------------

def test_furigana_groups():
    data = generate("furigana_hash.ass")
    line = data["lines"][1]  # 頭 で
    assert line["furiStyle"] == "K1-furigana"
    (g,) = line["furi"]
    assert (g["text"], g["base"], g["start"], g["end"]) == ("あたま", "頭", 0, 1)
    assert g["name"] == "KARA_0002_F01_あたま"
    assert g["comment"] == "[ass2ae] furi line=0002 n=01 event=2 style=K1-furigana"
    assert [(m["t"], m["d"], m["c"]) for m in g["markers"]] == [(2, 0.1, "あ"), (2.1, 0.12, "た"), (2.22, 0.13, "ま")]
    assert g["markers"][0]["p"] == {"kind": "furi", "base": "頭", "event": "2"}
    # one layer per furigana syllable, base ranges in JS string indices
    assert [(g["text"], g["start"], g["end"]) for g in data["lines"][3]["furi"]] == [("とう", 0, 1), ("きょう", 1, 2)]


def test_furigana_layout_groups():
    lines = generate("furigana_hash.ass")["lines"]

    def groups(i):
        return [(g["text"], g["lg"], g["spill"]) for g in lines[i]["furi"]]

    assert groups(0) == [("かん", 1, False), ("じ", 1, False)]  # neighbours share a layout group
    assert groups(1) == [("あたま", 1, True)]  # "<" spills back
    assert groups(3) == [("とう", 1, False), ("きょう", 2, False)]  # "!" and "！" break
    assert groups(7) == [("わたくし", 1, False), ("たち", 1, False)]
    assert groups(8) == [("わたくし", 1, False), ("たち", 2, False)]
    assert groups(9) == [("ぼくたちの", 1, True)]


def test_furigana_layout_group_breaks_at_line_break():
    subs = load(str(FIXTURES / "furigana_hash.ass"))
    subs.events[0].text = r"{\k20}漢|かん{\k20}\N字|じ"
    line = build_data(subs, parse_subs(subs), Options(), "x.ass")["lines"][0]
    assert line["text"] == "漢\r字"
    assert [(g["start"], g["end"], g["lg"]) for g in line["furi"]] == [(0, 1, 1), (2, 3, 2)]


def test_zero_length_furigana_joins_next_part():
    (g,) = generate("furigana_hash.ass")["lines"][6]["furi"]  # {\k0}漢|かん{\k20}字|じ
    assert g["text"] == "かんじ" and (g["start"], g["end"]) == (0, 2)
    assert [(m["c"], m["t"], m["d"]) for m in g["markers"]] == [("かんじ", 7, 0.2)]


def test_furigana_style_from_script_or_scaled():
    data = generate("furigana_hash.ass")
    assert data["styles"]["K1-furigana"]["size"] == 50 and "synthetic" not in data["styles"]["K1-furigana"]
    subs = load(str(FIXTURES / "furigana_hash.ass"))
    del subs.styles["K1-furigana"]
    data = build_data(subs, parse_subs(subs), Options(), "x.ass")
    st = data["styles"]["K1-furigana"]
    assert st["synthetic"] and st["size"] == 50 and st["outline"] == 1.5


def test_no_furigana_option():
    data = generate("furigana_hash.ass", Options(furigana=False))
    assert all(l["furi"] == [] and l["furiStyle"] is None for l in data["lines"])
    assert "K1-furigana" not in data["styles"]


def test_js_len_counts_utf16_units():
    from ass2ae.jsxgen import js_len
    assert js_len("漢字") == 2 and js_len("a\U0001F600") == 3


def test_line_seconds_for_ae_side_frames():
    first = generate("jp_kanji_kana.ass", Options(offset=F(1, 2)))["lines"][0]
    assert (first["start"], first["end"]) == (1.5, 3.5)


def test_unsung_color_replaces_secondary_colour():
    data = generate("jp_kanji_kana.ass", Options(unsung_color=[0, 1, 0], style_mode="ass"))
    assert all(st["fill"] == [0, 1, 0] for st in data["styles"].values())
