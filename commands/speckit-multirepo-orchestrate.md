---
description: Run implementation and objective validation of an already-split feature across the workspace members, from the agent chat, and write an executive HTML report for human review (run in the central specs repository — router side)
scripts:
  sh: scripts/bash/check-prerequisites.sh --json --paths-only
  ps: scripts/powershell/check-prerequisites.ps1 -Json -PathsOnly
  py: scripts/python/check_prerequisites.py --json --paths-only
---

> **Central repository command (router).** This command runs in the **central specs repository** and drives the `multi-repo` workflow that dispatches each member's agent and verifies its work. It is **not** `speckit.multirepo.implement`, which is the **worker-side** command that runs *inside a member repository* (usually dispatched headlessly by this workflow). Never run this command in a member repository.

## User Input

```text
$ARGUMENTS
```

Accepted forms (tokens in any order):

- `<feature-dir>` — the feature to orchestrate, a path under `specs/` (relative to the repo root, e.g. `specs/001-orders`, or absolute). Default: the active feature.
- `--auto` — non-interactive mode: the workflow's gates (`confirm`, `review`) are pre-approved and nothing is asked; the final report is still written and shown.
- `--report-only [<run_id>]` — dispatch nothing: rebuild `verification/report.html` from an existing run (default: the most recent run under `.specify/workflows/runs/` whose `state.json` has `workflow_id` `multi-repo` and whose `inputs.json` → `.inputs.feature` is this feature). Do Steps 1, 5 and 6 only — use it after a manual `specify workflow resume`, which refreshes `report.md` but not the HTML.
- Any other text is a note from the user (for example "only report, the review is mine"); honor it when it does not contradict the rules below.

## Purpose

This is the chat entry point for **everything after `tasks`**: implementation and validation of a feature whose tasks were already split per member by `speckit.multirepo.tasks`. It wraps the terminal workflows — `multi-repo-check` (pre-flight) and `multi-repo` (dispatch + verification) — so the user does not have to drive them by hand, relays the workflow's gates to the user, and finishes with an executive HTML summary for human review.

Scope rules that apply in every mode:

- **No spec, plan, or tasks generation.** This command never runs `speckit.specify`, `speckit.plan`, `speckit.tasks`, or `speckit.multirepo.tasks`, and never edits `spec.md`, `plan.md`, `tasks.md`, or `tasks/<member>.md`. When something is missing, it stops and names the command to run.
- **Validation is the workflow's, not yours.** Whether a member is done is decided by the exit codes of its `## Verification` checks, run by the orchestrator step (with `verify_retries` re-dispatches and `verification/<member>.feedback.md`). Never re-run checks yourself to "confirm", never mark a member verified from an agent's own report, and never edit member repositories.
- **Write scope.** The only files this command writes are under `<feature>/verification/`: `report.html` and the run capture files `orchestrate.json` / `orchestrate.log`. Everything else in that directory (`report.md`, `<member>.log`, `<member>.feedback.md`) belongs to the workflow step.

## Step 1 — Resolve the feature

1. Confirm this is the central repository: `.specify/workspace.yml` must exist. If it does not, **STOP** with: `No workspace manifest at .specify/workspace.yml — run this command in the central specs repository (see /speckit.multirepo.workspace).`
2. If `$ARGUMENTS` names a feature directory, use it. Otherwise run `{SCRIPT}` from the repo root and take FEATURE_DIR from its JSON output. If neither yields a directory, **STOP** and ask the user for the feature path (with `--auto`: stop with the error).
3. Let FEATURE_DIR be the absolute path and FEATURE_REL its path relative to the repo root (POSIX separators) — the workflow input uses FEATURE_REL. FEATURE_DIR must exist.
4. With `--report-only`, resolve the run id (see User Input; none found → **STOP** and say so), then go straight to Step 5 and Step 6.

## Step 2 — Precondition: per-member task files exist

Read `.specify/workspace.yml` (member `id`, `tasks_file` — default `tasks/<id>.md`). The feature is ready for orchestration only when **at least one** member's task file exists under FEATURE_DIR (these are the product of `speckit.multirepo.tasks`).

