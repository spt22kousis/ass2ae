from fractions import Fraction as F

import pytest

from ass2ae.tags import (NBSP, argtod, convert_text, legacy_alignment_to_numpad, parse_override,
                         split_segments)


def names(block):
    return [t.name for t in parse_override(block)]


def test_split_segments_blocks_and_text():
    segs = split_segments(r"a{\k10}b{\pos(1,2)}c")
    assert [(s.kind, s.raw) for s in segs] == [
        ("text", "a"), ("tags", r"\k10"), ("text", "b"), ("tags", r"\pos(1,2)"), ("text", "c")]


def test_unclosed_brace_is_text():
    segs = split_segments(r"a{b")
    assert [(s.kind, s.raw) for s in segs] == [("text", "a{b")]


def test_escaped_brace_does_not_open_block():
    segs = split_segments(r"a\{b\}c{\k1}")
    assert [(s.kind, s.raw) for s in segs] == [("text", r"a\{b\}c"), ("tags", r"\k1")]


def test_comment_block_has_no_tags():
    segs = split_segments("x{just a note}y")
    assert segs[1].kind == "tags" and segs[1].tags == ()


@pytest.mark.parametrize("block,expected", [
    (r"\fscx120\fs50\fsp2", ["fscx", "fs", "fsp"]),
    (r"\an8\a5", ["an", "a"]),
    (r"\kf10\K10\ko10\kt10\k10", ["kf", "K", "ko", "kt", "k"]),
    (r"\1c&H0000FF&\c&HFFFFFF&\3a&H80&", ["1c", "c", "3a"]),
    (r"\bord2\be1\b1\blur3", ["bord", "be", "b", "blur"]),
    (r"\-A", ["-"]),
    (r"\shad2\s1", ["shad", "s"]),
    (r"\pbo2\p1", ["pbo", "p"]),
])
def test_tag_name_prefix_order(block, expected):
    assert names(block) == expected


def test_tag_args_and_raw():
    (tag,) = parse_override(r"\pos(960, 540)")
    assert tag.name == "pos" and tag.args == ("960", "540") and tag.raw == r"\pos(960, 540)"
    (tag,) = parse_override(r"\k25")
    assert tag.arg == "25" and tag.args == ()


def test_backslash_argument_swallows_nested_tags():
    tags = parse_override(r"\t(0,100,\fscx120\k5)\k10")
    assert [t.name for t in tags] == ["t", "k"]
    assert tags[0].args == ("0", "100", r"\fscx120\k5")
    assert tags[1].arg == "10"


def test_unknown_tag():
    (tag,) = parse_override(r"\xyz12")
    assert not tag.known and tag.name == "xyz12"


def test_text_outside_tags_ignored():
    assert names(r"note \k10 more") == ["k"]


def test_argtod():
    assert argtod("25") == 25
    assert argtod(" 12.5xyz") == F(25, 2)
    assert argtod("") is None
    assert argtod("-3") == -3


def test_convert_text_escapes():
    assert convert_text(r"a\Nb", 0) == "a\nb"
    assert convert_text(r"a\nb", 0) == "a b"
    assert convert_text(r"a\nb", 1) == "a b"
    assert convert_text(r"a\nb", 2) == "a\nb"
    assert convert_text(r"a\hb", 0) == "a" + NBSP + "b"
    assert convert_text(r"\{x\}", 0) == "{x}"
    assert convert_text("a\tb", 0) == "a b"
    assert convert_text(r"a\xb\\", 0) == r"a\xb\\"


@pytest.mark.parametrize("legacy,numpad", [
    (1, 1), (2, 2), (3, 3), (5, 7), (6, 8), (7, 9), (9, 4), (10, 5), (11, 6), (4, 7), (8, 7)])
def test_legacy_alignment(legacy, numpad):
    assert legacy_alignment_to_numpad(legacy) == numpad
