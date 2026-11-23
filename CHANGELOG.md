# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-23

Initial release. Requires Spec Kit ≥ 1.1.0. Extension id `multirepo`: every
agent command is `speckit.multirepo.<name>` (skill `speckit-multirepo-<name>`);
the workflows are `multi-repo`, `multi-repo-check` and `multi-repo-bootstrap`,
and the custom step type is `multi-repo-implement`.

### Added

- **Workspace manifest** (`.specify/workspace.yml`): central specs repository
  plus member repositories, with `depends_on` ordering, optional per-member
  `constitution`, `url` (bootstrap remote) and domain topology; mono-repo
  layouts supported
- **`multi-repo-implement` workflow step**: dispatches each member in
  dependency waves (Kahn), with `dispatch_timeout`, `missing`
  (`error` | `skip`), `skip_completed`, `stop_on_failure` and `dry_run`
- **Objective verification (router / worker)**: member task files end with a
  `## Verification` section whose shell checks decide, by exit code, whether
  a member is done; `verify_retries` re-dispatches with
  `verification/<member>.feedback.md`; results in `verification/report.md`
  and `verification/<member>.log`; verification-only members for cross-repo
  contract checks; `ready: false` holds a member and its dependents
- **Governance bundles**: the workspace, member/type and member-local
  constitution layers combined into `<feature>/governance/<member>.md` per
  dispatch, with fail-fast validation; `install.sh member` keeps a
  governance section in the member's `AGENTS.md`
- **Workflows**: `multi-repo` (confirm gate → dispatch + verification →
  review gate), `multi-repo-check` (readiness and topology dry run) and
  `multi-repo-bootstrap` (clone missing members from their `url`)
- **Agent commands**:
  - `speckit.multirepo.orchestrate` (central, router side): implementation +
    validation of a feature already split into `tasks/<member>.md` —
    everything after `tasks` — from the agent chat. Takes the feature
    directory (default: the active feature), `--auto` (pre-approves the
    gates) and `--report-only`; aborts when the per-member task files are
    missing or `multi-repo-check` reports `no-dispatch` / `no-integration` /
    `unknown-integration` / `constitution-missing`; runs `multi-repo` in the
    background, relays its gates, and writes
    `<feature>/verification/report.html` — a standalone executive summary
    (inline CSS, no dependencies): verified/total, per-member table,
    *Requires attention* with expected vs actual exit per failing check, and
    the source files for drill-down
  - `speckit.multirepo.tasks` (central): splits the feature's tasks per
    member (also offered through the `after_tasks` hook)
  - `speckit.multirepo.implement` (member, worker side): headless-friendly
    implementation that runs the task file's Verification checks
  - `speckit.multirepo.workspace` (central): scaffolds and checks the
    workspace manifest
  - `speckit.multirepo.domain` (central): maps the domain topology
  - `speckit.multirepo.reverse` (central): baseline specs for existing code
  - `speckit.multirepo.help`: orientation, including "Who runs what, where"
- `install.sh` (central | member) with `--dev` and `--release` modes, in-place
  upgrades by re-running it, and `SPECIFY_BIN`