If none exists, **STOP without running anything**:

```text
No per-member task files in <FEATURE_REL>/tasks/ — this feature has not been split yet.
Run speckit.multirepo.tasks in this central repository first (after speckit.tasks), review the tasks/<member>.md files, then run this command again.
```

List the members that will participate (those with a task file), the members without one (not participating), and — for each participating file — whether it has a `## Verification` section. A participating member with no verification section will finish as `completed`, never `verified`: warn the user (it is not an error).

## Step 3 — Pre-flight: `multi-repo-check`

Run from the repo root:

```sh
specify workflow run multi-repo-check -i feature=<FEATURE_REL> --json
```

The JSON on stdout is the run outcome (`run_id`, `status`, `error`); the step's output is persisted in the run state: read `.specify/workflows/runs/<run_id>/state.json` and take `.step_results.check.output` (`members` — one entry per declared member, keyed by `repo`, with `status`, `reason`, `participant` — plus `waves`, `not_ready`, `missing`). Consider only the members the implementation would dispatch: participating (`participant: true`) and not held (no `ready: false`). A held member is excluded by the workflow before its configuration or local presence is checked, so its status never blocks the run — it is only reported (see `not_ready` below).

- **Configuration errors — abort.** When any participant has status `no-dispatch`, `no-integration`, `unknown-integration`, or `constitution-missing`, **do not dispatch**. Report a diagnostic table (member, status, `reason`) and the fix for each:
  - `no-integration` / `unknown-integration` → the member's `.specify/integration.json` or the manifest's `integration` field (re-run `specify init --here --integration <agent>` in the member, or fix the manifest);
  - `no-dispatch` → the member's integration has no headless CLI dispatch; pick an integration that supports it;
  - `constitution-missing` → the `constitution` file declared in the manifest does not exist in the central repository.
  Then **STOP**.
- **Locally absent members** (`not-cloned`, `not-initialized`) → the default `missing: error` would abort the run. Report them and suggest `specify workflow run multi-repo-bootstrap` (clones members with a manifest `url`). Interactively, offer to continue with `-i missing=skip` (only the ready members are dispatched) and wait for the answer; with `--auto`, **STOP** — never skip members silently.
- `not_ready` members (held by `ready: false`, with `held_reason`) are reported and are not an error — whatever their status, they are neither configuration errors nor locally absent for this run.
- Show the dispatch plan: the waves (in order) and the participating members of each.

If the check itself fails (non-zero exit, unparseable JSON), report its error and **STOP**.

## Step 4 — Run `multi-repo` and poll its output

Dispatches are long: each member may take up to `dispatch_timeout` seconds (default 3600) per dispatch, plus every verification command, times `1 + verify_retries` attempts. Never block on the command with a short tool timeout and never assume a quiet terminal means a hung run.

