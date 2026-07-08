from __future__ import annotations

import json
import os
import platform
import shutil
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
    for brewfile_name in ctx.config.get("brewfiles", []):
        brewfile = dotfiles / brewfile_name
        if not brewfile.exists() and not ctx.dry_run:
            raise SystemExit(f"Missing Brewfile: {brewfile}")
        runner.run(["brew", "bundle", "install", f"--file={brewfile}"])


def install_dotfiles(ctx: Context, runner: Runner) -> None:
    dotfiles = ensure_repo(ctx, runner, "dotfiles")
    env = os.environ.copy()
    env.update({key: str(value) for key, value in ctx.config.get("dotfiles_env", {}).items()})
    env["DOTFILES_WORKTREE"] = str(dotfiles)
    env["DOTFILES_ROOT"] = str(dotfiles)
    env["DOTFILES_DRY_RUN"] = "1" if ctx.dry_run else env.get("DOTFILES_DRY_RUN", "0")
    env["DOTFILES_INSTALL_BREW"] = "0"
    env["DOTFILES_INSTALL_MCRN_AI_DEPS"] = "1" if "brew" in ctx.components else "0"
    if "defaults" in ctx.components:
        env["DOTFILES_APPLY_MACOS_DEFAULTS"] = "1"
    runner.run(["bash", str(dotfiles / "scripts/install.sh")], env=env)


def install_skills(ctx: Context, runner: Runner) -> None:
    skills = ensure_repo(ctx, runner, "skills")
    profiles = ",".join(ctx.config.get("skill_profiles", []))
    command = ["python3", str(skills / "scripts/install-skills.py"), "--profile", profiles]
    if ctx.dry_run:
        command.append("--dry-run")
    runner.run(command)


def install_plugins(ctx: Context, runner: Runner) -> None:
    ensure_repo(ctx, runner, "codex-stuff")
    runner.run(["codex", "plugin", "marketplace", "add", "thesammykins/codex-stuff", "--ref", "main"])
    for plugin in ctx.config.get("codex_plugins", []):
        runner.run(["codex", "plugin", "add", f"{plugin}@codex-stuff"])


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
        PROFILE_DIR / "common.toml",
    ]
    for path in required_files:
        if not path.exists():
            problems.append(f"missing {path}")

    if problems:
        print("Check failed:")
        for problem in problems:
            print(f"  - {problem}")
        raise SystemExit(1)
    print("new-mac checks passed")
