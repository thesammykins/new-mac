#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any


HOME = Path.home()
DEV_ROOT = HOME / "Development"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        if path.is_symlink():
            digest.update(b"L" + os.readlink(path).encode() + b"\0")
        elif path.is_file():
            digest.update(b"F" + path.read_bytes())
        elif path.is_dir():
            digest.update(b"D")
    return digest.hexdigest()


def read_attestation(snapshot: Path) -> dict[str, Any]:
    return json.loads((snapshot / "attestation.json").read_text(encoding="utf-8"))


def verify_snapshot(snapshot: Path) -> None:
    attestation = read_attestation(snapshot)
    for name, details in attestation["archives"].items():
        path = snapshot / name
        if not path.is_file() or sha256_file(path) != details["sha256"]:
            raise SystemExit(f"snapshot archive failed verification: {path}")
    with tempfile.TemporaryDirectory(prefix="agent-snapshot-check-") as temporary:
        with tarfile.open(snapshot / "portable-state.tar.gz", "r:gz") as archive:
            archive.extractall(temporary, filter="fully_trusted")
        if not (Path(temporary) / "live-agents/skills").is_dir():
            raise SystemExit("portable snapshot does not contain live-agents/skills")
    print(f"verified snapshot: {snapshot}")


def source_skill_hashes(snapshot: Path) -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="agent-snapshot-skills-") as temporary:
        with tarfile.open(snapshot / "portable-state.tar.gz", "r:gz") as archive:
            archive.extractall(temporary, filter="fully_trusted")
        root = Path(temporary) / "live-agents/skills"
        return {path.name: tree_digest(path) for path in root.iterdir() if path.is_dir() and path.name != ".system"}


def replace_with_link(path: Path, target: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target)


