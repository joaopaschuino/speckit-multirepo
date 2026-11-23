#!/usr/bin/env bash
# Install (or upgrade in place) the multirepo extension components in a
# Spec Kit project.
#
# Usage:
#   ./install.sh central <project-dir> [--release vX.Y.Z | --dev <package-dir>]
#   ./install.sh member <project-dir> [--release vX.Y.Z | --dev <package-dir>]
#
# "central" installs the agent commands, the custom workflow step, and the
# workflow definition into the central specs repository. "member" installs
# only the agent commands (used by member repositories).
#
# Re-running the same command on an already-installed project is the
# supported upgrade path: existing components are replaced in place
# (extension and step with --force; workflows overwrite by default), and the
# member's AGENTS.md governance section is refreshed idempotently.
#
# Sources:
#   --dev <dir>   local package directory (default: this script's directory)
#   --release V   GitHub release tag, e.g. v1.0.0 — installs from the
#                 published release artifacts
#
# Environment:
#   SPECIFY_BIN   specify CLI to invoke (default: 'specify' on PATH). Point
#                 it at a >= 1.1.0 binary when your PATH carries an older one.
#
# Note: the custom step's `--from` install asks an interactive trust
# confirmation (default-deny) before downloading; answer "yes" when prompted.
set -euo pipefail

REPO="joaopaschuino/speckit-multirepo"

role="${1:?usage: install.sh central|member <project-dir> [--release vX.Y.Z | --dev <package-dir>]}"
project="${2:?usage: install.sh central|member <project-dir> [--release vX.Y.Z | --dev <package-dir>]}"
shift 2 || true

mode="dev"
src="$(cd "$(dirname "$0")" && pwd)"
release=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dev) mode="dev"; shift; [ "$#" -gt 0 ] && { src="$(cd "$1" && pwd)"; shift; } ;;
    --release) mode="release"; release="${2:?--release requires a version tag}"; shift 2 ;;
    *) echo "error: unknown option: $1" >&2; exit 1 ;;
  esac
done

SPECIFY_BIN="${SPECIFY_BIN:-specify}"
command -v "$SPECIFY_BIN" >/dev/null 2>&1 || {
  echo "error: specify CLI not found ($SPECIFY_BIN). Install Spec Kit >= 1.1.0 or set SPECIFY_BIN." >&2
  exit 1
}

project="$(cd "$project" && pwd)"
cd "$project"

# `extension add` can exit 0 without installing (e.g. a declined prompt);
# that must not pass as success.
# An already-installed manifest is not enough either: it must carry the
# version being installed, or a declined upgrade would pass silently.
ext_manifest="$project/.specify/extensions/multirepo/extension.yml"
ext_version() {
  sed -n 's/^[[:space:]]*version:[[:space:]]*"\{0,1\}\([^"]*\)"\{0,1\}[[:space:]]*$/\1/p' "$1" | head -n 1
}
require_installed() {
  if [ ! -f "$ext_manifest" ]; then
    echo "error: the extension was not installed." >&2
    exit 1
  fi
  local expected="$1" got
  got="$(ext_version "$ext_manifest")"
  if [ -n "$expected" ] && [ "$got" != "$expected" ]; then
    echo "error: the extension was not installed (found version $got, expected $expected)." >&2
    exit 1
  fi
}

if [ "$mode" = "dev" ]; then
  "$SPECIFY_BIN" extension add "$src" --dev --force
  require_installed "$(ext_version "$src/extension.yml")"
  if [ "$role" = "central" ]; then
    "$SPECIFY_BIN" workflow step add multirepo-implement --dev "$src/step/multirepo-implement" --force
    "$SPECIFY_BIN" workflow add "$src/workflow/multirepo" --dev
    "$SPECIFY_BIN" workflow add "$src/workflow/multirepo-check" --dev
    "$SPECIFY_BIN" workflow add "$src/workflow/multirepo-bootstrap" --dev
  fi
else
  ext_zip="https://github.com/$REPO/archive/refs/tags/$release.zip"
  wf_url="https://raw.githubusercontent.com/$REPO/$release/workflow/multirepo/workflow.yml"
  wf_check_url="https://raw.githubusercontent.com/$REPO/$release/workflow/multirepo-check/workflow.yml"
  wf_bootstrap_url="https://raw.githubusercontent.com/$REPO/$release/workflow/multirepo-bootstrap/workflow.yml"
  step_zip="https://github.com/$REPO/releases/download/$release/step-multirepo-implement-$release.zip"
  "$SPECIFY_BIN" extension add multirepo --from "$ext_zip" --force
  require_installed "${release#v}"
  if [ "$role" = "central" ]; then
    "$SPECIFY_BIN" workflow step add multirepo-implement --from "$step_zip" --force
    "$SPECIFY_BIN" workflow add multirepo --from "$wf_url"
    "$SPECIFY_BIN" workflow add multirepo-check --from "$wf_check_url"
    "$SPECIFY_BIN" workflow add multirepo-bootstrap --from "$wf_bootstrap_url"
  fi
fi

# Member repositories get the persistent governance pointer in AGENTS.md:
# it is what keeps free-form edits (which bypass the implement command)
# subject to the workspace constitution layers. Idempotent on re-runs.
if [ "$role" = "member" ]; then
  "$src/governance-note.sh" "$project"
fi

echo "multirepo ($role, $mode) installed in $project"
