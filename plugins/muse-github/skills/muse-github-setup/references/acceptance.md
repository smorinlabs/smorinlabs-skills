# Installation and acceptance

Validation is pending until the checks below produce evidence for the edited
skill and chosen repository. Existing OpenCode validation does not validate this
Claude Action migration.

## Prepare and apply

1. Verify repository identity, default branch, visibility, current Git state,
   worktrees, installation, activation, and authorized scope. Preserve unrelated
   work. Work from a fresh default-branch revision in an isolated worktree.
2. Resolve `scripts/install.py` from this skill directory. Run the following
   command shape with discovered values; `SKILL_DIR` is that resolved directory,
   `WORKTREE` is the target repository root, `OWNER` its organization, and
   `REVIEWER` the approved human `@login` or `@organization/team`:

   ```text
   python3 SKILL_DIR/scripts/install.py WORKTREE --organization OWNER --codeowner REVIEWER
   ```

   Add `--with-fixes` for requested manual fixes. Add `--migrate-opencode` only
   after inspecting the legacy installation. Omitted `--model` preserves an
   existing policy model; a fresh install defaults to the contributor tier.
   `--no-codeowner` replaces `--codeowner` only when ownership is managed
   separately. This is an installer command shape, not a reader task: replace
   every value and resolve the executable before handing it to a human.
3. Inspect the printed model and all creates/updates/deletions. The default is
   read-only. Repeat the same invocation with `--apply` to write local files.
   Inspect the complete diff, then repeat preview; it must report zero changes.
   Applying does not configure GitHub secrets, policies, activation, or runs.
4. Protect the workflow files, helper, `.github/muse-ci/`, marked instructions,
   and CODEOWNERS through normal human review. Verify the applicable branch
   rules, including inherited rulesets. Confirm GitHub reads the intended
   CODEOWNERS file. A classic protection endpoint returning 404 is not proof
   that organization rulesets are absent. Verify the writer boundary described
   in [security](security.md).
5. Read back exact workflow-path execution policies for `muse-pr-review.yml`
   (`pull_request`), `muse-followup.yml` (`issue_comment` and
   `pull_request_review_comment`), and optional `muse-fix-pr.yml`
   (`workflow_dispatch`). Preserve approved actors and inherited restrictions.
   If an approved team does not exist, bring the genuine organization decision
   to the owner; do not invent a team or substitute repository roles.
6. Provision credentials using [secrets](secrets.md), verify names only, and
   preserve their scope. Inspect all consumers of `MUSE_CI_ENABLED`. Keep its
   existing value unchanged until cutover is ready. An inactive installation
   stays inactive until authorized activation.

## Legacy cutover and rollback

`--migrate-opencode` accepts recorded known snapshots of the managed legacy
workflow/profile/helper/instruction files. It removes recognized obsolete Muse
workflows and profiles while installing replacements. It preserves the legacy
model and optional fix support. Root `opencode.json`, root `opencode.jsonc`,
unrelated `.opencode/` files, other workflows, and surrounding project
instructions remain untouched.

A modified or unknown managed legacy file is a conflict. Preserve it and prepare
a reviewed reconciliation; never use force-copying to make migration pass.
Subsequent Claude Action updates also recognize exact prior managed snapshots.
They retain the installed model and optional fixes without requiring the legacy
migration flag. Modified managed files still require reviewed reconciliation.
Update path-scoped execution policies and required-check names in the cutover.
Verify that obsolete Muse bots cannot run alongside the replacement. If an active
old installation requires a temporary pause, record and restore its prior
activation value after the new prerequisites are ready.

Before applying, record the target base commit and retain the installer diff.
Before merge, rollback means reverting only the installation changes in its
worktree. After merge, rollback is a normal reviewed revert of the migration
commit, including workflow-path/check policies and any deliberately changed
activation value. Avoid having both generations active. Re-read the restored
files and activation afterward. Do not reset a dirty checkout or alter unrelated
OpenCode configuration.

## Gate A: local implementation

Run these checks against the edited skill worktree, not its old live placement:

| Check | Required coverage |
|---|---|
| Installer/helper tests | Fresh install, exact legacy migration and managed-version update, idempotence, retained model/fixes, unrelated-file preservation, changed managed-file conflict, symlink refusal, failures |
| Workflow checks | Rendered YAML lint; event/actor/mention guards; explicit token; all Muse aliases; classifier false on every action |
| Runtime isolation | Explicit settings through SDK; no PR hooks/skills/MCP/instruction startup; no shell or review edits; fake credential paths denied to reads/native search; permitted CI log reads; safe in-checkout review aliases; escaping/credential/cyclic alias refusal; all fix symlinks refused; read-only tool exposure |
| Package/skill checks | Meaningful repository tests, generated manifest check, skill content/docs/trigger review, static load check against edited source |

