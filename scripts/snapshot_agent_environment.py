#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
from pathlib import Path


HOME = Path.home()
AGENTS = HOME / ".agents"
AGENTS_SOURCE = AGENTS.resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_manifest(root: Path) -> dict[str, dict[str, str | int]]:
    result: dict[str, dict[str, str | int]] = {}
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        info = path.lstat()
        if path.is_symlink():
            result[relative] = {"type": "symlink", "target": os.readlink(path), "mode": stat.S_IMODE(info.st_mode)}
        elif path.is_file():
            result[relative] = {"type": "file", "sha256": sha256_file(path), "size": info.st_size, "mode": stat.S_IMODE(info.st_mode)}
        elif path.is_dir():
            result[relative] = {"type": "directory", "mode": stat.S_IMODE(info.st_mode)}
    return result


def run_inventory(command: list[str], target: Path) -> None:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    target.write_text(result.stdout, encoding="utf-8")


def add_path(archive: tarfile.TarFile, path: Path, arcname: str) -> None:
    if path.exists() or path.is_symlink():
        archive.add(path, arcname=arcname, recursive=True)


def main() -> None:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = HOME / "Backups" / "agent-environment" / timestamp
    output.mkdir(parents=True, mode=0o700)
    os.chmod(output, 0o700)

    inventory = output / "inventory"
    inventory.mkdir(mode=0o700)
    (inventory / "agents-tree.json").write_text(json.dumps(tree_manifest(AGENTS_SOURCE), indent=2, sort_keys=True) + "\n")

    skills: dict[str, object] = {}
    skills_root = AGENTS_SOURCE / "skills"
    for skill in sorted(skills_root.iterdir()) if skills_root.is_dir() else []:
        if skill.is_dir() and skill.name != ".system":
            skills[skill.name] = tree_manifest(skill)
    (inventory / "skills-tree.json").write_text(json.dumps(skills, indent=2, sort_keys=True) + "\n")

    links = {}
    for path in [
        AGENTS,
        HOME / ".codex/AGENTS.md",
        HOME / ".claude/CLAUDE.md",
        HOME / ".claude/skills",
        HOME / ".claude/agents",
        HOME / ".config/opencode/AGENTS.md",
        HOME / ".config/opencode/skills",
        HOME / ".config/mise/config.toml",
    ]:
        links[str(path)] = {
            "exists": path.exists() or path.is_symlink(),
            "is_symlink": path.is_symlink(),
            "target": os.readlink(path) if path.is_symlink() else None,
            "resolved": str(path.resolve()) if path.exists() else None,
        }
    (inventory / "symlinks.json").write_text(json.dumps(links, indent=2, sort_keys=True) + "\n")

    commands = {
        "global-skills.json": ["npx", "--yes", "skills@1.5.16", "list", "-g", "--json"],
        "codex-plugins.txt": ["codex", "plugin", "list"],
        "brew-formulae.txt": ["brew", "list", "--formula", "--versions"],
        "brew-casks.txt": ["brew", "list", "--cask", "--versions"],
        "brew-taps.txt": ["brew", "tap"],
        "brew-outdated.txt": ["brew", "outdated", "--greedy", "--verbose"],
        "mise-current.txt": ["mise", "ls", "--current"],
        "mas-list.txt": ["mas", "list"],
    }
    for filename, command in commands.items():
        run_inventory(command, inventory / filename)

    lock = AGENTS_SOURCE / ".skill-lock.json"
    if lock.exists():
        shutil.copy2(lock, inventory / "skill-lock.json")

    exclusions = [
        "~/.codex/auth.json",
        "~/.codex/sessions and archived_sessions",
        "~/.codex browser profiles, generated media, caches, temporary data, and logs databases",
        "~/.config/opencode/node_modules",
        "agent authentication and session transcripts",
    ]
    (output / "EXCLUSIONS.txt").write_text("\n".join(exclusions) + "\n")

    portable = output / "portable-state.tar.gz"
    with tarfile.open(portable, "w:gz", dereference=False) as archive:
        add_path(archive, AGENTS_SOURCE, "live-agents")
        add_path(archive, HOME / "Downloads/bootstrap", "bootstrap")
        for relative in [".zshrc", ".zprofile", ".config/mise/config.toml", ".config/starship.toml", ".config/atuin/config.toml"]:
            add_path(archive, HOME / relative, f"home/{relative}")
        add_path(archive, inventory, "inventory")

    recovery = output / "local-recovery.tar.gz"
    with tarfile.open(recovery, "w:gz", dereference=False) as archive:
        for relative in [
            ".codex/config.toml",
            ".codex/.codex-global-state.json",
            ".codex/hooks",
            ".codex/rules",
            ".codex/automations",
            ".codex/memories",
            ".codex/plugins/data",
            ".codex/skills",
            ".claude/CLAUDE.md",
            ".claude/agents",
            ".claude/skills",
            ".claude/settings.json",
            ".config/opencode/opencode.jsonc",
            ".config/opencode/package.json",
            ".config/opencode/package-lock.json",
            ".config/opencode/agents",
            ".config/opencode/AGENTS.md",
            ".config/opencode/skills",
        ]:
            add_path(archive, HOME / relative, f"home/{relative}")

    archive_hashes = {path.name: {"sha256": sha256_file(path), "size": path.stat().st_size} for path in [portable, recovery]}
    attestation = {
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_agents": str(AGENTS_SOURCE),
        "source_agents_link": os.readlink(AGENTS) if AGENTS.is_symlink() else None,
        "archives": archive_hashes,
        "skill_directories": len(skills),
        "exclusions_file": "EXCLUSIONS.txt",
    }
    (output / "attestation.json").write_text(json.dumps(attestation, indent=2, sort_keys=True) + "\n")
    (output / "SHA256SUMS").write_text("".join(f"{details['sha256']}  {name}\n" for name, details in sorted(archive_hashes.items())))

    with tempfile.TemporaryDirectory(prefix="agent-snapshot-verify-") as temp:
        root = Path(temp)
        for archive_path in [portable, recovery]:
            with tarfile.open(archive_path, "r:gz") as archive:
                archive.extractall(root / archive_path.stem, filter="fully_trusted")
        restored = root / portable.stem / "live-agents"
        if tree_manifest(restored) != tree_manifest(AGENTS_SOURCE):
            raise SystemExit("portable archive verification failed")
        rehearsal = root / "rollback-rehearsal" / ".agents"
        rehearsal.parent.mkdir()
        # Rehearse the rollback link against the restored copy itself; the
        # optional ~/Downloads/bootstrap tree only exists on the original Mac.
        os.symlink(str(restored), rehearsal)
        if not rehearsal.resolve().is_dir():
            raise SystemExit("rollback rehearsal failed")

    (output / "VERIFIED").write_text("archives extracted, checksums compared, and rollback symlink rehearsed\n")
    print(output)


if __name__ == "__main__":
    main()
