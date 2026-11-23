"""The extension ships the prerequisite scripts its commands name, and its after_tasks hook is mandatory."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def installed_layout(tmp_path: Path) -> Path:
    """A project with a fake core script and the extension copied where Spec Kit installs it."""
    root = tmp_path / "project"
    core = root / ".specify" / "scripts" / "bash"
    core.mkdir(parents=True)
    (core / "check-prerequisites.sh").write_text(
        '#!/usr/bin/env bash\nprintf \'{"core":true,"args":"%s"}\\n\' "$*"\n', encoding="utf-8"
    )
    shutil.copytree(PACKAGE_ROOT / "scripts", root / ".specify" / "extensions" / "multi-repo" / "scripts")
    return root


def test_check_prerequisites_delegates_to_core(tmp_path):
    root = installed_layout(tmp_path)
    script = root / ".specify" / "extensions" / "multi-repo" / "scripts" / "bash" / "check-prerequisites.sh"
    out = subprocess.run(
        ["bash", str(script), "--json", "--require-tasks"], cwd=root, capture_output=True, text=True, check=True
    )
    assert json.loads(out.stdout) == {"core": True, "args": "--json --require-tasks"}


def test_check_prerequisites_reports_missing_core(tmp_path):
    root = installed_layout(tmp_path)
    (root / ".specify" / "scripts" / "bash" / "check-prerequisites.sh").unlink()
    script = root / ".specify" / "extensions" / "multi-repo" / "scripts" / "bash" / "check-prerequisites.sh"
    out = subprocess.run(["bash", str(script), "--json"], cwd=root, capture_output=True, text=True)
    assert out.returncode == 1
    assert "core check-prerequisites.sh not found" in out.stderr


def test_every_command_script_is_shipped():
    for command in (PACKAGE_ROOT / "commands").glob("*.md"):
        front = command.read_text(encoding="utf-8").split("---", 2)[1]
        for line in yaml.safe_load(front).get("scripts", {}).values():
            assert (PACKAGE_ROOT / line.split()[0]).is_file(), f"{command.name}: {line}"


def test_after_tasks_split_is_mandatory():
    manifest = yaml.safe_load((PACKAGE_ROOT / "extension.yml").read_text(encoding="utf-8"))
    assert manifest["hooks"]["after_tasks"]["command"] == "speckit.multi-repo.tasks"
    assert manifest["hooks"]["after_tasks"]["optional"] is False
