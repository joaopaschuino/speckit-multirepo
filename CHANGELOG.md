# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-23

First stable release. Requires Spec Kit ≥ 1.1.0. Extension id `multirepo`: every
agent command is `speckit.multirepo.<name>` (skill `speckit-multirepo-<name>`);
the workflows are `multirepo`, `multirepo-check` and `multirepo-bootstrap`,
and the custom step type is `multirepo-implement`.

### Fixed

- The commands' `scripts:` front matter names `scripts/bash/check-prerequisites.sh`
  (and the PowerShell and Python variants), which Spec Kit resolves inside the
  installed extension, but the package did not ship them: the first step of
  `/speckit.multirepo.tasks`, `.implement` and `.help` exited 127. The package
  now ships thin wrappers that delegate to the project's core scripts in
  `.specify/scripts/`.
- A member whose Verification commands all pass while its task file still has
  open `- [ ]` tasks is no longer reported `verified`: its verification status
  and Status column become `incomplete`, the step fails for it, and a retry
  (`verify_retries`) gets feedback listing the open tasks.
- `/speckit.multirepo.tasks` re-runs reset a member to `pending` when its task
  file gets new open tasks (a re-split, converge gaps, review findings), instead
  of keeping `verified`.
- The `after_tasks` hook is mandatory (`optional: false`): the core tasks
  command rewrites `tasks.md` and drops the orchestration table, which only the
  split rebuilds. In a repository without `.specify/workspace.yml` (a member)
  the split ends without changing anything.
- `- [ ]` lines inside HTML comments or fenced code blocks of a member task
  file are examples, not open tasks.
- The Python prerequisite wrapper returns the core script's exit code on
  Windows too; the PowerShell wrapper finds the core script in paths with
  `[ ]`.

### Changed (tests)

- The fake agents of the test suite check off the dispatched member's tasks,
  as a real agent does (`leave_open` / a `leave-open` sentinel keeps them open).

### Added

- **Workspace manifest** (`.specify/workspace.yml`): central specs repository
  plus member repositories, with `depends_on` ordering, optional per-member
  `constitution`, `url` (bootstrap remote) and domain topology; mono-repo
  layouts supported
- **`multirepo-implement` workflow step**: dispatches each member in
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
- **Workflows**: `multirepo` (confirm gate → dispatch + verification →
  review gate), `multirepo-check` (readiness and topology dry run) and
  `multirepo-bootstrap` (clone missing members from their `url`)
- **Agent commands**:
  - `speckit.multirepo.orchestrate` (central, router side): implementation +
    validation of a feature already split into `tasks/<member>.md` —
    everything after `tasks` — from the agent chat. Takes the feature
    directory (default: the active feature), `--auto` (pre-approves the
    gates) and `--report-only`; aborts when the per-member task files are
    missing or `multirepo-check` reports `no-dispatch` / `no-integration` /
    `unknown-integration` / `constitution-missing`; runs `multirepo` in the
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

### Upgrade from 0.x

0.x used the id `multi-repo` for the extension, workflows and step. Upgrade
the central repository and every member together, after finishing paused 0.x
runs (they cannot be resumed afterwards), by re-running `install.sh`. It
installs and checks 1.0.0 first; only then does it remove the `multi-repo`
extension, carry `multi-repo-config.yml` over to `multirepo-config.yml` (backed
up in `.specify/multirepo-migration/` until then; an edited
`multirepo-config.yml` is kept) and, on the central repository, save the 0.x
workflow definitions to `.specify/multirepo-migration/workflows/` and remove
the `multi-repo*` workflows and the `multi-repo-implement`
step. See README → Upgrading an existing workspace.
