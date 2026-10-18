from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import new_mac_actions as ACTIONS  # noqa: E402
from new_mac_core import Runner, load_profile  # noqa: E402


class ClaudeSetupTests(unittest.TestCase):
    def test_existing_claude_file_is_backed_up_not_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            (home / ".agents").mkdir()
            (home / ".agents/AGENTS.md").write_text("shared\n")
            (home / ".claude").mkdir()
            (home / ".claude/CLAUDE.md").write_text("hand-written\n")

            ACTIONS.link_into_place(home / ".claude/CLAUDE.md", home / ".agents/AGENTS.md", Runner(False))

            self.assertTrue((home / ".claude/CLAUDE.md").is_symlink())
            self.assertEqual((home / ".claude/CLAUDE.md").read_text(), "shared\n")
            backups = list((home / ".claude").glob("CLAUDE.md.backup-*"))
            self.assertEqual([path.read_text() for path in backups], ["hand-written\n"])

    def test_correct_link_is_left_alone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            target = home / "AGENTS.md"
            target.write_text("shared\n")
            link = home / "CLAUDE.md"
            link.symlink_to(target)
            runner = mock.Mock()
            ACTIONS.link_into_place(link, target, runner)
            runner.run.assert_not_called()

    def test_profiles_with_codex_plugins_also_set_up_claude(self) -> None:
        for profile in ("personal", "agent-dev"):
            config = load_profile(profile)
            self.assertIn("claude", config["default_components"])
            self.assertTrue(config["claude_plugins"])


if __name__ == "__main__":
    unittest.main()
