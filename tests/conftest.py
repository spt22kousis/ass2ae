from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

import pytest

from ass2ae.karaoke import parse_text

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXAMPLES = ROOT / "ass_example"


def parse(text: str, start=F(0), end=F(100), wrap: int = 0):
    return parse_text(text, F(start), F(end), wrap)


def marks(tp):
    """(text, start, duration) of each marker syllable."""
    return [(s.text, s.start, s.duration) for s in tp.syllables]


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES
