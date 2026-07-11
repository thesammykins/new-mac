#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() {
	printf '[new-mac] %s\n' "$*"
}

fail() {
	printf '[new-mac] ERROR: %s\n' "$*" >&2
	exit 1
}

usage() {
	cat <<'EOF'
Usage: ./setup.sh [advanced flags]

Run without arguments for the guided Mac setup menu.
Existing flags remain available for automation and scripted recovery.

Common flags:
  --profile personal|work|minimal|agent-dev
  --mode interactive|assume-defaults|ci
  --with brew,mas,dotfiles,skills,codex-stuff,codex,opencode,defaults
  --skip brew,mas,dotfiles,skills,plugins,defaults
  --dry-run
  --yes
  --dev-root PATH
EOF
}

run() {
	log "$*"
	"$@"
}

ensure_macos() {
	[[ "$(uname)" == "Darwin" ]] || fail "This setup currently supports macOS only."
}

ensure_xcode_cli_tools() {
	if xcode-select -p >/dev/null 2>&1; then
		return
	fi

	log "Xcode Command Line Tools are required."
	run xcode-select --install
	fail "Finish the Xcode Command Line Tools installer, then re-run this script."
}

ensure_homebrew() {
	if command -v brew >/dev/null 2>&1; then
		return
	fi

	log "Installing Homebrew..."
	/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

	if [[ -x /opt/homebrew/bin/brew ]]; then
		eval "$(/opt/homebrew/bin/brew shellenv)"
	elif [[ -x /usr/local/bin/brew ]]; then
		eval "$(/usr/local/bin/brew shellenv)"
	fi

	command -v brew >/dev/null 2>&1 || fail "Homebrew installed but brew is not on PATH."
}

ensure_git() {
	if command -v git >/dev/null 2>&1; then
		return
	fi
	run brew install git
}

ensure_mise() {
	if ! command -v mise >/dev/null 2>&1; then
		run brew install mise
	fi

	run mise trust -y "$REPO_ROOT/mise.toml"
	run mise install
}

main() {
	if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
		usage
		exit 0
	fi

	ensure_macos
	ensure_xcode_cli_tools
	ensure_homebrew
	ensure_git
	ensure_mise

	if [[ "$#" -eq 0 ]]; then
		log "Opening guided setup"
		run mise exec -- python "$REPO_ROOT/scripts/setup_tui.py"
	else
		log "Running compatibility command-line setup"
		run mise run apply -- "$@"
	fi
}

main "$@"
