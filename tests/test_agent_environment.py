from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("agent_environment", ROOT / "scripts/agent_environment.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
sys.path.insert(0, str(ROOT / "scripts"))
import new_mac_actions as ACTIONS  # noqa: E402
from new_mac_core import Context, Runner  # noqa: E402


class AgentEnvironmentTests(unittest.TestCase):
    def test_snapshot_source_may_be_a_real_directory(self) -> None:
        self.assertIn("AGENTS.is_symlink()", (ROOT / "scripts/snapshot_agent_environment.py").read_text())

    def test_orchestrator_never_upgrades_brew_implicitly(self) -> None:
        # Brewfiles install through dotfiles' tier script, which runs
        # `brew bundle install --no-upgrade`; new-mac must not call bundle itself.
        source = (ROOT / "scripts/new_mac_actions.py").read_text()
        self.assertIn('"scripts/brew-tiers.sh"), "install"', source)
        self.assertNotIn('"upgrade"', source)

    def test_existing_repo_is_not_updated_by_install_consumer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "dotfiles"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            ctx = Context(
                profile="personal", mode="interactive", dev_root=root,
                config={"repos": {"dotfiles": "https://example.invalid/dotfiles.git"}},
                components=[], dry_run=True, yes=True, json_output=False,
            )
            runner = mock.Mock(spec=Runner)

            self.assertEqual(repo, ACTIONS.ensure_repo(ctx, runner, "dotfiles"))

            runner.run.assert_not_called()

    def test_repo_update_refuses_dirty_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "dotfiles"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
            (repo / "tracked").write_text("one\n")
            subprocess.run(["git", "-C", str(repo), "add", "tracked"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
            (repo / "tracked").write_text("dirty\n")

            with self.assertRaisesRegex(SystemExit, "uncommitted changes"):
                ACTIONS.update_repo(repo, Runner(False))

    def test_repo_update_fast_forwards_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote = root / "remote.git"
            seed = root / "seed"
            checkout = root / "checkout"
            subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
            subprocess.run(["git", "clone", "-q", str(remote), str(seed)], check=True)
            for repo in (seed,):
                subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
                subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
            (seed / "tracked").write_text("one\n")
            subprocess.run(["git", "-C", str(seed), "add", "tracked"], check=True)
            subprocess.run(["git", "-C", str(seed), "commit", "-qm", "one"], check=True)
            subprocess.run(["git", "-C", str(seed), "push", "-qu", "origin", "HEAD"], check=True)
            subprocess.run(["git", "clone", "-q", str(remote), str(checkout)], check=True)
            (seed / "tracked").write_text("two\n")
            subprocess.run(["git", "-C", str(seed), "commit", "-qam", "two"], check=True)
            subprocess.run(["git", "-C", str(seed), "push", "-q"], check=True)

            ACTIONS.update_repo(checkout, Runner(False))

            self.assertEqual("two\n", (checkout / "tracked").read_text())

    def test_profiles_use_only_brewfiles_for_brew_tiers(self) -> None:
        for profile in (ROOT / "profiles").glob("*.toml"):
            source = profile.read_text()
            self.assertNotIn("DOTFILES_INSTALL_DEV", source)
            self.assertNotIn("DOTFILES_INSTALL_WORKSTATION", source)

    def test_snapshot_failure_aborts_before_apply(self) -> None:
        context = SimpleNamespace(dry_run=False)
        failure = subprocess.CalledProcessError(1, ["snapshot"])
        with (
            mock.patch.object(ACTIONS.Runner, "run", side_effect=failure),
            mock.patch.object(ACTIONS, "require_current_new_mac"),
            mock.patch.object(ACTIONS, "apply") as apply,
            self.assertRaises(subprocess.CalledProcessError),
        ):
            ACTIONS.smart_update(context)
        apply.assert_not_called()

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

    def test_skills_cutover_and_rollback_retain_both_states(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            original_home = MODULE.HOME
            MODULE.HOME = Path(temporary)
            try:
                agents = MODULE.HOME / ".agents"
                live = agents / "skills"
                candidate = agents / "skills.next.snapshot"
                live.mkdir(parents=True)
                candidate.mkdir()
                (live / "old.txt").write_text("old\n")
                (candidate / "new.txt").write_text("new\n")
                (candidate / ".migration-verified").write_text("snapshot\n")

                MODULE.cutover_skills(candidate)
                self.assertTrue((live / "new.txt").is_file())
                self.assertTrue((agents / "skills.bootstrap.snapshot/old.txt").is_file())

                snapshot = MODULE.HOME / "snapshot"
                snapshot.mkdir()
                MODULE.rollback_skills(snapshot)
                self.assertTrue((live / "old.txt").is_file())
                self.assertTrue((agents / "skills.failed.snapshot/new.txt").is_file())
            finally:
                MODULE.HOME = original_home


if __name__ == "__main__":
    unittest.main()
