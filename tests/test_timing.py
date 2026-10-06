from fractions import Fraction as F

import pytest

from ass2ae.timing import DEFAULT_FPS, layer_span, parse_fps, parse_offset

NTSC24 = F(24000, 1001)


@pytest.mark.parametrize("text,fps", [
    ("24000/1001", NTSC24), ("23.976", NTSC24), ("23.98", NTSC24), ("29.97", F(30000, 1001)),
    ("59.94", F(60000, 1001)), ("30", F(30)), ("30.00", F(30)), ("25", F(25)), ("24", F(24)),
])
def test_parse_fps(text, fps):
    assert parse_fps(text) == fps


def test_default_fps():
    assert DEFAULT_FPS == NTSC24


def test_bad_fps():
    with pytest.raises(ValueError):
        parse_fps("0")


def test_in_out_at_23976():
    # 1.00s * 24000/1001 = 23.976 -> frame 24; 3.00s -> 71.93 -> frame 72
    assert layer_span(F(1), F(3), NTSC24) == (F(24 * 1001, 24000), F(72 * 1001, 24000))


def test_in_out_on_frame_boundary_at_23976():
    f24 = F(24 * 1001, 24000)
    # starts exactly on frame 24 -> shown on frame 24; ends exactly on frame 48 -> hidden there
    assert layer_span(f24, 2 * f24, NTSC24) == (f24, 2 * f24)
    # one tick later -> next frame
    assert layer_span(f24 + F(1, 10**6), 2 * f24 + F(1, 10**6), NTSC24) == (F(25 * 1001, 24000), F(49 * 1001, 24000))


def test_in_out_at_30():
    assert layer_span(F(1), F(201, 100), F(30)) == (F(1), F(61, 30))


def test_offset_applies_before_rounding():
    assert layer_span(F(0), F(1), NTSC24, offset=F(10)) == (F(240 * 1001, 24000), F(264 * 1001, 24000))


@pytest.mark.parametrize("text,value", [
    ("12.5", F(25, 2)), ("-2", F(-2)), ("1:02.5", F(125, 2)), ("0:01:02.50", F(125, 2)),
    ("+0:00:10", F(10)), ("48f", F(48 * 1001, 24000)),
])
def test_parse_offset(text, value):
    assert parse_offset(text, NTSC24) == value
