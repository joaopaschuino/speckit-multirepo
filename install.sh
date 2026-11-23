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

# 0.x installed everything under the id `multi-repo`. Its settings are kept
# in the project, 1.0.0 is installed and verified next to it, and only then is
# 0.x removed — so a failed or declined install leaves 0.x working. The
# settings are restored, never over a multirepo-config.yml that was edited.
legacy_dir="$project/.specify/extensions/multi-repo"
backup_dir="$project/.specify/multirepo-migration"
backup="$backup_dir/multi-repo-config.yml"
new_config="$project/.specify/extensions/multirepo/multirepo-config.yml"
legacy_workflows="multi-repo multi-repo-check multi-repo-bootstrap"
new_workflows="multirepo multirepo-check multirepo-bootstrap"
if [ -d "$legacy_dir" ]; then
  echo "migrating the 0.x 'multi-repo' install to multirepo"
  # 0.x is still installed and in use, so its settings are the current ones
  # (a backup left by a failed attempt may be stale).
  if [ -f "$legacy_dir/multi-repo-config.yml" ]; then
    mkdir -p "$backup_dir"
    cp "$legacy_dir/multi-repo-config.yml" "$backup"
  fi
fi
if [ "$role" = "central" ]; then
  for state in "$project"/.specify/workflows/runs/*/state.json; do
    [ -f "$state" ] || continue
    if grep -Eq '"workflow_id": "multi-repo(-check|-bootstrap)?"' "$state" \
      && grep -q '"status": "paused"' "$state"; then
      echo "warning: 0.x run $(basename "$(dirname "$state")") is paused; it cannot be resumed after the upgrade" >&2
    fi
  done
fi
restore_legacy_config() {
  [ -f "$backup" ] || return 0
  # `extension add` writes the stock template; anything else was edited.
  if [ -f "$new_config" ] \
    && ! cmp -s "$new_config" "$project/.specify/extensions/multirepo/config-template.yml"; then
    echo "note: kept the existing $new_config; 0.x settings remain at $backup"
    return 0
  fi
  mv "$backup" "$new_config"
  rmdir "$backup_dir" 2>/dev/null || true
  echo "restored the 0.x settings to $new_config"
}
remove_legacy_workflows() {
  local id def
  for id in $legacy_workflows; do
    if [ -d "$project/.specify/workflows/$id" ]; then
      # Local edits to a 0.x workflow (e.g. input defaults) are not carried
      # into the 1.0.0 one; keep a copy to reapply them by hand.
      def="$project/.specify/workflows/$id/workflow.yml"
      if [ -f "$def" ]; then
        mkdir -p "$backup_dir/workflows"
        cp "$def" "$backup_dir/workflows/$id.yml"
        echo "note: saved the 0.x workflow '$id' to $backup_dir/workflows/$id.yml"
      fi
      "$SPECIFY_BIN" workflow remove "$id" \
        || echo "warning: could not remove the 0.x workflow '$id'" >&2
    fi
  done
  if [ -d "$project/.specify/workflows/steps/multi-repo-implement" ]; then
    "$SPECIFY_BIN" workflow step remove multi-repo-implement \
      || echo "warning: could not remove the 0.x step 'multi-repo-implement'" >&2
  fi
}

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
    legacy_kept
    exit 1
  fi
  local expected="$1" got
  got="$(ext_version "$ext_manifest")"
  if [ -n "$expected" ] && [ "$got" != "$expected" ]; then
    echo "error: the extension was not installed (found version $got, expected $expected)." >&2
    legacy_kept
    exit 1
  fi
}
# `workflow add`/`step add` also exit 0 on a declined trust prompt; the 0.x
# workflows are only removed once the new ones are really in place.
require_workflows() {
  local id missing=""
  for id in $new_workflows; do
    [ -f "$project/.specify/workflows/$id/workflow.yml" ] || missing="$missing $id"
  done
  [ -d "$project/.specify/workflows/steps/multirepo-implement" ] || missing="$missing multirepo-implement(step)"
  if [ -n "$missing" ]; then
    echo "error: not installed:$missing" >&2
    legacy_kept
    exit 1
  fi
}
legacy_kept() {
  [ -d "$legacy_dir" ] && echo "the 0.x 'multi-repo' install was left in place; re-run to retry" >&2
  [ -f "$backup" ] && echo "0.x settings saved at $backup" >&2
  return 0
}

if [ "$mode" = "dev" ]; then
  "$SPECIFY_BIN" extension add "$src" --dev --force
  require_installed "$(ext_version "$src/extension.yml")"
  if [ "$role" = "central" ]; then
    "$SPECIFY_BIN" workflow step add multirepo-implement --dev "$src/step/multirepo-implement" --force
    "$SPECIFY_BIN" workflow add "$src/workflow/multirepo" --dev
    "$SPECIFY_BIN" workflow add "$src/workflow/multirepo-check" --dev
    "$SPECIFY_BIN" workflow add "$src/workflow/multirepo-bootstrap" --dev
    require_workflows
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
    require_workflows
  fi
fi

if [ -d "$legacy_dir" ]; then
  "$SPECIFY_BIN" extension remove multi-repo --force \
    || echo "warning: could not remove the 0.x 'multi-repo' extension" >&2
fi
restore_legacy_config
if [ "$role" = "central" ]; then
  remove_legacy_workflows
fi

# Member repositories get the persistent governance pointer in AGENTS.md:
# it is what keeps free-form edits (which bypass the implement command)
# subject to the workspace constitution layers. Idempotent on re-runs.
if [ "$role" = "member" ]; then
  "$src/governance-note.sh" "$project"
fi

echo "multirepo ($role, $mode) installed in $project"
