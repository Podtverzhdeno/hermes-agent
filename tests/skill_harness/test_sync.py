"""Bundled skill sync must preserve customizations and disclose harness drift."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.skills_sync import sync_skills


class TestSkillHarnessSync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.bundled = root / "bundled"
        self.user = root / "user"
        self.manifest = self.user / ".bundled_manifest"
        skill = self.bundled / "github" / "example-skill"
        skill.mkdir(parents=True)
        self.source_skill = skill
        (skill / "SKILL.md").write_text(
            "---\nname: example-skill\n---\nOriginal", encoding="utf-8"
        )
        (skill / "harness.json").write_text(
            '{"skill":"example-skill","version":1}', encoding="utf-8"
        )
        self.parts = [
            patch("tools.skills_sync._get_bundled_dir", return_value=self.bundled),
            patch("tools.skills_sync.SKILLS_DIR", self.user),
            patch("tools.skills_sync.MANIFEST_FILE", self.manifest),
        ]
        for item in self.parts:
            item.start()
            self.addCleanup(item.stop)

    def test_fresh_profile_copied_with_source(self):
        result = sync_skills(quiet=True)
        self.assertEqual(result["harness_pending"], [])
        self.assertEqual(result["copied"], ["example-skill"])
        self.assertTrue((self.user / "github" / "example-skill" / "harness.json").exists())

    def test_user_modified_skill_never_overwritten_by_new_harness(self):
        sync_skills(quiet=True)
        local_skill = self.user / "github" / "example-skill"
        (local_skill / "SKILL.md").write_text("User custom instructions", encoding="utf-8")
        (self.source_skill / "SKILL.md").write_text("New upstream instructions", encoding="utf-8")
        (self.source_skill / "harness.json").write_text('{"version":2}', encoding="utf-8")
        result = sync_skills(quiet=True)
        self.assertEqual(result["user_modified"], ["example-skill"])
        self.assertEqual(result["harness_pending"], ["example-skill"])
        self.assertEqual((local_skill / "SKILL.md").read_text(), "User custom instructions")
        self.assertEqual((local_skill / "harness.json").read_text(),
                         '{"skill":"example-skill","version":1}')

    def test_unmodified_skill_gets_updated_harness(self):
        sync_skills(quiet=True)
        (self.source_skill / "harness.json").write_text('{"version":2}', encoding="utf-8")
        result = sync_skills(quiet=True)
        self.assertEqual(result["updated"], ["example-skill"])
        self.assertEqual(result["harness_pending"], [])
        self.assertEqual(
            (self.user / "github" / "example-skill" / "harness.json").read_text(),
            '{"version":2}',
        )

    def test_user_deleted_skill_does_not_trigger_automatic_reinstallation(self):
        import shutil
        sync_skills(quiet=True)
        shutil.rmtree(self.user / "github" / "example-skill")
        result = sync_skills(quiet=True)
        self.assertEqual(result["harness_pending"], [])
        self.assertFalse((self.user / "github" / "example-skill").exists())


if __name__ == "__main__":
    unittest.main()
