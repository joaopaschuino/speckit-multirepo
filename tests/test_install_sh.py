"""End-to-end tests for install.sh — fresh install and in-place upgrade.

The script is the documented installation and upgrade path (README →
Upgrading), so both the clean and the already-installed flows are behavioral
contracts: re-running must replace existing components without failing and
without duplicating the member's AGENTS.md governance section.

Skipped when no `specify` executable (>= 1.1.0) is available — run from the
spec-kit checkout's virtualenv as documented in the README.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import PACKAGE_ROOT

SCRIPT = PACKAGE_ROOT / "install.sh"
GOVERNANCE_START = "<!-- SPECKIT-MULTI-REPO:GOVERNANCE START -->"


def locate_specify() -> str | None:
    found = shutil.which("specify")
    if found:
        return found
    sibling = Path(sys.executable).with_name("specify")
    return str(sibling) if sibling.is_file() else None


SPECIFY_BIN = locate_specify()

pytestmark = pytest.mark.skipif(
    SPECIFY_BIN is None,
    reason="specify executable not found (run from the spec-kit checkout venv)",
)


def run_specify(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [SPECIFY_BIN, *args],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=120,
    )


def run_install(role: str, project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), role, str(project), "--dev"],
        capture_output=True,
        text=True,
        timeout=300,
    )


def init_project(path: Path) -> Path:
    path.mkdir(parents=True)
    result = run_specify(path, "init", "--here", "--integration", "muse", "--ignore-agent-tools")
    assert result.returncode == 0, result.stderr
    return path


def test_fresh_install_then_upgrade(tmp_path):
    central = init_project(tmp_path / "central")
    member = init_project(tmp_path / "member")

    # -- fresh install ------------------------------------------------------
    result = run_install("central", central)
    assert result.returncode == 0, result.stderr
    assert (central / ".specify" / "workflows" / "steps" / "multi-repo-implement" / "__init__.py").is_file()
    assert (central / ".specify" / "workflows" / "multi-repo" / "workflow.yml").is_file()
    assert (central / ".specify" / "workflows" / "multi-repo-check" / "workflow.yml").is_file()
    assert (central / ".specify" / "workflows" / "multi-repo-bootstrap" / "workflow.yml").is_file()

    result = run_install("member", member)
    assert result.returncode == 0, result.stderr
    agents = (member / "AGENTS.md").read_text(encoding="utf-8")
    assert GOVERNANCE_START in agents
    installed = (member / ".specify" / "extensions.yml").read_text(encoding="utf-8")
    assert "- multirepo" in installed

    # -- upgrade: re-running replaces components in place -------------------
    result = run_install("central", central)
    assert result.returncode == 0, (
        f"upgrade rerun failed on central: {result.stdout}\n{result.stderr}"
    )
    result = run_install("member", member)
    assert result.returncode == 0, (
        f"upgrade rerun failed on member: {result.stdout}\n{result.stderr}"
    )
    agents = (member / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.count(GOVERNANCE_START) == 1  # refreshed, never duplicated


def test_unknown_option_fails(tmp_path):
    result = subprocess.run(
        ["bash", str(SCRIPT), "central", str(tmp_path), "--bogus"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "unknown option" in result.stderr


def test_upgrade_from_pre_rename_multi_repo_install(tmp_path):
    """0.8.x installed the extension as 'multi-repo'; the upgrade replaces it."""
    tag = subprocess.run(
        ["git", "-C", str(PACKAGE_ROOT), "archive", "v0.8.0"],
        capture_output=True,
    )
    if tag.returncode != 0:
        pytest.skip("v0.8.0 tag not available in this checkout")
    old_src = tmp_path / "old"
    old_src.mkdir()
    subprocess.run(["tar", "-x", "-C", str(old_src)], input=tag.stdout, check=True)

    member = init_project(tmp_path / "member")
    result = subprocess.run(
        ["bash", str(old_src / "install.sh"), "member", str(member), "--dev", str(old_src)],
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "SPECIFY_BIN": SPECIFY_BIN},
    )
    assert result.returncode == 0, result.stderr
    legacy = member / ".specify" / "extensions" / "multi-repo"
    assert legacy.is_dir()
    (legacy / "multi-repo-config.yml").write_text("implement:\n  tasks_file: custom.md\n", encoding="utf-8")

    result = run_install("member", member)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert not legacy.exists()
    new = member / ".specify" / "extensions" / "multirepo"
    assert (new / "extension.yml").is_file()
    assert "custom.md" in (new / "multirepo-config.yml").read_text(encoding="utf-8")
    installed = (member / ".specify" / "extensions.yml").read_text(encoding="utf-8")
    assert "speckit.multirepo.tasks" in installed


def _install_v080_member(tmp_path: Path) -> tuple[Path, Path]:
    tag = subprocess.run(
        ["git", "-C", str(PACKAGE_ROOT), "archive", "v0.8.0"],
        capture_output=True,
    )
    if tag.returncode != 0:
        pytest.skip("v0.8.0 tag not available in this checkout")
    old_src = tmp_path / "old"
    old_src.mkdir()
    subprocess.run(["tar", "-x", "-C", str(old_src)], input=tag.stdout, check=True)
    member = init_project(tmp_path / "member")
    result = subprocess.run(
        ["bash", str(old_src / "install.sh"), "member", str(member), "--dev", str(old_src)],
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "SPECIFY_BIN": SPECIFY_BIN},
    )
    assert result.returncode == 0, result.stderr
    legacy = member / ".specify" / "extensions" / "multi-repo"
    (legacy / "multi-repo-config.yml").write_text("implement:\n  tasks_file: custom.md\n", encoding="utf-8")
    return member, old_src


def test_reinstall_of_pre_rename_source_keeps_settings_under_its_id(tmp_path):
    member, old_src = _install_v080_member(tmp_path)
    result = subprocess.run(
        ["bash", str(SCRIPT), "member", str(member), "--dev", str(old_src)],
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "SPECIFY_BIN": SPECIFY_BIN},
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    legacy = member / ".specify" / "extensions" / "multi-repo"
    assert "custom.md" in (legacy / "multi-repo-config.yml").read_text(encoding="utf-8")
    assert not (member / ".specify" / "extensions" / "multirepo").exists()


def test_upgrade_fails_when_extension_add_installs_nothing(tmp_path):
    member, _ = _install_v080_member(tmp_path)
    fake = tmp_path / "fake-specify"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        '[ "$1 $2" = "extension add" ] && exit 0\n'
        f'exec "{SPECIFY_BIN}" "$@"\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    result = subprocess.run(
        ["bash", str(SCRIPT), "member", str(member), "--dev"],
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "SPECIFY_BIN": str(fake)},
    )
    assert result.returncode != 0
    assert "the extension was not installed" in result.stderr
    assert "previous settings saved at" in result.stderr
