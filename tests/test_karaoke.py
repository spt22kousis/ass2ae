"""One test group per parsing rule in SPEC.md."""
from fractions import Fraction as F

import pytest

from ass2ae.karaoke import InvariantError, check_invariants
from ass2ae.model import Syllable
from ass2ae.tags import NBSP

from .conftest import marks, parse


# --- \k family -------------------------------------------------------------

def test_each_k_tag_starts_a_syllable_in_centiseconds():
    tp = parse(r"{\k20}a{\K30}b{\kf25}c{\ko25}d", start=F(1))
    assert marks(tp) == [
        ("a", F(1), F(20, 100)),
        ("b", F(120, 100), F(30, 100)),
        ("c", F(150, 100), F(25, 100)),
        ("d", F(175, 100), F(25, 100)),
    ]
    assert [(h.tag, h.kind, h.cs) for s in tp.syllables for h in s.highlights] == [
        ("k", "k", 20), ("K", "kf", 30), ("kf", "kf", 25), ("ko", "ko", 25)]
    assert tp.has_karaoke


def test_start_is_line_start_plus_previous_k_values():
    tp = parse(r"{\k10}a{\k20}b{\k30}c", start=F(5))
    assert [s.start for s in tp.syllables] == [F(5), F(510, 100), F(530, 100)]


def test_decimal_k_values_are_exact():
    tp = parse(r"{\k12.5}a{\k10}b")
    assert tp.syllables[1].start == F(125, 1000)


def test_two_k_in_one_block_make_an_empty_syllable():
    tp = parse(r"{\k10}a{\k30\k20}b")
    assert marks(tp) == [("a", F(0), F(10, 100)), ("b", F(40, 100), F(20, 100))]


def test_text_before_first_k_is_zero_duration_and_joins_next():
    tp = parse(r"pre{\k50}a{\k50}b", start=F(2))
    assert marks(tp) == [("prea", F(2), F(1, 2)), ("b", F(5, 2), F(1, 2))]
    assert tp.syllables[0].highlights[0].tag is None


def test_line_without_k_has_no_syllables():
    tp = parse(r"{\fad(200,200)}translation")
    assert tp.text == "translation" and tp.syllables == [] and not tp.has_karaoke


def test_line_without_k_keeps_pipes_and_hashes():
    tp = parse("a|b #c")
    assert tp.text == "a|b #c"


def test_missing_and_negative_k_values_warn():
    tp = parse(r"{\k}a{\k-5}b{\k10}c")
    assert marks(tp) == [("abc", F(0), F(1, 10))]
    assert len([w for w in tp.warnings if "treated as 0" in w]) == 2


def test_kt_is_reported():
    tp = parse(r"{\k10}a{\kt5}b")
    assert any("kt" in w for w in tp.warnings)
    assert tp.tags["kt"] == 1


# --- other tags --------------------------------------------------------------

def test_other_tags_are_removed_and_counted():
    tp = parse(r"{\fad(1,2)\c&H0000FF&\k10}a{\t(0,1,\fscx120)\k10}b{\bord3}")
    assert tp.text == "ab"
    assert dict(tp.tags) == {"fad": 1, "c": 1, "t": 1, "bord": 1}


def test_unknown_tags_counted_with_question_mark():
    tp = parse(r"{\zz9\k10}a")
    assert tp.tags["?zz9"] == 1


def test_pos_and_an_from_first_block():
    tp = parse(r"{\an8\pos(960,100.5)\k10}a")
    assert tp.alignment == 8 and tp.pos == (F(960), F(201, 2))
    assert tp.warnings == []


def test_first_alignment_wins_and_later_block_warns():
    tp = parse(r"{\k10}a{\an7\an3}b")
    assert tp.alignment == 7
    assert any("first override block" in w for w in tp.warnings)


def test_legacy_a_and_invalid_an():
    assert parse(r"{\a6}x").alignment == 8
    assert parse(r"{\an12}x").alignment is None


def test_pos_needs_two_args_and_move_blocks_pos():
    assert parse(r"{\pos(1)}x").pos is None
    tp = parse(r"{\move(1,2,3,4)\pos(5,6)}x")
    assert tp.pos is None and any("move" in w for w in tp.warnings)


def test_comment_block_without_backslash_is_ignored():
    tp = parse(r"{\k40}com{note to self}ment")
    assert marks(tp) == [("comment", F(0), F(4, 10))]
    assert not tp.tags


# --- special characters --------------------------------------------------------

def test_hard_newline_and_hard_space():
    tp = parse(r"{\k10}a\N{\k10}b\hc")
    assert tp.text == "a\nb" + NBSP + "c"
    assert [s.text for s in tp.syllables] == ["a\n", "b" + NBSP + "c"]


def test_soft_newline_depends_on_wrap_style():
    assert parse(r"a\nb", wrap=0).text == "a b"
    assert parse(r"a\nb", wrap=2).text == "a\nb"


def test_q_override_changes_wrap_style():
    assert parse(r"{\q2}a\nb", wrap=0).text == "a\nb"
    assert parse(r"{\q9}a\nb", wrap=2).text == "a\nb"  # invalid \q -> script WrapStyle


def test_escaped_braces_and_tab():
    assert parse(r"\{x\}" + "\ty").text == "{x} y"


# --- furigana and # ------------------------------------------------------------

def test_furigana_split():
    tp = parse(r"{\k20}漢|かん{\k20}字|じ")
    assert [s.text for s in tp.syllables] == ["漢", "字"]
    assert [(f.text, f.start, f.duration) for s in tp.syllables for f in s.furi] == [
        ("かん", F(0), F(1, 5)), ("じ", F(1, 5), F(1, 5))]


