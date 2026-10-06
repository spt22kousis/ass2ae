from fractions import Fraction as F

import pysubs2
import pytest

from ass2ae.layout import get_style, parse_color, placement, play_res
from ass2ae.model import Line


def subs_with(**info):
    s = pysubs2.SSAFile()
    s.info.clear()
    s.info.update({k: str(v) for k, v in info.items()})
    return s


@pytest.mark.parametrize("info,res", [
    ({"PlayResX": 1920, "PlayResY": 1080}, (1920, 1080)),
    ({}, (384, 288)),
    ({"PlayResX": 1280}, (1280, 1024)),
    ({"PlayResX": 640}, (640, 480)),
    ({"PlayResY": 1024}, (1280, 1024)),
    ({"PlayResY": 720}, (960, 720)),
])
def test_play_res_defaults(info, res):
    assert play_res(subs_with(**info)) == res


@pytest.mark.parametrize("text,rgb", [
    ("#FF8000", [1.0, 0.501961, 0.0]),
    ("ff8000", [1.0, 0.501961, 0.0]),
    ("&H0080FF&", [1.0, 0.501961, 0.0]),
    ("&H000080FF", [1.0, 0.501961, 0.0]),
])
def test_parse_color(text, rgb):
    assert parse_color(text) == rgb


def test_parse_color_rejects_garbage():
    with pytest.raises(ValueError):
        parse_color("red")


def make_line(alignment=None, pos=None, margins=(0, 0, 0)):
    return Line(1, "Dialogue", "S", F(0), F(1), "x", [], False, alignment, pos, margins)


STYLE = pysubs2.SSAStyle(alignment=2, marginl=30, marginr=50, marginv=40)
RES = (1920, 1080)


@pytest.mark.parametrize("an,x,y,justify,vertical", [
    (1, 30, 1040, "left", "bottom"),
    (2, 950, 1040, "center", "bottom"),
    (3, 1870, 1040, "right", "bottom"),
    (4, 30, 540, "left", "middle"),
    (5, 950, 540, "center", "middle"),
    (6, 1870, 540, "right", "middle"),
    (7, 30, 40, "left", "top"),
    (8, 950, 40, "center", "top"),
    (9, 1870, 40, "right", "top"),
])
def test_placement_from_alignment_and_margins(an, x, y, justify, vertical):
    p = placement(make_line(alignment=an), STYLE, RES)
    assert (p.alignment, p.x, p.y, p.justify, p.vertical) == (an, x, y, justify, vertical)
    assert not p.positioned


def test_style_alignment_used_without_override():
    assert placement(make_line(), STYLE, RES).alignment == 2


def test_event_margins_override_style():
    p = placement(make_line(alignment=1, margins=(100, 0, 200)), STYLE, RES)
    assert (p.x, p.y) == (100, 880)


def test_pos_overrides_margins():
    p = placement(make_line(alignment=8, pos=(F(960), F(201, 2))), STYLE, RES)
    assert (p.x, p.y, p.positioned) == (960, F(201, 2), True)


def test_unknown_style_falls_back_to_default():
    s = pysubs2.SSAFile()
    s.styles["Other"] = pysubs2.SSAStyle(fontsize=10)
    assert get_style(s, "Nope") is s.styles["Default"]
