# AGENTS.md - New Mac Orchestrator

## Role

This repo is the root setup orchestrator for Samantha's Macs. Keep it small, profile-driven, and safe to run repeatedly.

## Operating Rules

- Use `mise` tasks as the public interface. Prefer `mise run doctor`, `mise run plan`, `mise run apply`, and the focused install tasks over ad hoc commands.
- Start with `mise run doctor` and a dry-run plan before applying changes.
- Respect profile flags. Ask questions only when the selected profile and mode cannot determine a safe default.
- Keep repo boundaries clear:
  - `new-mac` orchestrates.
  - `dotfiles` owns shell/app config and Brewfile tiers.
  - `skills` owns custom skills and upstream skill manifests.
  - `codex-stuff` owns Codex plugins.
- Do not print secrets, inspect `.env` contents, or paste credential values. Use 1Password/varlock references where needed.
- Do not apply macOS defaults unless `--with defaults` or the profile explicitly enables them.
- Do not archive, delete, or rewrite unrelated local repos.

## Expected Flow

```bash
mise run doctor
mise run plan -- --profile personal --dry-run
mise run apply -- --profile personal --yes
```

For unattended setup, use `--mode assume-defaults --yes`. For validation-only automation, use `--mode ci`.

## Validation

After editing this repo, run:

```bash
python3 scripts/new_mac.py check
python3 scripts/new_mac.py plan --profile personal --dry-run
python3 scripts/new_mac.py plan --profile agent-dev --dry-run
```