1. **Confirm gate.** Interactively, show the plan from Step 3 and ask the user to approve the dispatch (this is the workflow's `confirm` gate); a rejection ends the command with nothing dispatched. With `--auto`, it is approved.
2. **Start the run in the background**, capturing stdout (the final JSON) and stderr (the live stream of the member agents) separately. Pass `-i confirm=approve` (the user already decided in 1). Interactively, leave `review` unset so the review gate pauses for the user; with `--auto`, pass `-i review=approve` too. Forward the user's own `verify_retries`, `dispatch_timeout`, or `missing=skip` choice as `-i key=value` when they gave one.

   ```sh
   mkdir -p <FEATURE_DIR>/verification
   specify workflow run multi-repo -i feature=<FEATURE_REL> -i confirm=approve [-i review=approve] [-i …] --json \
     > <FEATURE_DIR>/verification/orchestrate.json 2> <FEATURE_DIR>/verification/orchestrate.log &
   ```

3. **Poll** until the process exits: every 30–60 s, read the new lines of `orchestrate.log` and give the user a short progress line (current wave/member, dispatch start/finish, verification attempt) — not the raw log. Read `<FEATURE_DIR>/tasks.md` too: the workflow keeps its Status column current (`dispatched` → `verified` / `completed` / `failed`). Keep polling for as long as the run is alive; only consider it stuck when no log line and no Status change appeared for longer than `dispatch_timeout` — then report it and ask the user whether to keep waiting (with `--auto`: keep waiting; the step's own watchdog kills a dispatch that exceeds `dispatch_timeout`).
4. **Read the outcome.** `orchestrate.json` holds the run outcome: `run_id`, `status` (`completed` / `paused` / `failed` / `aborted`), `gate` (when paused: `step_id`, `message`, `options`), and `error`. The implement step's output is in the run state, `.specify/workflows/runs/<run_id>/state.json` → `.step_results.implement.output` (`results` per member — `repo`, `status`, `attempts`, `error`, `exit_code`, `timed_out`, `verification` — plus `verification`, `verification_summary`, `verification_report`, `failed`, `missing`, `not_ready`, `waves`, `stopped_after_wave`). If stdout is not valid JSON, report the tail of `orchestrate.log` and **STOP**.
5. **Relay gates.** When `status` is `paused` with `gate.step_id == "review"`: generate the HTML report first (Step 5), show the `verification_summary` and the report path, and ask the user to approve or reject — the same choice the terminal gate offers. Then continue the run:

   ```sh
   specify workflow resume <run_id> -i review=<approve|reject> --json \
     > <FEATURE_DIR>/verification/orchestrate.json 2>> <FEATURE_DIR>/verification/orchestrate.log
   ```

   (any other paused gate: relay its `gate.message` and `gate.options` the same way, passing the gate's verdict input on resume). With `--auto` no gate pauses; if one does anyway, resume it with `approve` and say so in the report.

A `failed` run is a normal outcome, not a crash: the step has already written `verification/report.md` and the per-member files, and the run can be resumed after the failing member is fixed. Do not resume a failed run on your own — whether to fix and resume is the user's decision.

## Step 5 — Write `<FEATURE_DIR>/verification/report.html`

Write it after every run that dispatched (whatever the final status — completed, failed, paused at review, or aborted at review), and rewrite it after a resume. It is an **executive summary for human review**: short, scannable, no raw logs. Sources, in priority order:

- `verification/report.md` — the step's per-member table (Member, Dispatch, Verification, Attempts, Failed checks);
- `verification/<member>.feedback.md` — for each failing check, its `## <check> — exit <got>, expected <expected>` (or `— timed out`) heading, the `Command:` line, and the output tail;
- `.step_results.implement.output.results` from the run's `state.json` — fallback for anything the files do not hold (a dispatch failure has no feedback file: use the result's `error`, `exit_code`, `timed_out`);
- `.step_results.implement.output.waves` and `stopped_after_wave` — when a wave fails the run stops (`stop_on_failure`), so members of later waves have no row in `results` / `report.md`: list each of them as `not dispatched` (reason: `stopped after wave <N+1> failed`).

Format rules:

- One standalone file: inline `<style>` only, no `<script>`, no external CSS/fonts/images/CDN, UTF-8 (`<meta charset="utf-8">`). It must render offline when opened from disk.
- HTML-escape every value taken from the sources (`&`, `<`, `>`, `"`).
- Do **not** paste logs: at most 1–2 lines of context per failing check.

Structure, in this order:

1. **Header** — feature name (FEATURE_DIR's directory name), the date of the run (ISO, `YYYY-MM-DD HH:MM`), the overall result `<verified>/<total> members verified` (total = every participating member: the members in `results`, including `missing` / `not-ready`, plus the `not dispatched` members of waves after `stopped_after_wave`), and the final status: the workflow run status (`completed`, `failed`, `paused at review`, `aborted`) plus `run_id`. Use a colored status badge (green completed, red failed/aborted, amber paused).
2. **Summary table** — one row per member, from `report.md`: member, status (dispatch status and verification status, e.g. `completed · verified`, `failed · failed`, `missing`, `not-ready`, `not dispatched`), attempts, failed checks (`—` when none). Color the status cell.
3. **Requires attention** — **only members that did not succeed** (dispatch `failed`, verification `failed`, `missing`, `not-ready`, `not dispatched`). For each member, one block; for each failing check: the check name, `expected exit <N> · got <M>` (or `timed out`), and 1–2 lines of context — the most informative lines of the output tail in `feedback.md` (the error line, not the banner), in a `<pre>`. For a dispatch failure, show the `error` instead. For `missing` / `not-ready` / `not dispatched`, show the reason. When every member succeeded, this section says "Nothing requires attention."
4. **Footer** — the source files for drill-down, as paths relative to the feature directory: `verification/report.md`, and for each member that has them `verification/<member>.log` and `verification/<member>.feedback.md`; plus `tasks.md` (orchestration page) and the run id with the command to inspect it (`specify workflow status <run_id>`).

Skeleton (adapt the rows; keep the structure and the inline style):

```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Verification — 001-orders</title>
<style>
body{font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif;margin:2rem auto;max-width:960px;color:#1f2328;padding:0 1rem}
h1{font-size:1.5rem;margin:0 0 .25rem}h2{font-size:1.1rem;margin:2rem 0 .5rem;border-bottom:1px solid #d0d7de;padding-bottom:.25rem}
.meta{color:#59636e}.badge{display:inline-block;padding:.1rem .55rem;border-radius:1rem;font-weight:600;font-size:.85rem}
.ok{background:#dafbe1;color:#116329}.fail{background:#ffebe9;color:#a40e26}.warn{background:#fff8c5;color:#7d4e00}.neutral{background:#eaeef2;color:#424a53}
table{border-collapse:collapse;width:100%}th,td{border:1px solid #d0d7de;padding:.4rem .6rem;text-align:left;vertical-align:top}th{background:#f6f8fa}
.member{border:1px solid #d0d7de;border-left:4px solid #cf222e;border-radius:6px;padding:.5rem 1rem;margin:.75rem 0}
pre{background:#f6f8fa;padding:.5rem;border-radius:4px;white-space:pre-wrap;margin:.25rem 0 .75rem}
footer{margin-top:2rem;color:#59636e;font-size:.85rem}code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
</style></head><body>
<header><h1>001-orders</h1>
<p class="meta">2026-11-23 14:05 · run <code>a1b2c3</code></p>
<p><span class="badge fail">failed</span> <strong>1/2 members verified</strong></p></header>
<h2>Summary</h2>
<table><tr><th>Member</th><th>Status</th><th>Attempts</th><th>Failed checks</th></tr>
<tr><td>s3</td><td><span class="badge ok">completed · verified</span></td><td>1</td><td>—</td></tr>
<tr><td>lambda</td><td><span class="badge fail">failed · failed</span></td><td>2</td><td>test</td></tr></table>
<h2>Requires attention</h2>
<div class="member"><h3>lambda</h3>
<p><strong>test</strong> — expected exit 0 · got 1</p>
<pre>FAIL src/handler.test.ts › rejects empty orders</pre></div>
<footer><p>Sources (relative to the feature directory): <code>verification/report.md</code> · <code>verification/s3.log</code> · <code>verification/lambda.log</code> · <code>verification/lambda.feedback.md</code> · <code>tasks.md</code> · <code>specify workflow status a1b2c3</code></p></footer>
</body></html>
```

## Step 6 — Report to the user

Answer in the user's language, briefly:

- The final status and `<verified>/<total> members verified`, then one line per member (status, attempts, failed checks).
- **The absolute path of `<FEATURE_DIR>/verification/report.html`** — always, on every run that wrote it.
- Next step, by outcome:
  - all verified, run `completed` → review the members' diffs and open their PRs (each member's change is a pure implementation diff);
  - a member `failed` → fix it in that member repository (the report's *Requires attention* section and `verification/<member>.feedback.md` say what broke), then run this command again: the new run skips members whose task files are fully checked off and whose checks still pass (`skip_completed`), and rewrites `report.html`. A manual `specify workflow resume <run_id>` refreshes only `report.md`, not the HTML — after one, run this command with `--report-only <run_id>` to rebuild `report.html` from that run without dispatching again;
  - `missing` / `not-ready` members → `multi-repo-bootstrap`, or remove `ready: false` and run again;
  - review rejected (`aborted`) → the dispatched code stays in the members; nothing was merged.
