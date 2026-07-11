from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("agent_environment", ROOT / "scripts/agent_environment.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AgentEnvironmentTests(unittest.TestCase):
    def test_orchestrator_never_upgrades_brew_implicitly(self) -> None:
        source = (ROOT / "scripts/new_mac_actions.py").read_text()
        self.assertIn('"bundle", "install", "--no-upgrade"', source)

    def test_tree_digest_detects_content_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "SKILL.md"
            path.write_text("one\n")
            before = MODULE.tree_digest(root)
            path.write_text("two\n")
            self.assertNotEqual(before, MODULE.tree_digest(root))

    def test_replace_with_link_replaces_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.write_text("target\n")
            link = root / "link"
            link.write_text("old\n")
            MODULE.replace_with_link(link, target)
            self.assertTrue(link.is_symlink())
            self.assertEqual(target.resolve(), link.resolve())


if __name__ == "__main__":
    unittest.main()
