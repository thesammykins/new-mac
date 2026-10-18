from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

from new_mac_core import (
    Context,
    PROFILE_DIR,
    REPO_ROOT,
    Runner,
    available_profiles,
    command_status,
    load_profile,
    plan_document,
    print_plan,
    repo_path,
    repo_url,
    resolve_components,
)


def require_confirmation(ctx: Context) -> None:
    if ctx.dry_run or ctx.yes or ctx.mode != "interactive":
        return
    response = input(f"Apply profile '{ctx.profile}' to this Mac? [y/N] ").strip().lower()
    if response not in {"y", "yes"}:
        raise SystemExit("Aborted.")


def ensure_repo(ctx: Context, runner: Runner, key: str) -> Path:
    target = repo_path(ctx, key)
    url = repo_url(ctx, key)
    if not url:
        raise SystemExit(f"No repo URL configured for {key}")

    if (target / ".git").exists():
        runner.run(["git", "-C", str(target), "pull", "--ff-only"])
        return target

    if ctx.dry_run:
        runner.run(["mkdir", "-p", str(target.parent)])
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
    runner.run(["git", "clone", url, str(target)])
    return target


def install_agents(ctx: Context, runner: Runner) -> None:
    for relative in (".agents", ".agents/skills", ".agents/commands", ".agents/hooks"):
        path = Path.home() / relative
        if ctx.dry_run:
            runner.run(["mkdir", "-p", str(path)])
        else:
            path.mkdir(parents=True, exist_ok=True)
            print(f"created {path}")


def install_codex_cli(ctx: Context, runner: Runner) -> None:
    if shutil.which("brew") is None and not ctx.dry_run:
        raise SystemExit("Homebrew is required to install Codex.")
    runner.run(["brew", "install", "--cask", "codex"])


def install_opencode_cli(ctx: Context, runner: Runner) -> None:
    if shutil.which("brew") is None and not ctx.dry_run:
        raise SystemExit("Homebrew is required to install OpenCode.")
    runner.run(["brew", "install", "opencode"])


def install_brew(ctx: Context, runner: Runner) -> None:
    dotfiles = ensure_repo(ctx, runner, "dotfiles")
    brewfiles = ctx.config.get("brewfiles", [])
    for brewfile_name in brewfiles:
        if not (dotfiles / brewfile_name).exists() and not ctx.dry_run:
            raise SystemExit(f"Missing Brewfile: {dotfiles / brewfile_name}")
    if brewfiles:
        # dotfiles' tier script trusts the Brewfiles' third-party taps before
        # installing; Homebrew refuses formulae from untrusted taps.
        runner.run(["bash", str(dotfiles / "scripts/brew-tiers.sh"), "install", *brewfiles])


def install_dotfiles(ctx: Context, runner: Runner) -> None:
    dotfiles = ensure_repo(ctx, runner, "dotfiles")
    status_file = Path.home() / ".cache/new-mac/dotfiles-status.json"
    if not ctx.dry_run:
        status_file.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({key: str(value) for key, value in ctx.config.get("dotfiles_env", {}).items()})
    env["DOTFILES_WORKTREE"] = str(dotfiles)
    env["DOTFILES_ROOT"] = str(dotfiles)
    env["DOTFILES_DRY_RUN"] = "1" if ctx.dry_run else env.get("DOTFILES_DRY_RUN", "0")
    env["DOTFILES_INSTALL_BREW"] = "0"
    env["DOTFILES_STATUS_FILE"] = str(status_file)
    if "defaults" in ctx.components:
        env["DOTFILES_APPLY_MACOS_DEFAULTS"] = "1"
    runner.run(["bash", str(dotfiles / "scripts/install.sh")], env=env)
    if not ctx.dry_run and status_file.is_file():
        payload = json.loads(status_file.read_text(encoding="utf-8"))
        counts = ", ".join(f"{key}={len(payload[key])}" for key in ("linked", "installed", "skipped", "outdated", "failed"))
        print(f"Dotfiles status: {payload['result']} ({counts})")


def install_skills(ctx: Context, runner: Runner) -> None:
    skills = ensure_repo(ctx, runner, "skills")
    installer = ["mise", "exec", "--", "python", str(skills / "scripts/install-skills.py")]
    runner.run([*installer, "install", *(["--dry-run"] if ctx.dry_run else [])])
    # External skills are pinned upstream sources; without --apply the
    # installer only previews the commands.
    runner.run([*installer, "external", *([] if ctx.dry_run else ["--apply"])])
    install_private_skills(ctx, runner, "install")


def install_private_skills(ctx: Context, runner: Runner, mode: str) -> None:
    # Personal skills live in a private repository. A Mac without access to it
    # still gets every public skill, so a failed clone only warns.
    if not repo_url(ctx, "skills-private"):
        return
    try:
        private = ensure_repo(ctx, runner, "skills-private")
    except subprocess.CalledProcessError:
        print("Skipping private skills: could not clone the private skills repository.")
        return
    runner.run(["bash", str(private / "scripts/install.sh"), mode])


def verify_skills(ctx: Context, runner: Runner) -> None:
    skills = repo_path(ctx, "skills")
    if not (skills / ".git").exists() and not ctx.dry_run:
        raise SystemExit(f"Skills checkout is missing: {skills}")
    runner.run(["mise", "exec", "--", "python", str(skills / "scripts/install-skills.py"), "verify"])
    install_private_skills(ctx, runner, "verify")


