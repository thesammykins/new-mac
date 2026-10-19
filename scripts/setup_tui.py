#!/usr/bin/env python3
from __future__ import annotations

import curses
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKUP_ROOT = Path.home() / "Backups/agent-environment"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from new_mac_core import PROFILE_STATE, save_profile, saved_profile  # noqa: E402


@dataclass(frozen=True)
class MenuItem:
    label: str
    action: str


MAIN_MENU = (
    MenuItem("Smart Update", "smart-update"),
    MenuItem("Set Up or Change This Mac", "setup"),
    MenuItem("Verify and Repair", "verify-repair"),
    MenuItem("Manage Skills", "skills"),
    MenuItem("Backups and Rollback", "backups"),
    MenuItem("Advanced", "advanced"),
    MenuItem("Exit", "exit"),
)

PROFILE_MENU = (
    MenuItem("Personal", "personal"),
    MenuItem("Work", "work"),
    MenuItem("Minimal", "minimal"),
    MenuItem("Agent Development", "agent-dev"),
    MenuItem("CI Runner", "ci"),
)

SKILLS_MENU = (
    MenuItem("Synchronize all skills", "sync-skills"),
    MenuItem("Verify installed skills", "verify-skills"),
    MenuItem("Back", "back"),
)

ADVANCED_MENU = (
    MenuItem("Doctor", "doctor"),
    MenuItem("Audit repositories", "audit"),
    MenuItem("Preview personal setup", "preview"),
    MenuItem("Back", "back"),
)


def move_selection(index: int, key: int, size: int) -> int:
    if key in (curses.KEY_UP, ord("k")):
        return (index - 1) % size
    if key in (curses.KEY_DOWN, ord("j")):
        return (index + 1) % size
    return index


def is_fresh_mac(home: Path = Path.home()) -> bool:
    return not (home / ".agents/skills").is_dir()


def verified_snapshots(root: Path = BACKUP_ROOT) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        (path for path in root.iterdir() if path.is_dir() and (path / "VERIFIED").is_file()),
        reverse=True,
    )


def prompt_menu(
    title: str,
    items: tuple[MenuItem, ...],
    *,
    input_fn: Callable[[str], str] = input,
    output: TextIO = sys.stdout,
) -> str:
    print(f"\n{title}", file=output)
    for number, item in enumerate(items, start=1):
        suffix = " (default)" if number == 1 else ""
        print(f"  {number}. {item.label}{suffix}", file=output)
    while True:
        response = input_fn("Choose an option [1]: ").strip()
        if not response:
            return items[0].action
        if response.lower() in {"q", "quit"}:
            return "exit"
        if response.isdigit() and 1 <= int(response) <= len(items):
            return items[int(response) - 1].action
        print("Please enter one of the listed numbers.", file=output)


def curses_menu(screen: curses.window, title: str, items: tuple[MenuItem, ...]) -> str:
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    screen.keypad(True)
    index = 0
    while True:
        screen.erase()
        height, width = screen.getmaxyx()
        screen.addnstr(1, 2, title, max(1, width - 4), curses.A_BOLD)
        screen.addnstr(2, 2, "Arrow keys or j/k · Enter to select · Esc/q to go back", max(1, width - 4))
        for row, item in enumerate(items, start=4):
            marker = "› " if row - 4 == index else "  "
            style = curses.A_REVERSE if row - 4 == index else curses.A_NORMAL
            if row < height - 1:
                screen.addnstr(row, 2, marker + item.label, max(1, width - 4), style)
        screen.refresh()
        key = screen.getch()
        if key in (10, 13, curses.KEY_ENTER):
            return items[index].action
        if key in (27, ord("q")):
            return "back"
        index = move_selection(index, key, len(items))


def choose(title: str, items: tuple[MenuItem, ...], interactive: bool) -> str:
    if interactive:
        return curses.wrapper(curses_menu, title, items)
    return prompt_menu(title, items)


