"""Prove FSDP progressive disclosure did not discard the original scrape."""

from hashlib import sha1
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FSDP = ROOT / "skills" / "mlops" / "training" / "pytorch-fsdp"
LEGACY_ORIGINAL_BLOB = "9e16f446ff7601ba63cc898eca4eb47b12b663d2"
OTHER_ORIGINAL_BLOB = "2b544dc982f60417274162d5d7fa5fdd453603df"


def _git_blob_digest(text: str) -> str:
    raw = text.encode("utf-8")
    return sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def test_original_fsdp_skill_content_archived_exactly():
    archive = (FSDP / "references" / "legacy-generated-2025.md").read_text(encoding="utf-8")
    marker = "\n---\n\n"
    assert marker in archive
    original = archive.split(marker, 1)[1]
    assert _git_blob_digest(original) == LEGACY_ORIGINAL_BLOB


def test_original_other_reference_content_archived_exactly():
    refs = FSDP / "references"
    first = (refs / "archive-distributed-foundations.md").read_text(encoding="utf-8")
    second = (refs / "archive-checkpoint-parallelism.md").read_text(encoding="utf-8")
    assert _git_blob_digest(first + "\n" + second) == OTHER_ORIGINAL_BLOB


def test_fsdp_activation_is_bounded_but_archives_remain_readable():
    active = (FSDP / "SKILL.md").read_text(encoding="utf-8")
    index = (FSDP / "references" / "other.md").read_text(encoding="utf-8")
    assert len(active) < 10000
    assert len(index) < 2000
    assert "fully_shard" in active
    for name in (
        "legacy-generated-2025.md",
        "archive-distributed-foundations.md",
        "archive-checkpoint-parallelism.md",
    ):
        assert (FSDP / "references" / name).stat().st_size < 256 * 1024
