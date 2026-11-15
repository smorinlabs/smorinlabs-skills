---
name: muse-github-setup
description: "Install, update, or migrate Muse GitHub reviews to the official Anthropic Claude Code Action, keeping Muse as the model backend. Use for 'install Muse reviews', 'set up Muse in GitHub Actions', 'migrate Muse from OpenCode', or adding @muse PR follow-ups and inline discussion replies. Prepares trusted workflows, checks member-only protections and scoped credentials, preserves model/tier choices, and verifies authorized installation and live behavior. Includes optional manually requested fix PRs. Not for generic Claude/OpenCode setup, local code review, an iterative coding loop, or unrelated CI repair."
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, AskUserQuestion, WebFetch, WebSearch
---

# muse-github-setup

Install and maintain organization-member Muse reviews through the official Claude Code Action, including PR follow-ups and optional manual fix PRs.

## Workflow

1. **Resolve scope and source.** Verify the target owner/name, default branch,
   visibility, local checkout, current workflows, and existing authorization.
   Use repository discovery before cloning. Work in an isolated worktree and
   preserve unrelated changes. Keep this skill's name when migrating an existing
   installation. A setup request covers preparation; use the user's established
   authorization for publishing, activation, and bounded paid acceptance tests.
   Do not ask again for an action already authorized. Resolve genuine missing
   owner decisions before their dependent action.

2. **Inspect prerequisites.** Read [security](references/security.md), then inspect
   `.github/workflows/`, `.github/scripts/muse_ci.py`, `.github/muse-ci/`,
   `.opencode/muse-ci/`, root OpenCode config, project instructions, CODEOWNERS,
   branch rules, workflow execution policies, and repository writers. Templates
   require an organization-owned GitHub.com repository and fresh GitHub-hosted
   Ubuntu runners. Current human organization membership and repository write
   access are separate requirements. Private membership uses the dedicated
   Members-read App described in [secrets](references/secrets.md).
   CODEOWNERS alone cannot stop a modified PR workflow from executing. Verify
   the writer boundary and exact workflow-path policies before activation.
   Find every consumer of `MUSE_CI_ENABLED` before changing it; preserve its
   existing state until the replacement is ready.

3. **Preserve the model and credentials.** Omitted `--model` preserves the model
   recorded in an existing managed policy. A fresh install defaults to
   `muse-spark-1.3-contributor`; Meta may use contributor content for training.
   Preserve an established tier decision. A private repository without one
   needs an owner decision: recommend `muse-spark-1.3` standard tier, explain
   contributor data use, and include not installing as an option. Never silently
   change a private repository's tier or credential scope. The other supported
   model is `muse-wonder-1.0`. All Claude model aliases and subagent routing stay
   on the selected Muse ID. Claude uses `https://api.meta.ai` without `/v1`.
   Anthropic does not support non-Claude backends; Meta documents compatibility.

4. **Preview the installation.** Resolve `scripts/install.py` relative to this
   skill and invoke it with Python from the source worktree. Supply the target
   repository root, `--organization` with its verified owner, and `--codeowner`
   with the approved `@login` or `@organization/team`. Use `--no-codeowner` only
   when ownership is managed separately. Add `--with-fixes` for requested manual
   fix PRs and `--model` only for a deliberate model selection. Add
   `--migrate-opencode` for an existing managed OpenCode installation. Default
   execution prints a plan; `--apply` writes local files. Inspect the printed
   model and every deletion before applying. Read [acceptance](references/acceptance.md)
   for the complete cutover, idempotence, and rollback procedure.
   Known legacy files migrate only when they match a recorded snapshot exactly.
   Modified legacy files require reviewed reconciliation; do not force overwrite.
   Existing optional fix support and model choice are retained. Root
   `opencode.json`/`opencode.jsonc` and unrelated OpenCode content are preserved.