def run_backend(*arguments: str) -> bool:
    command = [sys.executable, str(REPO_ROOT / "scripts/new_mac.py"), *arguments]
    print("\n" + "─" * 72)
    completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
    print("─" * 72)
    if completed.returncode == 0:
        print("Completed successfully.")
        return True
    print(f"Action failed with exit code {completed.returncode}.")
    return False


def confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N] ").strip().lower() in {"y", "yes"}


def choose_snapshot(interactive: bool) -> Path | None:
    snapshots = verified_snapshots()
    if not snapshots:
        print("No verified snapshots are available.")
        return None
    items = tuple(MenuItem(path.name, str(path)) for path in snapshots) + (MenuItem("Back", "back"),)
    selected = choose("Verified snapshots", items, interactive)
    return None if selected == "back" else Path(selected)


def run_setup(interactive: bool, *, existing_mac: bool = False) -> None:
    profile = choose("Choose a setup profile", PROFILE_MENU, interactive)
    if profile == "back":
        return
    run_backend("plan", "--profile", profile)
    if not confirm(f"Apply the {profile} plan shown above?"):
        return
    # An existing Mac goes through Smart Update so a verified snapshot is taken
    # and repositories are updated before anything is applied.
    command = "smart-update" if existing_mac else "apply"
    if run_backend(command, "--profile", profile, "--yes"):
        save_profile(profile)


def manage_skills(interactive: bool) -> None:
    while True:
        action = choose("Manage Skills", SKILLS_MENU, interactive)
        if action in {"back", "exit"}:
            return
        if action == "sync-skills":
            run_backend("install-skills", "--yes")
        elif action == "verify-skills":
            run_backend("verify-skills")


def manage_backups(interactive: bool) -> None:
    snapshots = verified_snapshots()
    items = (
        MenuItem(f"List verified snapshots ({len(snapshots)})", "list"),
        MenuItem("Verify a snapshot", "verify"),
        MenuItem("Roll back from a snapshot", "rollback"),
        MenuItem("Back", "back"),
    )
    while True:
        action = choose("Backups and Rollback", items, interactive)
        if action in {"back", "exit"}:
            return
        if action == "list":
            if snapshots:
                print("\n".join(path.name for path in snapshots))
            else:
                print("No verified snapshots are available.")
        elif action == "verify":
            snapshot = choose_snapshot(interactive)
            if snapshot:
                run_backend("verify-snapshot", str(snapshot))
        elif action == "rollback":
            snapshot = choose_snapshot(interactive)
            if snapshot and confirm(f"Restore .agents from {snapshot.name}? The current state will be retained"):
                run_backend("restore-snapshot", str(snapshot), "--yes")


def advanced(interactive: bool) -> None:
    while True:
        action = choose("Advanced", ADVANCED_MENU, interactive)
        if action in {"back", "exit"}:
            return
        if action == "doctor":
            run_backend("doctor")
        elif action == "audit":
            run_backend("audit")
        elif action == "preview":
            profile = saved_profile() or choose("Preview which profile?", PROFILE_MENU, interactive)
            if profile != "back":
                run_backend("plan", "--profile", profile, "--dry-run")


def main() -> None:
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    while True:
        action = choose("New Mac Setup", MAIN_MENU, interactive)
        if action in {"exit", "back"}:
            return
        if action == "smart-update":
            # A fresh Mac, or one never set up through new-mac, picks a profile
            # and reviews its plan first.
            if is_fresh_mac() or not saved_profile():
                run_setup(interactive, existing_mac=not is_fresh_mac())
            else:
                run_backend("smart-update", "--profile", saved_profile(), "--yes")
        elif action == "setup":
            run_setup(interactive, existing_mac=not is_fresh_mac())
        elif action == "verify-repair":
            if saved_profile():
                run_backend("verify-repair", "--profile", saved_profile(), "--yes")
            else:
                print("No profile is recorded for this Mac yet; choose one first.")
                run_setup(interactive, existing_mac=not is_fresh_mac())
        elif action == "skills":
            manage_skills(interactive)
        elif action == "backups":
            manage_backups(interactive)
        elif action == "advanced":
            advanced(interactive)


if __name__ == "__main__":
    main()
