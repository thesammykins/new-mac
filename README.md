# New Mac

Agentic setup for Samantha's Macs. This repo is the first repo to clone on a new machine; it bootstraps the minimum tools, then delegates the rest to `mise` tasks and profile-driven installers.

## Operating Model

1. Install the minimum host tools: Xcode Command Line Tools, Homebrew, Git, and `mise`.
2. Clone this repo into `$HOME/Development/new-mac`.
3. Trust and install the repo's `mise` config.
4. Run a dry-run plan.
5. Apply a selected profile.

```bash
git clone https://github.com/thesammykins/new-mac.git "$HOME/Development/new-mac"
cd "$HOME/Development/new-mac"
./setup.sh --profile personal --dry-run
./setup.sh --profile personal --yes
```

You can also point Codex or OpenCode at this repo and ask it to run the same tasks. The repo-local `AGENTS.md` defines the expected agent behavior.

## Profiles

- `minimal`: base Homebrew/dotfiles only.
- `personal`: personal workstation baseline.
- `work`: work-safe developer baseline without personal workstation apps by default.
- `agent-dev`: full agent development baseline with skills and Codex plugins.

Common flags:

```bash
mise run plan -- --profile personal --dry-run
mise run apply -- --profile agent-dev --with defaults --yes
mise run apply -- --profile work --skip defaults,mas --yes
```

Supported flags:

- `--profile personal|work|minimal|agent-dev`
- `--mode interactive|assume-defaults|ci`
- `--with brew,mas,dotfiles,skills,codex-stuff,codex,opencode,defaults`
- `--skip brew,mas,dotfiles,skills,plugins,defaults`
- `--dry-run`
- `--yes`
- `--dev-root PATH`

`plugins` is accepted as an alias for `codex-stuff`.
Codex and OpenCode are installed by the developer Brewfile in normal profiles; use `--with codex` or `--with opencode` only for focused installs outside the bundle path.

## Repo Boundaries

- `thesammykins/new-mac`: orchestration, profiles, host inspection, and setup tasks.
- `thesammykins/dotfiles`: shell/app config, Brewfile tiers, `mise` global config, and shared agent rules.
- `thesammykins/skills`: custom skills plus a manifest of upstream skill sources.
- `thesammykins/codex-stuff`: Codex plugin marketplace.
- `thesammykins/brewfile`: legacy; no longer used by this setup path.

## Tasks

```bash
mise run doctor
mise run plan -- --profile personal --dry-run
mise run apply -- --profile personal --yes
mise run install-brew -- --profile personal --dry-run
mise run install-dotfiles -- --profile personal --dry-run
mise run install-skills -- --profile agent-dev --dry-run
mise run install-plugins -- --profile agent-dev --dry-run
mise run check
```

## Existing Mac Agent Migration

The migration flow keeps the existing bootstrap link until a fully staged replacement passes hash verification:

```bash
mise run snapshot
mise run verify-snapshot -- ~/Backups/agent-environment/<timestamp>
mise run stage-agents -- ~/Backups/agent-environment/<timestamp>
mise run cutover-agents -- ~/.agents.next.<timestamp>
```

The cutover retains `~/.agents.bootstrap.<timestamp>`. Restore it without deleting the failed candidate:

```bash
mise run rollback-agents -- ~/Backups/agent-environment/<timestamp>
```

Snapshots exclude authentication, sessions, browser profiles, generated media, caches, and logs databases. They remain local under `~/Backups/agent-environment` with owner-only permissions.

## Fresh Mac Notes

`mise` requires trusted config files before it runs repo tasks. `setup.sh` runs `mise trust` for this repo after installing `mise`.

macOS defaults and Dock changes are never applied unless the selected profile includes them or `--with defaults` is passed explicitly.
