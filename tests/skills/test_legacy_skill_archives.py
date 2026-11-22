"""Lossless archival checks for original knowledge-rich skills.

All original content is preserved; shrinking activated SKILL.md must never
silently delete previous examples. The Git blob SHA fixes the exact source.
"""
from hashlib import sha1
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ORIGINALS = [
    ("skills/autonomous-ai-agents/hermes-agent",
     "references/legacy-full-guide-2026.md",
     "8d93e3fb793fa5b702315d335d30204798635104", 9000),
    ("skills/research/ml-paper-writing",
     "references/legacy-paper-guide-2026.md",
     "8650ef8762d9aa0ded9641d672672964ac7980a0", 9000),
    ("skills/mlops/evaluation/lm-evaluation-harness",
     "references/legacy-full-2026.md",
     "7b820424fbadaeef7983e8eb71afc859f24a7f1e", 9000),
    ("skills/mlops/research/dspy",
     "references/legacy-full-2026.md",
     "20840199596d3c737e5a0cd4491d7a6cfe0b64d6", 9000),
    ("optional-skills/mlops/chroma",
     "references/legacy-full-2026.md",
     "94cb8ebac5410c5dce043c8dd4b248b8c0ded2f5", 9000),
    ("optional-skills/mlops/faiss",
     "references/legacy-full-2026.md",
     "2e33007b309667e608d33d249420ca8c1889d5a4", 9000),
    ("optional-skills/mlops/qdrant",
     "references/legacy-full-2026.md",
     "d6e9d33d31f9b540131d73389491323c6d2175a6", 9000),
]


def _blob_sha(text):
    blob = text.encode("utf-8")
    return sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest()


@pytest.mark.parametrize("folder,arch,expected,limit", ORIGINALS)
def test_archives_recover_original_git_content(folder, arch, expected, limit):
    root = REPO / folder
    text = (root / arch).read_text(encoding="utf-8")
    marker = "\n---\n\n"
    assert marker in text
    original = text.split(marker, 1)[1]
    assert _blob_sha(original) == expected, folder

    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    assert len(skill) < limit
    assert "references/" in skill, "Active skill should point to archived details"
    assert len(skill) < len(original), "No context saving despite archival"


def test_lm_eval_uses_version_aware_current_cli():
    text = (REPO / "skills/mlops/evaluation/lm-evaluation-harness/SKILL.md").read_text()
    assert "lm-eval run" in text
    assert "lm-eval ls tasks" in text
    assert "lm_eval --model " not in text


def test_dspy_never_presumes_optimization_gain():
    text = (REPO / "skills/mlops/research/dspy/SKILL.md").read_text()
    assert "held-out" in text
    assert "dspy.configure" in text
    assert "now optimized_qa performs better" not in text
