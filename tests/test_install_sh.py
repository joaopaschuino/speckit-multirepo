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
    assert (central / ".specify" / "workflows" / "steps" / "multirepo-implement" / "__init__.py").is_file()
    assert (central / ".specify" / "workflows" / "multirepo" / "workflow.yml").is_file()
    assert (central / ".specify" / "workflows" / "multirepo-check" / "workflow.yml").is_file()
    assert (central / ".specify" / "workflows" / "multirepo-bootstrap" / "workflow.yml").is_file()

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


def test_fails_when_extension_add_installs_nothing(tmp_path):
    member = init_project(tmp_path / "member")
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


def install_v080(tmp_path: Path, role: str, project: Path) -> None:
    """Install the last 0.x release (id 'multi-repo') from the v0.8.0 tag."""
    old_src = tmp_path / "v0.8.0"
    if not old_src.is_dir():
        tag = subprocess.run(
            ["git", "-C", str(PACKAGE_ROOT), "archive", "v0.8.0"], capture_output=True
        )
        if tag.returncode != 0:
            pytest.skip("v0.8.0 tag not available in this checkout")
        old_src.mkdir()
        subprocess.run(["tar", "-x", "-C", str(old_src)], input=tag.stdout, check=True)
    result = subprocess.run(
        ["bash", str(old_src / "install.sh"), role, str(project), "--dev", str(old_src)],
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "SPECIFY_BIN": SPECIFY_BIN},
    )
    assert result.returncode == 0, result.stderr
    legacy = project / ".specify" / "extensions" / "multi-repo"
    assert legacy.is_dir()
    (legacy / "multi-repo-config.yml").write_text("implement:\n  tasks_file: custom.md\n", encoding="utf-8")


def test_upgrade_member_from_v080(tmp_path):
    member = init_project(tmp_path / "member")
    install_v080(tmp_path, "member", member)

    result = run_install("member", member)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert not (member / ".specify" / "extensions" / "multi-repo").exists()
    config = member / ".specify" / "extensions" / "multirepo" / "multirepo-config.yml"
    assert "custom.md" in config.read_text(encoding="utf-8")
    assert not (member / ".specify" / "multirepo-migration").exists()
    installed = (member / ".specify" / "extensions.yml").read_text(encoding="utf-8")
    assert "speckit.multirepo.tasks" in installed
    assert "speckit.multi-repo." not in installed
    agents = (member / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.count(GOVERNANCE_START) == 1

    # a re-run keeps settings edited after the upgrade
    config.write_text("implement:\n  tasks_file: edited.md\n", encoding="utf-8")
    result = run_install("member", member)
    assert result.returncode == 0, result.stderr
    assert "edited.md" in config.read_text(encoding="utf-8")


def test_upgrade_central_from_v080(tmp_path):
    central = init_project(tmp_path / "central")
    install_v080(tmp_path, "central", central)
    workflows = central / ".specify" / "workflows"
    assert (workflows / "multi-repo" / "workflow.yml").is_file()
    run = workflows / "runs" / "old-run"
    run.mkdir(parents=True)
    (run / "state.json").write_text(
        '{\n  "run_id": "old-run",\n  "workflow_id": "multi-repo",\n  "status": "paused"\n}\n',
        encoding="utf-8",
    )

    result = run_install("central", central)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "0.x run old-run is paused" in result.stderr
    for old in ("multi-repo", "multi-repo-check", "multi-repo-bootstrap", "steps/multi-repo-implement"):
        assert not (workflows / old).exists(), old
    for new in ("multirepo", "multirepo-check", "multirepo-bootstrap"):
        assert (workflows / new / "workflow.yml").is_file(), new
    assert (workflows / "steps" / "multirepo-implement" / "__init__.py").is_file()
    saved = central / ".specify" / "multirepo-migration" / "workflows" / "multi-repo.yml"
    assert 'id: "multi-repo"' in saved.read_text(encoding="utf-8")
    config = central / ".specify" / "extensions" / "multirepo" / "multirepo-config.yml"
    assert "custom.md" in config.read_text(encoding="utf-8")

    result = run_install("central", central)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_failed_upgrade_keeps_legacy_settings(tmp_path):
    member = init_project(tmp_path / "member")
    install_v080(tmp_path, "member", member)
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
    backup = member / ".specify" / "multirepo-migration" / "multi-repo-config.yml"
    assert f"0.x settings saved at {backup}" in result.stderr
    assert "custom.md" in backup.read_text(encoding="utf-8")
    # 0.x keeps working until 1.0.0 is really installed
    assert "left in place" in result.stderr
    legacy = member / ".specify" / "extensions" / "multi-repo"
    assert "custom.md" in (legacy / "multi-repo-config.yml").read_text(encoding="utf-8")
    assert "speckit.multi-repo." in (member / ".specify" / "extensions.yml").read_text(encoding="utf-8")

    # 0.x settings edited after the failed attempt win over its stale backup
    (legacy / "multi-repo-config.yml").write_text(
        "implement:\n  tasks_file: later.md\n", encoding="utf-8"
    )
    # the next successful run restores them
    result = run_install("member", member)
    assert result.returncode == 0, result.stderr
    config = member / ".specify" / "extensions" / "multirepo" / "multirepo-config.yml"
    assert "later.md" in config.read_text(encoding="utf-8")
    assert not backup.exists()
    assert not legacy.exists()


def test_declined_workflow_upgrade_keeps_legacy_workflows(tmp_path):
    central = init_project(tmp_path / "central")
    install_v080(tmp_path, "central", central)
    fake = tmp_path / "fake-specify"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        '[ "$1 $2" = "workflow add" ] && exit 0\n'
        f'exec "{SPECIFY_BIN}" "$@"\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    result = subprocess.run(
        ["bash", str(SCRIPT), "central", str(central), "--dev"],
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "SPECIFY_BIN": str(fake)},
    )
    assert result.returncode != 0
    assert "not installed: multirepo multirepo-check multirepo-bootstrap" in result.stderr
    workflows = central / ".specify" / "workflows"
    for old in ("multi-repo", "multi-repo-check", "multi-repo-bootstrap", "steps/multi-repo-implement"):
        assert (workflows / old).exists(), old
    assert (central / ".specify" / "extensions" / "multi-repo").is_dir()