Record commands, exit statuses, versions, and passed/failed/skipped results.
Do not claim Gate A while a required failure remains. Skill loading and static
workflow checks do not establish a real GitHub interaction.
Review symlink checks must include the startup-configuration exception described
in [security](security.md): aliases originating at or beneath the action's
restored paths fail before model use, while safe aliases originating elsewhere
may point into their regular directories.

## Gate B: one live pilot

Select exactly one repository after Gate A. A second pilot is optional only when
it exercises a materially different supported setup. Inventory may proceed, but
no other consumer migration starts until the first pilot passes all applicable
checks. Follow normal branch/review/merge rules and existing authorization.

Land the trusted setup before the test PR. The setup PR's base lacks the new
helper and is not a valid acceptance test. Read back installed commits, policies,
secret names, and actual activation. Activate only within the authorized scope.
Use small reversible PRs and clearly identified test comments.

| Scenario | Required evidence |
|---|---|
| Eligible PR opens/updates | Official action uses Muse; exact input SHA recorded; progress visible; no code mutation |
| Deliberate unambiguous defect | Valid inline finding on the intended file, line, and reviewed commit |
| Member's new `@muse` PR comment | Relevant follow-up with PR context and a separate response |
| Two member follow-ups overlap | Both bounded runs retain their own correlated responses; neither pending request is replaced by the other |
| Member's new inline `@muse` reply | Actual completed reply in the intended discussion with no additional answer thread; new-inline-comment tool denied only for this event; temporary upstream progress fallback is permitted only when helper relocation succeeds and the fallback is removed |
| Progress and repeat review | Visible progress updates; final marked summary reused on another eligible trigger; no unintended leftover duplicate |
| PR advances during run | Cancellation or explicit stale failure; old/current SHA recorded; existing findings acknowledged as possibly stale |
| Ineligible actor/event | Rejected before Meta credentials are used; prefer offline fixtures for dangerous cases |
| Web tools | Read-only permission/exposure verified locally; actual WebFetch/WebSearch provider/network behavior recorded separately in authorized live acceptance |
| Failure | Diagnosable failed outcome; completion requires verified publication through a successful updater result or guarded publication of successful final SDK text when no updater was attempted; failed updater attempts cannot fall back; no Anthropic classifier request or silent model fallback |
| Optional manual fix | New helper-created branch and separate PR; ordinary-file diff; human review required; no approval or merge |
| Fix failure/invalid changes | No publication after unsuccessful model action or protected/sensitive-path validation failure |

Collect exact commits, workflow/run URLs, inline/follow-up/reply URLs, stable
summary ID, runtime versions, and relevant captured output. A green job without
the expected interaction fails acceptance. Diagnose each paid failure before
another bounded attempt. Do not expose real secrets or grant outsiders access
to manufacture a negative test.

The finalizer records fixed-name read-only tool invocation and correlated
result counts in job logs. These counts establish whether a tool returned a
result or reported an error; they do not prove the result was correct. Compare
web results with the requested public source. Raw prompts, tool arguments,
result contents, and execution transcripts are not published by this diagnostic.
Reviews and follow-ups allow at most 24 model turns within a 10-minute job.
The trusted prompt reserves a final comment update and prohibits placeholder
comments for tool discovery. Turn limits and these instructions reduce failure
risk; only live publication evidence establishes successful completion.

GitHub must allow Actions to create PRs for manual publication. Inspect that
repository setting only when fixes are in scope. Verify actual checks on the
bot-created PR; inherited policies or GitHub token behavior may require a human
approval. Do not add a privileged token to bypass that state. Supply a concrete
reader task when only a maintainer can finish it. Source:
[workflows triggered by workflows](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow).

## Batches and completion

After Gate B, migrate one or two similar repositories first. Refresh each
repository before preparation and collect installation/activation/live evidence.
Expand only when the results support it. Stop on systemic failure and repair the
shared skill before advancing. Keep every failure, skip, and unresolved repository
in the rollout ledger; exclude a repository only within the user's scope.

Report **authored**, **locally validated**, **PR opened**, **merged**, **installed**,
**activated**, and **live-verified** separately. Secret-name presence does not
prove credential validity. No required repository or acceptance check may be
silently counted as complete. Skill deployment also requires its live placement
to resolve to the updated source after the normal merge/sync process.