5. **Review the rendered changes.** The managed paths are
   `.github/workflows/muse-pr-review.yml`, `muse-followup.yml`, optional
   `muse-fix-pr.yml`, `.github/scripts/muse_ci.py`, and `.github/muse-ci/`.
   The installer updates its marked `AGENTS.md` and CODEOWNERS sections while
   preserving surrounding content. Remove recognized obsolete Muse workflows
   in the same cutover to avoid duplicate bots. Update exact workflow-path
   execution policies and any required-check names deliberately. The helper is
   vendored: keep it byte-identical to the template and exclude it from target
   formatter autofixes. Project-specific policy changes belong upstream in
   this skill, followed by re-rendering.

6. **Provision only required credentials.** Follow [secrets](references/secrets.md).
   Preserve existing secret values and scope; inspect names only. Use a compatible
   installed `repo-secrets` provisioner when available, otherwise provide its
   secure manual fallback. Never invent a private secret-manager reference or
   ask for a key in chat. No new Anthropic API key or Claude GitHub App is needed.
   The Meta key satisfies the action launch check and supplies Meta bearer auth.
   Every action invocation must set `classify_inline_comments: 'false'`.

7. **Validate, then prove one pilot.** Run workflow lint, meaningful installer and
   helper tests, manifest checks, and skill-quality/load checks against this
   edited source worktree. Record passed, failed, and skipped checks separately.
   Local success is Gate A, not proof of GitHub interaction. Follow the target's
   normal branch/review/merge rules. After authorized installation and activation,
   complete the pilot matrix in [acceptance](references/acceptance.md): inline
   finding, top-level follow-up, inline reply, progress, reusable summary, repeat
   trigger, stale handling, and rejection before model use. Diagnose a paid
   failure before retrying. Never approve or merge a generated fix PR.

8. **Roll out within the approved scope.** The first pilot's complete acceptance
   is Gate B. Inventory may proceed earlier; consumer migrations may not. After
   Gate B, start with one or two similar repositories, verify each, then expand
   cautiously. Keep a ledger of identified, excluded, prepared, installed,
   activated, live-verified, failed, and blocked repositories with exact commits
   and evidence URLs. Stop batches on a systemic failure and fix the shared
   skill first. Do not count unresolved repositories as complete.

## Supported behavior

| Surface | Behavior |
|---|---|
| Automatic PR review | Open/update/reopen/ready events on eligible PRs; inline findings, live progress, then a helper-maintained reusable summary |
| `@muse` top-level PR comment | New eligible human comment starts a separate follow-up response with PR context |
| `@muse` inline review comment | New eligible human comment starts a response in that discussion; actual thread placement must pass pilot acceptance |
| Optional manual fix | Default-branch `workflow_dispatch`; local file edits followed by trusted helper branch/PR publication for human review |

Reviews permit the runtime's read-only tools, including native file listing/search,
web tools, resource inspection, and CI status/log inspection. Backend and network
support for web tools still requires live verification; permission is not proof
that a provider supports a tool. Reviews cannot edit code or run project commands.
The optional fix workflow separately authorizes ordinary-file edits.
Tag mode supplies progress tracking; the helper supplies
summary reuse because upstream sticky matching does not reliably recognize
`github-actions[bot]`. Follow-up responses remain in their discussions. The helper verifies a successful
comment-update tool result and publication readback. If the upstream action falls
back to top-level progress for an inline reply, the helper relocates its completed
answer to the validated discussion root before declaring success.

Do not enable issue triage, bot triggers, automatic fixes, approvals, merges,
unrestricted tools, or unrelated automation. The direct action is SHA-pinned;
its installer and dependency resolution remain external trust dependencies.
Read controls are runtime permissions, not an OS sandbox. Findings may publish
before a final stale-head check; do not promise atomic current-head publication.

## References

- [Security](references/security.md): actors, permissions, isolation, and limits.
- [Acceptance](references/acceptance.md): installation, cutover, pilot evidence, rollback.
- [Secrets](references/secrets.md): scoped credentials and secure provisioning.
- [Provenance](references/provenance.md): exact inspected sources and runtime versions.
