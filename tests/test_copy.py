"""No accusation words in UI text, templates or exports (SRS-NF-14, UF §7)."""
import re
from pathlib import Path

import pytest

from nakshatra.report import templates as T

ROOT = Path(__file__).parents[1]
WORDS = re.compile(r"\b(fake|fraud|fraudulent|scam)", re.I)


def test_templates_clean():
    for name in ("RING_TMPL", "LOCK_TMPL", "VERDICT_TMPL", "NONE_TMPL"):
        assert not WORDS.search(getattr(T, name)), name
    assert not any(WORDS.search(v) for v in T.PHASE_LABELS.values())


def test_check_copy_rejects():
    with pytest.raises(ValueError):
        T.check_copy("These look like Fake reviews")
    assert T.check_copy("coordinated, unlikely by chance") == "coordinated, unlikely by chance"


def test_user_facing_sources_clean():
    files = list((ROOT / "nakshatra" / "report").glob("*.py")) + list((ROOT / "web" / "src").rglob("*.ts*"))
    for f in files:
        for i, line in enumerate(f.read_text().splitlines(), 1):
            if "BANNED" in line or "WORDS" in line or line.strip().startswith("#"):
                continue
            assert not WORDS.search(line), f"{f.name}:{i}: {line.strip()}"
