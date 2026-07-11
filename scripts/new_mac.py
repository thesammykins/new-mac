#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from new_mac_actions import (
    apply,
    audit,
    check,
    doctor,
    install_agents,
    install_brew,
    install_dotfiles,
    install_plugins,
    install_skills,
    smart_update,
    verify_repair,
    verify_skills,
)
from new_mac_core import Runner, available_profiles, build_context, print_plan
from agent_environment import restore_snapshot, verify_snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Profile-driven Mac setup orchestrator.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_flags(target: argparse.ArgumentParser) -> None:
        target.add_argument("--profile", choices=available_profiles(), default="personal")
        target.add_argument("--mode", choices=["interactive", "assume-defaults", "ci"], default=None)
        target.add_argument("--with", dest="with_components", default="")
        target.add_argument("--skip", dest="skip_components", default="")
        target.add_argument("--dry-run", action="store_true")
        target.add_argument("--yes", action="store_true")
        target.add_argument("--dev-root", default=None)
        target.add_argument("--json", dest="json_output", action="store_true")

    for name in (
        "doctor",
        "plan",
        "apply",
        "install-brew",
        "install-dotfiles",
        "install-agents",
        "install-skills",
        "install-plugins",
        "check",
        "smart-update",
        "verify-repair",
        "verify-skills",
        "audit",
    ):
        add_common_flags(subparsers.add_parser(name))
    verify = subparsers.add_parser("verify-snapshot")
    verify.add_argument("snapshot")
    restore = subparsers.add_parser("restore-snapshot")
    restore.add_argument("snapshot")
    restore.add_argument("--yes", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "verify-snapshot":
        verify_snapshot(Path(args.snapshot).expanduser().resolve())
        return
    if args.command == "restore-snapshot":
        if not args.yes:
            raise SystemExit("restore-snapshot requires --yes")
        restore_snapshot(Path(args.snapshot).expanduser().resolve())
        return
    forced = {
        "install-brew": ["brew"],
        "install-dotfiles": ["dotfiles"],
        "install-agents": ["agents"],
        "install-skills": ["skills"],
        "install-plugins": ["codex-stuff"],
    }.get(args.command)
    ctx = build_context(args, forced_components=forced)

    match args.command:
        case "doctor":
            doctor(ctx)
        case "plan":
            print_plan(ctx)
        case "apply":
            apply(ctx)
        case "install-brew":
            install_brew(ctx, Runner(ctx.dry_run))
        case "install-dotfiles":
            install_dotfiles(ctx, Runner(ctx.dry_run))
        case "install-agents":
            install_agents(ctx, Runner(ctx.dry_run))
        case "install-skills":
            install_skills(ctx, Runner(ctx.dry_run))
        case "install-plugins":
            install_plugins(ctx, Runner(ctx.dry_run))
        case "check":
            check(ctx)
        case "smart-update":
            smart_update(ctx)
        case "verify-repair":
            verify_repair(ctx)
        case "verify-skills":
            verify_skills(ctx, Runner(ctx.dry_run))
        case "audit":
            audit(ctx)
        case _:
            raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
