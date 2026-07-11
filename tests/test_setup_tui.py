from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("setup_tui", ROOT / "scripts/setup_tui.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SetupTuiTests(unittest.TestCase):
    def test_main_menu_has_required_order_and_default(self) -> None:
        self.assertEqual("smart-update", MODULE.MAIN_MENU[0].action)
        self.assertEqual(
            [
                "Smart Update",
                "Set Up or Change This Mac",
                "Verify and Repair",
                "Manage Skills",
                "Backups and Rollback",
                "Advanced",
                "Exit",
            ],
            [item.label for item in MODULE.MAIN_MENU],
        )

    def test_navigation_wraps_and_supports_jk(self) -> None:
        self.assertEqual(6, MODULE.move_selection(0, ord("k"), 7))
        self.assertEqual(0, MODULE.move_selection(6, ord("j"), 7))

    def test_numbered_fallback_uses_default_on_enter(self) -> None:
        output = io.StringIO()
        selected = MODULE.prompt_menu("Menu", MODULE.MAIN_MENU, input_fn=lambda _: "", output=output)
        self.assertEqual("smart-update", selected)
        self.assertIn("1. Smart Update (default)", output.getvalue())

    def test_numbered_fallback_maps_selection(self) -> None:
        selected = MODULE.prompt_menu("Menu", MODULE.MAIN_MENU, input_fn=lambda _: "4", output=io.StringIO())
        self.assertEqual("skills", selected)

    def test_fresh_mac_detection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            self.assertTrue(MODULE.is_fresh_mac(home))
            (home / ".agents/skills").mkdir(parents=True)
            self.assertFalse(MODULE.is_fresh_mac(home))

    def test_only_verified_snapshots_are_listed_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("20260101T000000Z", "20260102T000000Z"):
                path = root / name
                path.mkdir()
                (path / "VERIFIED").write_text("verified\n")
            (root / "unverified").mkdir()
            self.assertEqual(
                ["20260102T000000Z", "20260101T000000Z"],
                [path.name for path in MODULE.verified_snapshots(root)],
            )

    def test_saved_profile_defaults_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "profile"
            self.assertEqual("personal", MODULE.saved_profile(state))
            MODULE.save_profile("work", state)
            self.assertEqual("work", MODULE.saved_profile(state))


if __name__ == "__main__":
    unittest.main()
