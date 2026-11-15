# New Mac

The single setup and maintenance entry point for Sammy's Macs.

```bash
git clone https://github.com/thesammykins/new-mac.git /tmp/new-mac && /tmp/new-mac/setup.sh
```

On a brand-new Mac, `git` first offers to install the Command Line Tools; run
the line again once they finish. Setup clones everything, including new-mac
itself, into `~/repos`; on personal and work Macs it first makes `~/repos` its
own APFS volume (dotfiles' `repos-volume.sh`, which asks for sudo). A `~/repos`
that already has files stays a plain folder.
Later runs use `~/repos/new-mac`.

Sign in to the App Store first: one failed Brewfile entry stops the run, and
App Store apps fail without a sign-in. Stay at the keyboard for the sudo
prompts. Afterwards, sign in to 1Password and turn on its SSH agent (commits
are signed through it), run `gh auth login`, then synchronize skills from the
menu to pick up the private ones. macOS defaults are not applied by the menu;
run `DOTFILES_APPLY_MACOS_DEFAULTS=1 bash ~/repos/dotfiles/scripts/install.sh`,
or pass `--with defaults` to a scripted apply.

Or have an agent do it: point it at [AGENTS.md](AGENTS.md), which lists what
to ask you before it changes anything. Profiles: `personal`,
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

Snapshots remain local under `~/Backups/agent-environment`. Verified snapshots
are never removed automatically, and every rollback retains the state it replaces.

## Maintenance

```bash
mise run setup
mise run check
mise run audit
```

The menu is for a person at the keyboard. Agents, CI and scripted recovery use
the direct commands in [AGENTS.md](AGENTS.md); `mise exec -- python scripts/new_mac.py --help` lists them.
