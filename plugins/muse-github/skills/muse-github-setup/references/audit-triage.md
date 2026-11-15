# Migrate an existing documentation audit job

Use this path only when the user requests replacing an existing Muse audit-triage
job that invokes `opencode run`. The job diagnoses failed `weekly-audit` runs and
proposes documentation repairs. Its edit permission is separate from PR reviews.
The installer refuses a fresh automatic-repair installation.

## Prepare and apply

Read [security](security.md) and inspect the existing workflow, helper, policy,
activation variable, credential names, default branch, repository writers, branch
rules, workflow execution policies, and applicable project instructions. Preserve
the existing model tier and secret scope. Read secret names only.

Use `scripts/install.py` from the resolved skill directory with the target
worktree, `--organization`, `--codeowner` or `--no-codeowner`, and
`--audit-triage --migrate-opencode`. The ordinary installer contract applies:
preview first, inspect every change, add `--apply`, and repeat preview for zero
changes. Do not combine audit triage with `--with-fixes`. Unknown or modified
legacy files require reviewed reconciliation; do not force overwrite.

The installer recognizes recorded audit-triage snapshots, preserves the existing
activation switch (`MUSE_CI_ENABLED` or `MUSE_AUDIT_TRIAGE_ENABLED`), and migrates
the existing model from its OpenCode provider prefix to the same bare Muse ID.
It leaves existing review workflows, review policy/helper, root OpenCode settings,
unrelated `.opencode/` content, and surrounding project instructions unchanged.

| Managed path | Purpose |
|---|---|
| `.github/workflows/audit-triage.yml` | Existing job name and triggers, with the official Claude Code Action |
| `.github/scripts/muse_audit_triage.py` | Trusted run validation, bounded failure input, runtime preparation, prepublication checks, URL report |
| `.github/muse-audit-triage/policy.json` | Organization, established model, input limit, activation switch |
| `.github/muse-audit-triage/triage-settings.json` | Read-only tools plus documentation-only file edits |
| `.github/muse-audit-triage/runtime.py` | Vendored shared runtime security helper, independent of consumer review files |

The cutover removes the recognized legacy `audit_triage.py` helper and its three
`.opencode/audit-triage/` configuration files. The workflow path remains unchanged,
so inspect and preserve its exact execution policy. Protect the new helper/config
paths and marked instruction/ownership sections through the normal review process.

## Behavior and limits

- Accept only a failed scheduled weekly audit on the repository's default branch,
  or an explicitly requested replay of an eligible failed audit. Validate the
  repository, workflow, run, event, and audited commit before using model credentials.
- Load executable helper and settings from trusted current default-branch code.
  Freeze the audited commit and bounded failure input separately. Failed logs and
  repository content are untrusted data, never executable setup instructions.
- Use the Action's prompt-driven agent mode with `track_progress: false` and
  `classify_inline_comments: false`. Route the main model and every alias to Muse.
  Do not enable bots or fabricate a human actor to bypass upstream authorization.
- Permit runtime read-only tools, including file/search and web inspection. Backend
  limitations still apply; native WebSearch's documented `max_uses` incompatibility
  is unchanged. Permit file edits only under `docs/`, with protected instructions
  and credential files excluded. Deny shell commands and model-controlled GitHub
  publication. Prove real runtime permission behavior; a settings file alone is
  not evidence that a rule works.
  The pinned Action creates its GitHub CI tool server only for PR contexts, so
  audit events receive the helper's frozen failure bundle rather than that live
  server. Permission to use a read-only tool does not instantiate its server.
- Require a successful model result and validate every tracked/untracked changed
  path before staging, committing, pushing, or opening a repair PR. Reject
  symlinks, protected files, credential files, and changes outside the approved
  documentation scope. No changes means no repair PR.
- Keep deterministic branch/commit/PR publication and URL verification outside
  the model step. Never approve or merge a generated repair PR. The workflow is
  bounded; it is not an OS sandbox and does not execute project tests with the
  model credential present.

An existing repair branch stops preparation before model use, even if its PR was
never created. Inspect that branch and the failed publication run, then recover
its PR through the normal authorized process. Do not blindly rerun the paid job,
force-push a replacement commit, or delete an existing repair branch. A branch
created after the preflight check still makes a conflicting non-force push fail
safely; the preflight check is not an atomic reservation.

## Gates and evidence

Gate A requires meaningful installer/helper tests, real CLI permission probes,
workflow lint, manifest checks, skill loading, and independent review of the
edited source. Test idempotence, preservation, modified-file refusal, trigger
rejections, failure handling, read access, allowed documentation edits, denied
out-of-scope edits, and validation before publication.

Select one pilot with an eligible recorded failed documentation audit and
available logs. Preserve activation state until cutover is ready. Install through
normal PR checks and protections, then run a bounded replay. Verify the official
Action and Muse model, exact audited SHA, expected ordinary documentation changes,
separate repair PR, URL report, and absence of unauthorized edits or duplicate PRs.
A green skipped job is not proof of model execution. Record skipped/no-change
cases separately. Close an acceptance repair PR without merging.

If no eligible failed documentation audit exists, use a separately named,
temporary, manual-only acceptance workflow. Keep its synthetic run/job/log input
explicitly labeled; do not widen or disable production guards. Exercise the real
Action, Muse backend, runtime settings, change validation, repair PR publication,
and URL verification against a harmless documentation fixture created only in
the runner. Never put a deliberate broken link on the default branch. Close the
fixture PR unmerged and remove the temporary harness through normal review.
Report this as live model/publication acceptance with synthetic failure input;
production trigger eligibility remains covered by independent fixtures and
applicable real-run rejection/skip checks.

Only after that pilot passes, migrate the remaining repositories incrementally.
Read back installed files and unchanged activation/model decisions, and collect
applicable live evidence per repository. Stop on a shared defect and repair the
skill first. Keep the rollout ledger explicit about pending and blocked work.

For rollback, retain the old revision and activation value. Disable only the
affected job's existing switch when necessary, restore the prior files through
normal review, restore its original switch value, and verify that only one
triage implementation can run. Never toggle a shared switch without checking its
other consumers. Do not delete unrelated OpenCode configuration.
