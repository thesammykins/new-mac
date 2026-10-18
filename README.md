# New Mac

The single setup and maintenance entry point for Sammy's Macs.

```bash
git clone https://github.com/thesammykins/new-mac.git ~/Development/new-mac && ~/Development/new-mac/setup.sh
```

On a brand-new Mac, `git` first offers to install the Command Line Tools; run
the line again once they finish. Or have an agent do it: point it at [AGENTS.md](AGENTS.md), which lists what
to ask you before it changes anything. Profiles: `personal`, `agent-dev`,
`work`, `minimal`, and `ci` for CI runner Macs.

The guided menu handles an existing Mac's safe update, fresh-machine profile
selection, verification and repair, skills, backups, rollback, and advanced
diagnostics. It uses the Python standard library only: curses in an interactive
terminal and numbered prompts everywhere else.

Smart Update is the default. It creates and verifies a two-tier local snapshot,
then explicitly updates clean repositories with fast-forward-only merges. Dirty,
ahead, and diverged repositories stop before any apply step. It installs missing
Homebrew items without requesting upgrades, applies dotfiles, synchronizes the
complete skill inventory and Codex plugins, then runs the doctor.

## Ownership

- `new-mac` owns orchestration and the human-facing menu.
- `dotfiles` owns shared configuration, Brewfile tiers, and global mise settings;
  projects own their runtime and package-manager versions.
- `skills` owns the public skill catalog and installer; `skills-private`
  holds personal skills.
- `codex-stuff` owns portable Codex plugins; Claude plugins are listed in
  `profiles/common.toml`.
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
