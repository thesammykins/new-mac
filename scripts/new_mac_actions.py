from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from dataclasses import replace
from datetime import datetime
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
    save_profile,
)


def require_confirmation(ctx: Context) -> None:
    if ctx.dry_run or ctx.yes or ctx.mode != "interactive":
        return
    response = input(f"Apply profile '{ctx.profile}' to this Mac? [y/N] ").strip().lower()
    if response not in {"y", "yes"}:
        raise SystemExit("Aborted.")


def ensure_repo(ctx: Context, runner: Runner, key: str, env: dict[str, str] | None = None) -> Path:
    target = repo_path(ctx, key)
    url = repo_url(ctx, key)
    if not url:
        raise SystemExit(f"No repo URL configured for {key}")

    if (target / ".git").exists():
        return target

    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"Repository target exists but is not a Git checkout: {target}")

    if ctx.dry_run:
        runner.run(["mkdir", "-p", str(target.parent)])
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
    runner.run(["git", "clone", url, str(target)], env=env)
    return target


def git_output(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def update_repo(repo: Path, runner: Runner, env: dict[str, str] | None = None) -> None:
    if git_output(repo, "status", "--porcelain"):
        raise SystemExit(f"Refusing to update repository with uncommitted changes: {repo}")

    try:
        upstream = git_output(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"Repository has no configured upstream branch: {repo}") from error
    remote = upstream.split("/", 1)[0]
    runner.run(["git", "-C", str(repo), "fetch", "--prune", remote], env=env)
    if runner.dry_run:
        return

    ahead_text, behind_text = git_output(repo, "rev-list", "--left-right", "--count", f"HEAD...{upstream}").split()
    ahead, behind = int(ahead_text), int(behind_text)
    if ahead:
        state = "diverged from" if behind else "ahead of"
        raise SystemExit(f"Refusing to update repository {state} {upstream}: {repo}")
    if not behind:
        print(f"Repository already current: {repo}")
        return
    runner.run(["git", "-C", str(repo), "merge", "--ff-only", upstream])


def update_existing_repositories(ctx: Context, runner: Runner) -> None:
    keys: list[str] = []
    if "brew" in ctx.components or "dotfiles" in ctx.components:
        keys.append("dotfiles")
    if "skills" in ctx.components:
        keys.append("skills")
        # Only update the private checkout if this Mac already has it.
        if repo_url(ctx, "skills-private") and (repo_path(ctx, "skills-private") / ".git").exists():
            keys.append("skills-private")
    if "codex-stuff" in ctx.components:
        keys.append("codex-stuff")

    for key in keys:
        target = ensure_repo(ctx, runner, key)
        if not (target / ".git").exists() or ctx.dry_run:
            continue
        if key == "skills-private":
            # Optional, like its install: never wait for credentials, and a
            # failed update warns instead of stopping Smart Update.
            try:
                update_repo(target, runner, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
            except (subprocess.CalledProcessError, SystemExit) as error:
                print(f"Skipping private skills update: {error}")
            continue
        update_repo(target, runner)


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
    if ctx.dry_run and (dotfiles / "scripts/install.sh").is_file():
        env.pop("DOTFILES_STATUS_FILE")
        # The installer's DOTFILES_DRY_RUN mode changes nothing, so run it to
        # show which files would be linked or backed up.
        subprocess.run(["bash", str(dotfiles / "scripts/install.sh")], env=env, check=True)
    else:
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
    # Without credentials git would wait for a username; fail fast instead.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        private = ensure_repo(ctx, runner, "skills-private", env=env)
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


def link_into_place(path: Path, target: Path, runner: Runner) -> None:
    # Point a Claude config path at the shared copy. Anything already there that
    # isn't that link is kept beside it as a dated backup, never deleted.
    if path.is_symlink() and path.resolve() == target.resolve():
        return
    if path.exists() or path.is_symlink():
        backup = path.with_name(f"{path.name}.backup-{datetime.now():%Y%m%d%H%M%S}")
        runner.run(["mv", str(path), str(backup)])
    runner.run(["mkdir", "-p", str(path.parent)])
    runner.run(["ln", "-s", str(target), str(path)])


def install_claude(ctx: Context, runner: Runner) -> None:
    # Claude Code is the one global mise tool (dotfiles' mise config). Its
    # instructions and skills are the shared ~/.agents copies, like Codex's.
    if shutil.which("mise") is None and not ctx.dry_run:
        raise SystemExit("mise is required to install Claude Code; install the dev Brewfile tier first.")
    runner.run(["mise", "install", "claude"], cwd=Path.home())
    home = Path.home()
    link_into_place(home / ".claude/CLAUDE.md", home / ".agents/AGENTS.md", runner)
    link_into_place(home / ".claude/skills", home / ".agents/skills", runner)
    # This process's PATH predates the install, so run claude through mise.
    claude = ["mise", "exec", "claude", "--", "claude"]
    known = known_claude_marketplaces(claude)
    for marketplace in ctx.config.get("claude_marketplaces", []):
        # Adding a marketplace twice fails, so setup only adds missing ones.
        if marketplace not in known:
            runner.run([*claude, "plugin", "marketplace", "add", marketplace], cwd=home)
    for plugin in ctx.config.get("claude_plugins", []):
        runner.run([*claude, "plugin", "install", plugin], cwd=home)


def known_claude_marketplaces(claude: list[str]) -> set[str]:
    if shutil.which("mise") is None:
        return set()
    result = subprocess.run([*claude, "plugin", "marketplace", "list", "--json"], capture_output=True, text=True, cwd=Path.home())
    if result.returncode != 0:
        return set()
    return {entry.get("url") or entry.get("repo") for entry in json.loads(result.stdout)}


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
    if "claude" in ctx.components:
        install_claude(ctx, runner)
    if not ctx.dry_run:
        save_profile(ctx.profile)


def newest_verified_snapshot(root: Path | None = None) -> Path:
    snapshot_root = root or Path.home() / "Backups/agent-environment"
    snapshots = sorted(
        (path for path in snapshot_root.glob("*") if path.is_dir() and (path / "VERIFIED").is_file()),
        reverse=True,
    )
    if not snapshots:
        raise SystemExit("snapshot command completed without producing a verified snapshot")
    return snapshots[0]


def require_current_new_mac() -> None:
    # Smart Update applies whatever this checkout says, so an outdated copy on
    # a second Mac would apply old logic. Ask for a pull rather than updating
    # the code that is already running.
    if not (REPO_ROOT / ".git").exists():
        return
    try:
        upstream = git_output(REPO_ROOT, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
        subprocess.run(["git", "-C", str(REPO_ROOT), "fetch", "--quiet", upstream.split("/", 1)[0]], check=True)
        behind = int(git_output(REPO_ROOT, "rev-list", "--count", f"HEAD..{upstream}"))
    except (subprocess.CalledProcessError, ValueError):
        print("Could not check whether new-mac is up to date; continuing.")
        return
    if behind:
        raise SystemExit(f"new-mac is {behind} commit(s) behind {upstream}. Run `git -C {REPO_ROOT} pull --ff-only`, then rerun.")


def smart_update(ctx: Context) -> None:
    runner = Runner(ctx.dry_run)
    if not ctx.dry_run:
        require_current_new_mac()
    runner.run(["mise", "exec", "--", "python", str(REPO_ROOT / "scripts/snapshot_agent_environment.py")])
    if ctx.dry_run:
        print("[dry-run] snapshot verification, safe apply, and doctor would follow")
        return
    snapshot = newest_verified_snapshot()
    runner.run(
        ["mise", "exec", "--", "python", str(REPO_ROOT / "scripts/agent_environment.py"), "verify-snapshot", str(snapshot)]
    )
    update_existing_repositories(ctx, runner)
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
        "commands": [command_status(name) for name in ("git", "brew", "mise", "python3", "codex", "claude", "opencode", "mas")],
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