def install_plugins(ctx: Context, runner: Runner) -> None:
    ensure_repo(ctx, runner, "codex-stuff")
    runner.run(["codex", "plugin", "marketplace", "add", "thesammykins/codex-stuff", "--ref", "main"])
    for plugin in ctx.config.get("codex_plugins", []):
        identifier = plugin if "@" in plugin else f"{plugin}@codex-stuff"
        runner.run(["codex", "plugin", "add", identifier])


def apply(ctx: Context) -> None:
    runner = Runner(ctx.dry_run)
    require_confirmation(ctx)
    print_plan(ctx)
    print("")

    if "agents" in ctx.components:
        install_agents(ctx, runner)
    if "brew" in ctx.components:
        install_brew(ctx, runner)
    if "dotfiles" in ctx.components:
        install_dotfiles(ctx, runner)
    if "codex" in ctx.components:
        install_codex_cli(ctx, runner)
    if "opencode" in ctx.components:
        install_opencode_cli(ctx, runner)
    if "skills" in ctx.components:
        install_skills(ctx, runner)
    if "codex-stuff" in ctx.components:
        install_plugins(ctx, runner)


def newest_verified_snapshot(root: Path | None = None) -> Path:
    snapshot_root = root or Path.home() / "Backups/agent-environment"
    snapshots = sorted(
        (path for path in snapshot_root.glob("*") if path.is_dir() and (path / "VERIFIED").is_file()),
        reverse=True,
    )
    if not snapshots:
        raise SystemExit("snapshot command completed without producing a verified snapshot")
    return snapshots[0]


def smart_update(ctx: Context) -> None:
    runner = Runner(ctx.dry_run)
    runner.run(["mise", "exec", "--", "python", str(REPO_ROOT / "scripts/snapshot_agent_environment.py")])
    if ctx.dry_run:
        print("[dry-run] snapshot verification, safe apply, and doctor would follow")
        return
    snapshot = newest_verified_snapshot()
    runner.run(
        ["mise", "exec", "--", "python", str(REPO_ROOT / "scripts/agent_environment.py"), "verify-snapshot", str(snapshot)]
    )
    apply(replace(ctx, yes=True))
    doctor(ctx)
    print(f"Smart Update complete. Verified rollback snapshot: {snapshot}")


def verify_repair(ctx: Context) -> None:
    check(ctx)
    smart_update(ctx)
    verify_skills(ctx, Runner(ctx.dry_run))


def audit(ctx: Context) -> None:
    check(ctx)
    runner = Runner(ctx.dry_run)
    checks = (
        (repo_path(ctx, "skills"), ["mise", "run", "check"]),
        (repo_path(ctx, "dotfiles"), ["mise", "run", "check"]),
        (repo_path(ctx, "dotfiles"), ["mise", "run", "audit"]),
    )
    for cwd, command in checks:
        if not cwd.is_dir() and not ctx.dry_run:
            raise SystemExit(f"Required checkout is missing: {cwd}")
        runner.run(command, cwd=cwd)
    print("Repository audit complete.")


def doctor(ctx: Context) -> None:
    payload: dict[str, Any] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "dev_root": str(ctx.dev_root),
        "commands": [command_status(name) for name in ("git", "brew", "mise", "python3", "codex", "opencode", "mas")],
        "repos": plan_document(ctx)["repos"],
        "agents_skills": str(Path.home() / ".agents/skills"),
        "codex_skills": str(Path.home() / ".codex/skills"),
    }
    if ctx.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"Platform: {payload['platform']}")
    print(f"Machine: {payload['machine']}")
    print(f"Dev root: {payload['dev_root']}")
    print("")
    print("Commands:")
    for item in payload["commands"]:
        status = item["path"] if item["found"] else "missing"
        print(f"  - {item['command']}: {status}")
    print("")
    print("Repos:")
    for name, details in payload["repos"].items():
        state = "present" if details["exists"] else "missing"
        print(f"  - {name}: {details['path']} ({state})")


def check(_: Context) -> None:
    problems: list[str] = []
    for profile in available_profiles():
        try:
            config = load_profile(profile)
            resolve_components(config, None, None)
        except Exception as error:  # noqa: BLE001 - validation should report all profile failures.
            problems.append(f"{profile}: {error}")

    required_files = [
        REPO_ROOT / "setup.sh",
        REPO_ROOT / "scripts/new_mac.py",
        REPO_ROOT / "scripts/agent_environment.py",
        REPO_ROOT / "scripts/snapshot_agent_environment.py",
        PROFILE_DIR / "common.toml",
    ]
    for path in required_files:
        if not path.exists():
            problems.append(f"missing {path}")

    expected_plugins = {"arxiv-research", "local-ci-signoff", "prompt-rewriter", "codex-plugin-publisher", "chief-of-staff"}
    for profile in ("personal", "agent-dev"):
        missing_plugins = expected_plugins - set(load_profile(profile).get("codex_plugins", []))
        if missing_plugins:
            problems.append(f"{profile}: missing Codex plugins {', '.join(sorted(missing_plugins))}")

    if problems:
        print("Check failed:")
        for problem in problems:
            print(f"  - {problem}")
        raise SystemExit(1)
    print("new-mac checks passed")
