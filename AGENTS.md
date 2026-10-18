# AGENTS.md - New Mac Orchestrator

This repo sets up and maintains Samantha's Macs. An agent will usually be the
one running it, so this file is the operating manual. Keep the repo small,
profile-driven, and safe to run repeatedly.

## Ask before running anything

Setup changes the whole machine. Ask the user these, in one message, unless
they already said:

1. **Which profile?** `personal` (workstation and dev apps), `agent-dev`
   (same, tuned for agent work), `work` (core and dev tooling, no personal
   apps), `minimal` (core only), or `ci` (a CI runner Mac).
2. **Fresh Mac or existing one?** On an existing Mac, use Smart Update so a
   verified snapshot is taken first.
3. **Apply macOS defaults?** Only with `--with defaults`; never by default.
4. **Should this Mac get private skills?** It needs `gh auth login` with access
   to `thesammykins/skills-private`. Without access, setup warns and carries on.
5. **Any tier to remove?** Removing a Brewfile tier uninstalls apps. Preview
   with `scripts/brew-tiers.sh uninstall <tier>` in dotfiles and get a yes
   before adding `--apply`.

Then show the plan and get a yes before applying:

```bash
python3 scripts/new_mac.py plan --profile <profile> --dry-run
python3 scripts/new_mac.py apply --profile <profile> --yes
```

On an existing Mac use `python3 scripts/new_mac.py smart-update --profile <profile> --yes`.
`./setup.sh` is the same thing as a guided menu for a person at the keyboard.

## What each component does

- `brew`: installs the profile's Brewfile tiers through dotfiles'
  `scripts/brew-tiers.sh`, which trusts each Brewfile's taps first.
- `dotfiles`: links shell and app config from `thesammykins/dotfiles`.
- `skills`: installs the public catalog, the pinned external skills, and the
  private skills when the Mac can clone them.
- `codex`, `codex-stuff`: Codex CLI and its plugins.
- `claude`: Claude Code from dotfiles' global mise config, `~/.claude`
  links to the shared instructions and skills, and the Claude plugins listed
  in `profiles/common.toml`. Existing Claude files are backed up, not deleted.
- `defaults`: macOS defaults, only when asked.

## Rules

- Do not print secrets, read `.env` contents or paste credential values. Use
  1Password and varlock references.
- Do not archive, delete or rewrite unrelated local repos.
- Repo boundaries: `new-mac` orchestrates; `dotfiles` owns config and Brewfile
  tiers; `skills` and `skills-private` own skills; `codex-stuff` owns Codex
  plugins.
- A CI runner's release toolchain comes from that project's runner setup
  script, not from this repo.

## Validation

After editing this repo:

```bash
mise run check
python3 scripts/new_mac.py plan --profile personal --dry-run
python3 scripts/new_mac.py plan --profile ci --dry-run
```
