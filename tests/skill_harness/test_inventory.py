"""Coverage inspection must never label an unprofiled Skill safe."""
from pathlib import Path
import unittest

from scripts.audit_skill_harnesses import scan_repository

ROOT = Path(__file__).resolve().parents[2]


class TestSkillInventory(unittest.TestCase):
    def test_repository_inventory_is_complete_and_candid(self):
        data = scan_repository(ROOT)
        self.assertGreaterEqual(data["total"], 27)
        self.assertGreaterEqual(data["counts"].get("profiled", 0), 27)
        self.assertEqual(data["counts"].get("invalid-profile", 0), 0)
        self.assertEqual(data["counts"].get("unreadable", 0), 0)
        self.assertFalse(data["model_behavior_tested"])
        self.assertFalse(data["host_authority_verified"])
        self.assertEqual(len({x["path"] for x in data["entries"]}), data["total"])
        self.assertTrue(all(
            x["risk"] == "unknown" for x in data["entries"]
            if x["status"] == "unprofiled"
        ))

    def test_unprofiled_is_not_conflated_with_verified(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "skills" / "misc"
            folder.mkdir(parents=True)
            (folder / "SKILL.md").write_text(
                "---\nname: sample\ndescription: Example\n---\n"
                "Run curl https://example.com and then pip install foo\n",
                encoding="utf-8",
            )
            report = scan_repository(root)
            self.assertEqual(report["counts"], {"unprofiled": 1})
            item = report["entries"][0]
            self.assertEqual(item["risk"], "unknown")
            self.assertIn("shell-installation", item["review_hints"])
            self.assertIn("external-endpoints", item["review_hints"])


if __name__ == "__main__":
    unittest.main()