def stage_agents(snapshot: Path) -> Path:
    verify_snapshot(snapshot)
    suffix = snapshot.name
    candidate = HOME / f".agents.next.{suffix}"
    if candidate.exists() or candidate.is_symlink():
        raise SystemExit(f"staging path already exists: {candidate}")
    with tempfile.TemporaryDirectory(prefix="agent-stage-") as temporary:
        with tarfile.open(snapshot / "portable-state.tar.gz", "r:gz") as archive:
            archive.extractall(temporary, filter="fully_trusted")
        shutil.copytree(Path(temporary) / "live-agents", candidate, symlinks=True)

    dotfiles = DEV_ROOT / "dotfiles"
    replace_with_link(candidate / "AGENTS.md", dotfiles / ".agents/AGENTS.md")
    replace_with_link(candidate / "GEMINI.md", dotfiles / ".agents/GEMINI.md")

    skills = DEV_ROOT / "skills"
    subprocess.run(
        ["mise", "exec", "--", "python", "scripts/install-skills.py", "--install-root", str(candidate / "skills")],
        cwd=skills,
        check=True,
    )
    backup_link = HOME / f".agents.bootstrap.{suffix}"
    live = HOME / ".agents"
    metadata = {
        "snapshot": str(snapshot),
        "backup_link": str(backup_link),
        "source_link": os.readlink(live) if live.is_symlink() else None,
    }
    (candidate / ".migration.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    verify_stage(snapshot, candidate)
    (candidate / ".migration-verified").write_text("verified\n")
    print(candidate)
    return candidate


def verify_stage(snapshot: Path, candidate: Path) -> None:
    expected = source_skill_hashes(snapshot)
    actual = {path.name: tree_digest(path) for path in (candidate / "skills").iterdir() if path.is_dir() and path.name != ".system"}
    if expected != actual:
        missing = sorted(set(expected) - set(actual))
        changed = sorted(name for name in expected.keys() & actual.keys() if expected[name] != actual[name])
        extra = sorted(set(actual) - set(expected))
        raise SystemExit(f"staged skills differ; missing={missing}, changed={changed}, extra={extra}")
    if not (candidate / "AGENTS.md").is_symlink() or not (candidate / "GEMINI.md").is_symlink():
        raise SystemExit("staged shared instructions are not linked to dotfiles")
    print(f"verified stage: {candidate} ({len(actual)} skill directories)")


def ensure_consumer_links() -> None:
    links = {
        HOME / ".codex/AGENTS.md": HOME / ".agents/AGENTS.md",
        HOME / ".claude/CLAUDE.md": HOME / ".agents/AGENTS.md",
        HOME / ".claude/skills": HOME / ".agents/skills",
        HOME / ".claude/agents": HOME / ".agents/claude-agents",
        HOME / ".config/opencode/AGENTS.md": HOME / ".agents/AGENTS.md",
        HOME / ".config/opencode/skills": HOME / ".agents/skills",
    }
    for path, target in links.items():
        replace_with_link(path, target)


def cutover(candidate: Path) -> None:
    live = HOME / ".agents"
    if not (candidate / ".migration-verified").is_file():
        raise SystemExit("candidate has not passed verify-stage")
    metadata = json.loads((candidate / ".migration.json").read_text())
    backup = Path(metadata["backup_link"])
    if backup.exists() or backup.is_symlink():
        raise SystemExit(f"backup link already exists: {backup}")
    live.rename(backup)
    try:
        candidate.rename(live)
        ensure_consumer_links()
    except BaseException:
        if not live.exists() and backup.exists():
            backup.rename(live)
        raise
    print(f"cut over {live}; rollback link retained at {backup}")


def rollback(snapshot: Path) -> None:
    live = HOME / ".agents"
    backup = HOME / f".agents.bootstrap.{snapshot.name}"
    if not backup.is_symlink():
        raise SystemExit(f"rollback link missing: {backup}")
    failed = HOME / f".agents.failed.{snapshot.name}"
    if failed.exists() or failed.is_symlink():
        raise SystemExit(f"failed-state target already exists: {failed}")
    live.rename(failed)
    backup.rename(live)
    ensure_consumer_links()
    if str(live.resolve()) != read_attestation(snapshot)["source_agents"]:
        raise SystemExit("rollback did not restore the attested agents source")
    print(f"rolled back {live}; migrated state retained at {failed}")


def restore_snapshot(snapshot: Path) -> None:
    verify_snapshot(snapshot)
    live = HOME / ".agents"
    candidate = HOME / f".agents.restore.{snapshot.name}"
    failed = HOME / f".agents.pre-restore.{snapshot.name}"
    for path in (candidate, failed):
        if path.exists() or path.is_symlink():
            raise SystemExit(f"restore path already exists: {path}")
    with tempfile.TemporaryDirectory(prefix="agent-restore-") as temporary:
        with tarfile.open(snapshot / "portable-state.tar.gz", "r:gz") as archive:
            archive.extractall(temporary, filter="fully_trusted")
        shutil.copytree(Path(temporary) / "live-agents", candidate, symlinks=True)
    if tree_digest(candidate) != tree_digest_from_archive(snapshot):
        shutil.rmtree(candidate)
        raise SystemExit("restored candidate differs from the verified archive")
    live.rename(failed)
    try:
        candidate.rename(live)
        ensure_consumer_links()
    except BaseException:
        if not live.exists() and failed.exists():
            failed.rename(live)
        raise
    print(f"restored {live} from {snapshot}; previous state retained at {failed}")


def tree_digest_from_archive(snapshot: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="agent-restore-verify-") as temporary:
        with tarfile.open(snapshot / "portable-state.tar.gz", "r:gz") as archive:
            archive.extractall(temporary, filter="fully_trusted")
        return tree_digest(Path(temporary) / "live-agents")


def stage_skills(snapshot: Path) -> Path:
    verify_snapshot(snapshot)
    skills_repo = DEV_ROOT / "skills"
    installer = skills_repo / "scripts/install-skills.py"
    if not installer.is_file():
        raise SystemExit(f"skills installer is missing: {installer}")
    candidate = HOME / ".agents" / f"skills.next.{snapshot.name}"
    if candidate.exists() or candidate.is_symlink():
        raise SystemExit(f"skills staging path already exists: {candidate}")
    subprocess.run(
        ["mise", "exec", "--", "python", str(installer), "--install-root", str(candidate)],
        cwd=skills_repo,
        check=True,
    )
    system = HOME / ".agents/skills/.system"
    if system.is_dir():
        shutil.copytree(system, candidate / ".system", symlinks=True)
    subprocess.run(
        ["mise", "exec", "--", "python", str(installer), "--install-root", str(candidate), "--verify"],
        cwd=skills_repo,
        check=True,
    )
    (candidate / ".migration-verified").write_text(snapshot.name + "\n", encoding="utf-8")
    print(candidate)
    return candidate


def cutover_skills(candidate: Path) -> None:
    marker = candidate / ".migration-verified"
    if not marker.is_file():
        raise SystemExit("skills candidate has not passed verification")
    suffix = marker.read_text(encoding="utf-8").strip()
    live = HOME / ".agents/skills"
    backup = HOME / ".agents" / f"skills.bootstrap.{suffix}"
    if backup.exists() or backup.is_symlink():
        raise SystemExit(f"skills rollback directory already exists: {backup}")
    live.rename(backup)
    try:
        candidate.rename(live)
        ensure_consumer_links()
    except BaseException:
        if not live.exists() and backup.exists():
            backup.rename(live)
        raise
    print(f"activated {live}; previous skills retained at {backup}")


def rollback_skills(snapshot: Path) -> None:
    live = HOME / ".agents/skills"
    backup = HOME / ".agents" / f"skills.bootstrap.{snapshot.name}"
    failed = HOME / ".agents" / f"skills.failed.{snapshot.name}"
    if not backup.is_dir():
        raise SystemExit(f"skills rollback directory is missing: {backup}")
    if failed.exists() or failed.is_symlink():
        raise SystemExit(f"failed-state directory already exists: {failed}")
    live.rename(failed)
    backup.rename(live)
    ensure_consumer_links()
    print(f"rolled back {live}; replaced skills retained at {failed}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Verify, stage, cut over, or roll back the shared agent environment.")
    subcommands = result.add_subparsers(dest="command", required=True)
    for name in ["verify-snapshot", "stage-agents", "rollback-agents", "restore-snapshot", "stage-skills", "rollback-skills"]:
        command = subcommands.add_parser(name)
        command.add_argument("snapshot", type=Path)
    verify = subcommands.add_parser("verify-stage")
    verify.add_argument("snapshot", type=Path)
    verify.add_argument("candidate", type=Path)
    cut = subcommands.add_parser("cutover-agents")
    cut.add_argument("candidate", type=Path)
    cut_skills = subcommands.add_parser("cutover-skills")
    cut_skills.add_argument("candidate", type=Path)
    return result


def main() -> None:
    args = parser().parse_args()
    if args.command == "verify-snapshot":
        verify_snapshot(args.snapshot.resolve())
    elif args.command == "stage-agents":
        stage_agents(args.snapshot.resolve())
    elif args.command == "verify-stage":
        verify_stage(args.snapshot.resolve(), args.candidate.resolve())
    elif args.command == "cutover-agents":
        cutover(args.candidate.resolve())
    elif args.command == "rollback-agents":
        rollback(args.snapshot.resolve())
    elif args.command == "restore-snapshot":
        restore_snapshot(args.snapshot.resolve())
    elif args.command == "stage-skills":
        stage_skills(args.snapshot.resolve())
    elif args.command == "cutover-skills":
        cutover_skills(args.candidate.resolve())
    elif args.command == "rollback-skills":
        rollback_skills(args.snapshot.resolve())


if __name__ == "__main__":
    main()
