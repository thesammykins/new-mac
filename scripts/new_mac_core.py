from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = REPO_ROOT / "profiles"

COMPONENT_ALIASES = {"plugins": "codex-stuff"}
COMPONENT_ORDER = [
    "agents",
    "brew",
    "dotfiles",
    "codex",
    "claude",
    "opencode",
    "skills",
    "codex-stuff",
    "defaults",
    "mas",
]
VALID_COMPONENTS = set(COMPONENT_ORDER)


@dataclass(frozen=True)
class Context:
    profile: str
    mode: str
    dev_root: Path
    config: dict[str, Any]
    components: list[str]
    dry_run: bool
    yes: bool
    json_output: bool


class Runner:
    def __init__(self, dry_run: bool) -> None:
        self.dry_run = dry_run

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        printable = " ".join(args)
        if cwd is not None:
            printable = f"(cd {cwd} && {printable})"
        if self.dry_run:
            print(f"[dry-run] {printable}")
            return
        subprocess.run(args, cwd=cwd, env=dict(env) if env is not None else None, check=True)


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def available_profiles() -> list[str]:
    return sorted(path.stem for path in PROFILE_DIR.glob("*.toml") if path.stem != "common")


def load_profile(profile: str) -> dict[str, Any]:
    common = load_toml(PROFILE_DIR / "common.toml")
    profile_path = PROFILE_DIR / f"{profile}.toml"
    if not profile_path.exists():
        valid = ", ".join(available_profiles())
        raise SystemExit(f"Unknown profile '{profile}'. Expected one of: {valid}")
    return merge_dicts(common, load_toml(profile_path))


def expand_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def normalize_component(name: str) -> str:
    normalized = COMPONENT_ALIASES.get(name, name)
    if normalized not in VALID_COMPONENTS:
        valid = ", ".join(sorted(VALID_COMPONENTS | set(COMPONENT_ALIASES)))
        raise SystemExit(f"Unknown component '{name}'. Expected one of: {valid}")
    return normalized


def resolve_components(config: dict[str, Any], include: str | None, skip: str | None) -> list[str]:
    selected = {normalize_component(item) for item in config.get("default_components", [])}
    selected.update(normalize_component(item) for item in split_csv(include))
    selected.difference_update(normalize_component(item) for item in split_csv(skip))
    return [component for component in COMPONENT_ORDER if component in selected]


def build_context(args: Any, forced_components: list[str] | None = None) -> Context:
    config = load_profile(args.profile)
    mode = args.mode or str(config.get("default_mode", "interactive"))
    dev_root = expand_path(args.dev_root or str(config.get("dev_root", "~/Development")))
    dry_run = bool(args.dry_run or mode == "ci")
    components = forced_components or resolve_components(config, args.with_components, args.skip_components)
    return Context(
        profile=args.profile,
        mode=mode,
        dev_root=dev_root,
        config=config,
        components=components,
        dry_run=dry_run,
        yes=bool(args.yes),
        json_output=bool(args.json_output),
    )


def repo_path(ctx: Context, key: str) -> Path:
    configured = ctx.config.get("paths", {}).get(key, key)
    return ctx.dev_root / configured


def repo_url(ctx: Context, key: str) -> str:
    return str(ctx.config.get("repos", {}).get(key, ""))


def command_status(command: str) -> dict[str, Any]:
    path = shutil.which(command)
    if path is None:
        return {"command": command, "found": False, "path": None}
    return {"command": command, "found": True, "path": path}


def plan_document(ctx: Context) -> dict[str, Any]:
    repos = {
        key: {
            "url": repo_url(ctx, key),
            "path": str(repo_path(ctx, key)),
            "exists": (repo_path(ctx, key) / ".git").exists(),
        }
        for key in ("dotfiles", "skills", "skills-private", "codex-stuff")
    }
    return {
        "profile": ctx.profile,
        "mode": ctx.mode,
        "dry_run": ctx.dry_run,
        "dev_root": str(ctx.dev_root),
        "components": ctx.components,
        "brewfiles": ctx.config.get("brewfiles", []),
        "codex_plugins": ctx.config.get("codex_plugins", []),
        "claude_plugins": ctx.config.get("claude_plugins", []),
        "repos": repos,
    }


def print_plan(ctx: Context) -> None:
    plan = plan_document(ctx)
    if ctx.json_output:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return

    print(f"Profile: {plan['profile']}")
    print(f"Mode: {plan['mode']}")
    print(f"Dry run: {plan['dry_run']}")
    print(f"Dev root: {plan['dev_root']}")
    print("Components: " + ", ".join(plan["components"]))
    print("Brewfiles: " + ", ".join(plan["brewfiles"]))
    print("Skills: complete desired inventory")
    print("Codex plugins: " + ", ".join(plan["codex_plugins"]))
    print("Claude plugins: " + ", ".join(plan["claude_plugins"]))
    print("")
    print("Repos:")
    for name, details in plan["repos"].items():
        state = "present" if details["exists"] else "missing"
        print(f"  - {name}: {details['path']} ({state})")
