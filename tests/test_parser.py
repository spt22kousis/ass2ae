from fractions import Fraction as F

import pytest

from ass2ae.parser import load, parse_subs

from .conftest import EXAMPLES, FIXTURES


def lines_of(name, **kw):
    return parse_subs(load(str(FIXTURES / name)), **kw)


def test_jp_fixture():
    res = lines_of("jp_kanji_kana.ass")
    by_no = {l.event_no: l for l in res.lines}
    assert sorted(by_no) == [1, 2, 3, 4, 7, 8]
    assert res.skipped == {"Dialogue with Effect=fx": 1, "Comment": 1}

    l1 = by_no[1]
    assert l1.text == "君の名前は" and l1.alignment == 8 and l1.pos == (F(960), F(100))
    assert [h.kind for s in l1.syllables for h in s.highlights] == ["k", "k", "kf", "ko", "kf"]
    assert [s.start for s in l1.syllables] == [F(1), F(12, 10), F(15, 10), F(175, 100), F(2)]

    assert not by_no[2].has_karaoke and by_no[2].text == "你的名字是" and by_no[2].tags["fad"] == 1

    l3 = by_no[3]
    assert [(s.text, s.start, s.duration) for s in l3.syllables] == [
        ("前夜", F(4), F(1, 2)), ("空", F(48, 10), F(2, 10)), ("を", F(5), F(1))]

    l4 = by_no[4]
    assert l4.event_type == "Comment"
    assert [(s.text, s.start) for s in l4.syllables] == [("星", F(7)), ("空", F(75, 10)), ("だ", F(85, 10))]

    assert by_no[7].text == "上の\n下だ"
    assert by_no[8].text == "あ い" and by_no[8].tags["t"] == 1


def test_en_fixture():
    res = lines_of("en_spaces.ass")
    texts = [[s.text for s in l.syllables] for l in res.lines]
    assert texts == [
        ["Hel", "lo ", "world ", "again"],
        ["I want", " to fly!"],
        ["one ", "two three"],
        ["soft ", "break"],
        ["comment", " here"],
    ]
    assert any("truncated" in w for w in res.lines[2].warnings)


def test_furigana_fixture():
    res = lines_of("furigana_hash.ass")
    assert [l.text for l in res.lines] == ["漢字", "頭 で", "今日は", "東京", "あ", "#a", "漢字"]
    # a \-B block after a syllable's text belongs to that syllable (AssKaraoke), and is sticky
    assert [s.inline_fx for s in res.lines[1].syllables] == ["A", "B", "B"]


def test_templated_fixture_selects_only_source_lines():
    res = lines_of("templated.ass")
    assert [(l.event_type, l.style) for l in res.lines] == [
        ("Comment", "K2"), ("Comment", "K1"), ("Comment", "K2"), ("Dialogue", "noK")]
    assert res.skipped["Dialogue with Effect=fx"] == 4
    assert res.skipped["Comment"] == 4
    assert res.lines[0].text == "頭 でわかっては嘆いた"
    assert not res.lines[3].has_karaoke


def test_styles_filter():
    res = lines_of("templated.ass", styles=["K1"])
    assert [l.style for l in res.lines] == ["K1"]
    assert res.skipped["style not selected"] == 3


def test_event_numbers_match_aegisub_rows():
    res = lines_of("templated.ass")
    assert [l.event_no for l in res.lines] == [5, 6, 7, 12]


def _example_files():
    return sorted(EXAMPLES.glob("*.ass")) if EXAMPLES.is_dir() else []


@pytest.mark.skipif(not _example_files(), reason="ass_example/ not present")
@pytest.mark.parametrize("path", _example_files(), ids=lambda p: p.name)
def test_real_files_invariants(path):
    res = parse_subs(load(str(path)))
    assert res.lines
    for line in res.lines:
        if not line.has_karaoke:
            continue
        assert "".join(s.text for s in line.syllables) == line.text
        for a, b in zip(line.syllables, line.syllables[1:]):
            assert a.start < b.start
        assert all(s.duration > 0 for s in line.syllables)
        assert all(line.start <= s.start and s.end <= line.end for s in line.syllables)
