from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import new_mac_actions as ACTIONS  # noqa: E402
import new_mac_core as CORE  # noqa: E402
import setup_tui as TUI  # noqa: E402

SPEC = importlib.util.spec_from_file_location("agent_environment", ROOT / "scripts/agent_environment.py")
assert SPEC and SPEC.loader
AGENT_ENV = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AGENT_ENV)


def context(profile: str = "personal", dry_run: bool = True, dev_root: Path | None = None) -> CORE.Context:
    args = SimpleNamespace(profile=profile, mode="assume-defaults", dev_root=str(dev_root) if dev_root else None,
                           dry_run=dry_run, with_components="", skip_components="", yes=True, json_output=False)
    return CORE.build_context(args)


class RollbackLinkTests(unittest.TestCase):
    def test_real_file_is_moved_aside_not_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            target = home / ".agents/AGENTS.md"
            target.parent.mkdir()
            target.write_text("shared\n")
            path = home / ".codex/AGENTS.md"
            path.parent.mkdir()
            path.write_text("only copy\n")

            AGENT_ENV.replace_with_link(path, target)

            self.assertTrue(path.is_symlink())
            backups = list(path.parent.glob("AGENTS.md.backup-*"))
            self.assertEqual([backup.read_text() for backup in backups], ["only copy\n"])

    def test_real_directory_is_moved_aside(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            target = home / ".agents/skills"
            target.mkdir(parents=True)
            path = home / ".claude/skills"
            (path / "mine").mkdir(parents=True)
            AGENT_ENV.replace_with_link(path, target)
            self.assertTrue(path.is_symlink())
            self.assertTrue(any((backup / "mine").is_dir() for backup in path.parent.glob("skills.backup-*")))


class SnapshotPortabilityTests(unittest.TestCase):
    def test_snapshot_works_without_bootstrap_folder_or_skills(self) -> None:
        # A second Mac has no ~/Downloads/bootstrap and may have no skills yet.
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            (home / ".agents").mkdir()
            (home / ".agents/AGENTS.md").write_text("shared\n")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/snapshot_agent_environment.py")],
                env={**os.environ, "HOME": str(home)}, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            snapshots = list((home / "Backups/agent-environment").iterdir())
            self.assertTrue((snapshots[0] / "VERIFIED").is_file())


class ProfileChoiceTests(unittest.TestCase):
    def test_smart_update_without_a_saved_profile_asks_for_one(self) -> None:
        with (
            mock.patch.object(TUI, "saved_profile", return_value=""),
            mock.patch.object(TUI, "is_fresh_mac", return_value=False),
            mock.patch.object(TUI, "choose", side_effect=["smart-update", "exit"]),
            mock.patch.object(TUI, "run_setup") as run_setup,
            mock.patch.object(TUI, "run_backend") as run_backend,
        ):
            TUI.main()
        run_setup.assert_called_once()
        run_backend.assert_not_called()

    def test_verify_and_repair_uses_the_saved_profile(self) -> None:
        with (
            mock.patch.object(TUI, "saved_profile", return_value="work"),
            mock.patch.object(TUI, "choose", side_effect=["verify-repair", "exit"]),
            mock.patch.object(TUI, "run_backend") as run_backend,
        ):
            TUI.main()
        run_backend.assert_called_once_with("verify-repair", "--profile", "work", "--yes")

    def test_apply_records_the_profile_but_a_dry_run_does_not(self) -> None:
        with mock.patch.object(ACTIONS, "save_profile") as save, redirect_stdout(io.StringIO()):
            ACTIONS.apply(CORE.Context(profile="ci", mode="assume-defaults", dev_root=Path("/nonexistent"),
                                       config={}, components=[], dry_run=True, yes=True, json_output=False))
            save.assert_not_called()
            ACTIONS.apply(CORE.Context(profile="ci", mode="assume-defaults", dev_root=Path("/nonexistent"),
                                       config={}, components=[], dry_run=False, yes=True, json_output=False))
            save.assert_called_once_with("ci")

    def test_ci_mode_says_it_applies_nothing(self) -> None:
        args = SimpleNamespace(profile="ci", mode="ci", dev_root=None, dry_run=False, with_components="",
                               skip_components="", yes=True, json_output=False)
        output = io.StringIO()
        with redirect_stdout(output):
            ctx = CORE.build_context(args)
        self.assertTrue(ctx.dry_run)
        self.assertIn("--profile ci", output.getvalue())


class ExistingMacFirstRunTests(unittest.TestCase):
    def test_existing_mac_without_profile_gets_a_snapshot_first(self) -> None:
        # An existing Mac with no recorded profile chooses one, then runs Smart
        # Update (snapshot + repo updates) rather than a plain apply.
        with (
            mock.patch.object(TUI, "saved_profile", return_value=""),
            mock.patch.object(TUI, "is_fresh_mac", return_value=False),
            mock.patch.object(TUI, "choose", side_effect=["smart-update", "work", "exit"]),
            mock.patch.object(TUI, "confirm", return_value=True),
            mock.patch.object(TUI, "save_profile"),
            mock.patch.object(TUI, "run_backend", return_value=True) as run_backend,
        ):
            TUI.main()
        self.assertEqual(run_backend.call_args_list[-1].args, ("smart-update", "--profile", "work", "--yes"))

    def test_fresh_mac_applies_directly(self) -> None:
        with (
            mock.patch.object(TUI, "saved_profile", return_value=""),
            mock.patch.object(TUI, "is_fresh_mac", return_value=True),
            mock.patch.object(TUI, "choose", side_effect=["smart-update", "personal", "exit"]),
            mock.patch.object(TUI, "confirm", return_value=True),
            mock.patch.object(TUI, "save_profile"),
            mock.patch.object(TUI, "run_backend", return_value=True) as run_backend,
        ):
            TUI.main()
        self.assertEqual(run_backend.call_args_list[-1].args[0], "apply")


class SetupMenuTests(unittest.TestCase):
    def test_changing_an_existing_mac_takes_a_snapshot_first(self) -> None:
        with (
            mock.patch.object(TUI, "is_fresh_mac", return_value=False),
            mock.patch.object(TUI, "choose", side_effect=["setup", "work", "exit"]),
            mock.patch.object(TUI, "confirm", return_value=True),
            mock.patch.object(TUI, "save_profile"),
            mock.patch.object(TUI, "run_backend", return_value=True) as run_backend,
        ):
            TUI.main()
        self.assertEqual(run_backend.call_args_list[-1].args[0], "smart-update")


class StageSkillsTests(unittest.TestCase):
    def test_staged_skills_keep_everything_the_catalog_does_not_provide(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            live = home / ".agents/skills"
            (live / "council").mkdir(parents=True)
            (live / "council/SKILL.md").write_text("external\n")
            (live / ".system").mkdir()
            (live / ".external-skills.json").write_text("{}\n")
            (live / ".private-skills.record").write_text("x y\n")
            (live / "tool-managed").symlink_to(home)
            dev_root = home / "Development"
            (dev_root / "skills/scripts").mkdir(parents=True)
            (dev_root / "skills/scripts/install-skills.py").write_text("")
            snapshot = home / "snapshot"
            snapshot.mkdir()
            commands = []

            def fake_run(command, cwd=None, check=None):
                commands.append(command)
                if "install" in command:
                    candidate = Path(command[command.index("--target") + 1])
                    (candidate / "catalog-skill").mkdir(parents=True)

            with (
                mock.patch.object(AGENT_ENV, "HOME", home),
                mock.patch.object(AGENT_ENV, "DEV_ROOT", dev_root),
                mock.patch.object(AGENT_ENV, "verify_snapshot"),
                mock.patch.object(AGENT_ENV.subprocess, "run", side_effect=fake_run),
                redirect_stdout(io.StringIO()),
            ):
                candidate = AGENT_ENV.stage_skills(snapshot)

            for name in ("catalog-skill", "council", ".system", ".external-skills.json", ".private-skills.record"):
                self.assertTrue((candidate / name).exists(), name)
            self.assertTrue((candidate / "tool-managed").is_symlink())
            self.assertIn("--checked-in-only", commands[-1])


class PrivateUpdateTests(unittest.TestCase):
    def test_private_update_failure_warns_and_does_not_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            dev_root = Path(temporary)
            for key in ("dotfiles", "skills", "skills-private", "codex-stuff"):
                (dev_root / key / ".git").mkdir(parents=True)
            ctx = context(dry_run=False, dev_root=dev_root)
            calls = []
            def fake_update(repo, runner, env=None):
                calls.append((repo.name, env))
                if repo.name == "skills-private":
                    raise subprocess.CalledProcessError(128, ["git", "fetch"])
            with mock.patch.object(ACTIONS, "update_repo", side_effect=fake_update), redirect_stdout(io.StringIO()) as output:
                ACTIONS.update_existing_repositories(ctx, CORE.Runner(False))
            private_env = dict(calls)["skills-private"]
            self.assertEqual(private_env["GIT_TERMINAL_PROMPT"], "0")
            self.assertIn("Skipping private skills update", output.getvalue())
            self.assertIn("codex-stuff", dict(calls))


class ClaudeAndPrivateSkillsTests(unittest.TestCase):
    def test_claude_commands_run_through_mise(self) -> None:
        ctx = context()
        output = io.StringIO()
        with mock.patch.object(ACTIONS, "known_claude_marketplaces", return_value=set()), redirect_stdout(output):
            ACTIONS.install_claude(ctx, CORE.Runner(True))
        plugin_lines = [line for line in output.getvalue().splitlines() if "plugin" in line]
        self.assertTrue(plugin_lines)
        self.assertTrue(all("mise exec claude -- claude plugin" in line for line in plugin_lines))

    def test_private_clone_cannot_wait_for_a_password(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ctx = context(dry_run=False, dev_root=Path(temporary))
            runner = mock.Mock()
            runner.run.side_effect = subprocess.CalledProcessError(128, ["git", "clone"])
            with redirect_stdout(io.StringIO()) as output:
                ACTIONS.install_private_skills(ctx, runner, "install")
            clone_env = runner.run.call_args.kwargs["env"]
            self.assertEqual(clone_env["GIT_TERMINAL_PROMPT"], "0")
            self.assertIn("Skipping private skills", output.getvalue())

    def test_dry_run_previews_dotfiles_without_a_status_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            dev_root = Path(temporary)
            installer = dev_root / "dotfiles/scripts/install.sh"
            installer.parent.mkdir(parents=True)
            (dev_root / "dotfiles/.git").mkdir()
            installer.write_text('echo "dry=$DOTFILES_DRY_RUN status=${DOTFILES_STATUS_FILE:-none}"\n')
            ctx = context(dry_run=True, dev_root=dev_root)
            result = subprocess.run
            with mock.patch.object(ACTIONS.subprocess, "run", wraps=result) as run:
                ACTIONS.install_dotfiles(ctx, CORE.Runner(True))
            env = run.call_args.kwargs["env"]
            self.assertEqual(env["DOTFILES_DRY_RUN"], "1")
            self.assertNotIn("DOTFILES_STATUS_FILE", env)


class SelfUpdateTests(unittest.TestCase):
    def test_smart_update_stops_when_new_mac_is_behind(self) -> None:
        with (
            mock.patch.object(ACTIONS, "git_output", side_effect=["origin/main", "3"]),
            mock.patch.object(ACTIONS.subprocess, "run"),
            self.assertRaises(SystemExit) as stop,
        ):
            ACTIONS.require_current_new_mac()
        self.assertIn("3 commit(s) behind", str(stop.exception))


if __name__ == "__main__":
    unittest.main()
