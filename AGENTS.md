# AGENTS.md - New Mac Orchestrator

## Role

This repo is the root setup orchestrator for Samantha's Macs. Keep it small, profile-driven, and safe to run repeatedly.

## Operating Rules

- Use `./setup.sh` as the human-facing interface. Keep `mise run setup`, `mise run check`, and `mise run audit` as the small public task surface.
- Keep direct commands available for automation and recovery without exposing their flags in the primary README.
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
./setup.sh
```

For unattended setup and validation-only automation, use the retained direct Python command interface.

## Validation

After editing this repo, run:

```bash
python3 scripts/new_mac.py check
python3 scripts/new_mac.py plan --profile personal --dry-run
python3 scripts/new_mac.py plan --profile agent-dev --dry-run
```