def test_hash_continuation_merges_time_and_keeps_furigana_times():
    tp = parse(r"{\k10}頭|<あ{\k12}#|<た{\k13}#|<ま{\k2} {\k12}で", start=F(2))
    assert marks(tp) == [
        ("頭", F(2), F(35, 100)),
        (" ", F(235, 100), F(2, 100)),
        ("で", F(237, 100), F(12, 100)),
    ]
    head = tp.syllables[0]
    assert [(f.text, f.start, f.duration, f.spillback, f.isbreak) for f in head.furi] == [
        ("あ", F(2), F(10, 100), True, True),
        ("た", F(210, 100), F(12, 100), True, True),
        ("ま", F(222, 100), F(13, 100), True, True),
    ]
    assert [h.cs for h in head.highlights] == [10, 12, 13]


def test_fullwidth_pipe_and_hash():
    tp = parse(r"{\k15}今日｜きょ{\k15}＃｜う{\k20}は")
    assert [s.text for s in tp.syllables] == ["今日", "は"]
    assert [f.text for f in tp.syllables[0].furi] == ["きょ", "う"]


def test_break_prefix():
    tp = parse(r"{\k10}東|!とう{\k10}京|！きょう")
    assert [(f.text, f.isbreak, f.spillback) for s in tp.syllables for f in s.furi] == [
        ("とう", True, False), ("きょう", True, False)]


def test_hash_with_extra_text_is_dropped_with_warning():
    tp = parse(r"{\k10}あ{\k10}#い")
    assert tp.text == "あ" and marks(tp) == [("あ", F(0), F(1, 5))]
    assert any("continuation" in w for w in tp.warnings)


def test_hash_as_first_syllable_is_literal():
    tp = parse(r"{\k10}#{\k10}a")
    assert [s.text for s in tp.syllables] == ["#", "a"]


def test_spaces_around_furigana_syllable_are_kept():
    tp = parse(r"{\k10} 漢|かん {\k10}字")
    assert [s.text for s in tp.syllables] == [" 漢 ", "字"]


def test_inline_fx_is_sticky():
    tp = parse(r"{\-A}{\k10}a{\k10}b {\-B}{\k10}c{\k10}d")
    assert [s.inline_fx for s in tp.syllables] == ["A", "B", "B", "B"]
    assert tp.tags["-"] == 2


# --- zero duration, empty, truncation ------------------------------------------

def test_zero_duration_text_joins_next():
    tp = parse(r"{\k10}a{\k0}b{\k10}c")
    assert marks(tp) == [("a", F(0), F(1, 10)), ("bc", F(1, 10), F(1, 10))]


def test_zero_duration_text_at_end_joins_previous():
    tp = parse(r"{\k10}a{\k10}b{\k0}!")
    assert marks(tp) == [("a", F(0), F(1, 10)), ("b!", F(1, 10), F(1, 10))]


def test_zero_duration_furigana_is_kept_on_merge():
    tp = parse(r"{\k0}漢|かん{\k20}字|じ")
    assert marks(tp) == [("漢字", F(0), F(1, 5))]
    assert [f.text for f in tp.syllables[0].furi] == ["かん", "じ"]


def test_empty_syllable_gets_no_marker_and_does_not_shift_others():
    tp = parse(r"{\k10}a{\k50}{\k10}b")
    assert marks(tp) == [("a", F(0), F(1, 10)), ("b", F(6, 10), F(1, 10))]


def test_zero_total_duration():
    tp = parse(r"{\k0}a{\k0}b")
    assert tp.syllables == [] and tp.text == "ab"
    assert any("zero total duration" in w for w in tp.warnings)


def test_truncation_at_line_end():
    tp = parse(r"{\k30}one {\k30}two {\k30}three", start=F(3), end=F(35, 10))
    assert marks(tp) == [("one ", F(3), F(3, 10)), ("two three", F(33, 10), F(2, 10))]
    assert any("truncated" in w for w in tp.warnings)


def test_syllable_exactly_at_line_end_is_not_truncated():
    tp = parse(r"{\k50}a{\k50}b", start=F(0), end=F(1))
    assert tp.warnings == []


# --- invariants and character warnings -------------------------------------------

@pytest.mark.parametrize("text", [
    r"{\k20}Hel{\k15}lo {\k30}world {\k10}again",
    r"I {\k25}want{\k0} to{\k25} fly{\k0}!",
    r"{\-A}{\k8}頭|<あ{\k12}#|<た{\k13}#|<ま{\k2} {\k12}で",
    r"pre{\k10\k0}{\k0}x{\k10}{\k0}\N{\k20}y{\k0}z",
])
def test_invariants_hold(text):
    tp = parse(text, end=F(1))
    assert "".join(s.text for s in tp.syllables) == tp.text
    starts = [s.start for s in tp.syllables]
    assert starts == sorted(set(starts))


def test_check_invariants_detects_violations():
    a = Syllable("a", F(0), F(1))
    b = Syllable("b", F(0), F(1))
    with pytest.raises(InvariantError):
        check_invariants("ab", [a, b])
    with pytest.raises(InvariantError):
        check_invariants("ax", [a, Syllable("b", F(1), F(1))])


def test_non_bmp_warning():
    tp = parse("{\\k10}a\U0001F600")
    assert any("non-BMP" in w and "U+1F600" in w for w in tp.warnings)


def test_combining_warning():
    tp = parse("{\\k10}が")
    assert any("U+3099" in w for w in tp.warnings)
