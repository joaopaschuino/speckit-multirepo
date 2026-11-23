#!/usr/bin/env python3
"""Delegate to the project's core check_prerequisites.py (see scripts/bash/check-prerequisites.sh)."""
import os
import sys
from pathlib import Path

core = Path(__file__).resolve().parents[4] / "scripts" / "python" / "check_prerequisites.py"
if not core.is_file():
    sys.exit("multirepo: Spec Kit's core check_prerequisites.py not found at .specify/scripts/python/ (run specify init)")
os.execv(sys.executable, [sys.executable, str(core), *sys.argv[1:]])
