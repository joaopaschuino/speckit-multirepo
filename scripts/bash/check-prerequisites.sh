#!/usr/bin/env bash
# The extension's commands name scripts/bash/check-prerequisites.sh, which Spec Kit resolves inside the installed
# extension (.specify/extensions/multirepo/scripts/bash/). Delegate to the project's core script.
set -euo pipefail
SCRIPT_DIR="$(CDPATH="" cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CORE="$SCRIPT_DIR/../../../../scripts/bash/check-prerequisites.sh"
if [[ ! -f "$CORE" ]]; then
  echo "multirepo: Spec Kit's core check-prerequisites.sh not found at .specify/scripts/bash/ (run specify init)" >&2
  exit 1
fi
exec bash "$CORE" "$@"
