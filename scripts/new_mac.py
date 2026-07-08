#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess

from new_mac_actions import (
    apply,
    check,
    doctor,
    install_agents,
    install_brew,
    install_dotfiles,
    install_plugins,
    install_skills,
)
from new_mac_core import Runner, available_profiles, build_context, print_plan


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
    ):
        add_common_flags(subparsers.add_parser(name))
    return parser


def main() -> None:
    args = build_parser().parse_args()
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
        case _:
            raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error

