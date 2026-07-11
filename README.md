# New Mac

The single setup and maintenance entry point for Sammy's Macs.

```bash
git clone https://github.com/thesammykins/new-mac.git "$HOME/Development/new-mac"
cd "$HOME/Development/new-mac"
./setup.sh
```

The guided menu handles an existing Mac's safe update, fresh-machine profile
selection, verification and repair, skills, backups, rollback, and advanced
diagnostics. It uses the Python standard library only: curses in an interactive
terminal and numbered prompts everywhere else.

Smart Update is the default. It creates and verifies a two-tier local snapshot
before pulling or applying anything, installs missing Homebrew items without
requesting upgrades, applies dotfiles, synchronizes the complete skill inventory
and Codex plugins, then runs the doctor.

## Ownership

- `new-mac` owns orchestration and the human-facing menu.
- `dotfiles` owns shared configuration, Brewfile tiers, and the pinned mise baseline.
- `skills` owns the complete shared skill catalog and installer.
- `codex-stuff` owns portable Codex plugins.
- `codex-private-setup` owns private Codex profile and hook policy.

Snapshots remain local under `~/Backups/agent-environment`. Verified snapshots
are never removed automatically, and every rollback retains the state it replaces.

## Maintenance

```bash
mise run setup
mise run check
mise run audit
```

The direct Python commands and compatibility flags remain available for CI,
isolated testing, and scripted recovery, but are intentionally outside the normal
setup path. Run `python3 scripts/new_mac.py --help` when that interface is needed.
