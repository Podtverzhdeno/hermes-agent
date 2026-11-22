"""Static executable-snippet lint catches documented dangerous defaults."""
from pathlib import Path
import unittest

from scripts.skill_harness_safety_lint import (
    audit_reviewed_skills, lint_shell_snippets,
)

ROOT = Path(__file__).resolve().parents[2]


class TestSnippetLint(unittest.TestCase):
    def test_audited_skill_examples_are_clear(self):
        self.assertEqual(audit_reviewed_skills(ROOT), [])

    def test_rejects_yolo_command_in_shell_fence(self):
        markdown = "Intro\n~~~bash\ncodex exec --yolo 'do something'\n~~~\n"
        result = lint_shell_snippets(markdown)
        self.assertEqual(result[0]["rule"], "skip-agent-permissions")

    def test_rejects_plaintext_token_storage(self):
        markdown = "~~~sh\ngit config --global credential.helper store\n~~~"
        result = lint_shell_snippets(markdown)
        self.assertEqual(result[0]["rule"], "plaintext-credential-store")

    def test_rejects_system_package_override(self):
        markdown = "~~~bash\npip install --break-system-packages pygount\n~~~"
        self.assertEqual(lint_shell_snippets(markdown)[0]["rule"],
                         "global-python-package-override")

    def test_prose_warning_does_not_trigger_false_positive(self):
        warning = "Never use --yolo or dangerously-skip-permissions.\n"
        self.assertEqual(lint_shell_snippets(warning), [])

    def test_shell_comments_dont_trigger_command_rule(self):
        content = "~~~bash\n# Never codex exec --yolo\ncodex --version\n~~~"
        self.assertEqual(lint_shell_snippets(content), [])

    def test_backtick_fence_parsed(self):
        markdown = "\x60\x60\x60bash\nclaude --dangerously-skip-permissions\n\x60\x60\x60"
        self.assertEqual(lint_shell_snippets(markdown)[0]["rule"],
                         "skip-agent-permissions")


if __name__ == "__main__":
    unittest.main()
