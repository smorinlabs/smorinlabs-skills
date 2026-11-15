# muse-github-setup

Install or migrate organization-member Muse GitHub reviews through the official
Anthropic Claude Code Action. Muse remains the model backend. The skill prepares
automatic PR review, new `@muse` comment follow-ups, inline discussion replies,
progress tracking, reusable summaries, and optional manually requested fix PRs.
Neither workflow approves or merges PRs.

**Triggers on:** “install Muse reviews”, “set up Muse in GitHub Actions”,
“migrate Muse from OpenCode”, and requests to add `@muse` PR interactions.
**Arguments:** none; name the repository and whether manual fix PRs are wanted
in ordinary language. This is not a local-review or general Claude setup skill.

## What gets installed

| Managed path | Purpose |
|---|---|
| `.github/workflows/muse-pr-review.yml` | Automatic review on eligible PR open/update/reopen/ready events |
| `.github/workflows/muse-followup.yml` | New eligible top-level or inline PR comments containing `@muse` |
| `.github/workflows/muse-fix-pr.yml` | Optional default-branch manual fix request |
| `.github/scripts/muse_ci.py` | Member authorization, trusted runtime preparation, input recording, final validation and publication |
| `.github/muse-ci/policy.json` | Schema 2 organization/model policy using bare Muse IDs |
| `.github/muse-ci/review-settings.json` | Restricted review permissions |
| `.github/muse-ci/fix-settings.json` | Optional ordinary-file edit permissions |

The installer also maintains marked project-instruction and CODEOWNERS sections.
Surrounding instructions and unrelated files remain intact. Workflows use the
existing activation variable `MUSE_CI_ENABLED`; installation does not change it.
Updates recognize exact previously generated Claude Action files and preserve
their model and optional fixes. Locally modified managed files remain conflicts
that require reviewed reconciliation.

Reviews permit the available read-only tools: native file reads/searches, web
tools, resource inspection, runtime/task listings, and CI status/log inspection.
Editing/writing requires the separate optional fix workflow. Web tools still
need provider/network support; local permission tests do not establish real
WebSearch/WebFetch success.

Live acceptance with the pinned runtime confirmed WebFetch. Native WebSearch
reaches Muse but fails because Meta rejects the CLI's `max_uses` request field;
it remains permitted. The [security reference](../../plugins/muse-github/skills/muse-github-setup/references/security.md)
records the compatibility limit and source.

The finalizer logs read-only tool-call counts and correlated success/error counts.
These diagnostics omit tool arguments and response contents. A successful tool
result establishes execution; verify the returned information separately.

The action shows live progress. A trusted helper consolidates completed automatic reviews
into a reusable marked summary because upstream sticky matching does not reliably
recognize the repository-token bot. Comment follow-ups retain separate responses;
each triggering comment has its own bounded run, so rapid follow-ups do not
replace one another. They may complete in a different order from their requests.
The helper verifies publication and correct discussion placement. When upstream
progress falls back to top level for a child reply, the helper relocates the
completed answer to the validated root and removes the fallback after readback.
When Muse finishes without calling the comment updater, the helper can publish
its successful final response to the uniquely identified, run-linked bot comment.
It verifies the saved body before completing. Failed updater calls and empty
final responses still fail; initial progress text never counts as an answer.
The pilot must prove this temporary progress behavior. Tests do not run in the
credential-bearing model step. Manual fixes use local file edits, then the helper
validates and creates a separate branch/PR for human review.

Inline follow-ups stay in their existing discussion and cannot create a second
review thread. A top-level `@muse` request can ask for new inline findings.

## Models and trust

Fresh installation defaults to `muse-spark-1.3-contributor` and repository secret
`META_MUSE_CI_API_KEY`. Meta may use contributor content for training. Existing
model/tier and credential-scope choices are preserved. The supported alternatives
are `muse-spark-1.3` standard tier and `muse-wonder-1.0`; select them deliberately
with installer `--model`. Private repositories without a prior tier choice need
an owner decision. No Anthropic key is required.

Meta documents Claude Code compatibility; Anthropic does not support non-Claude
backends. The integration pins the official action revision but still trusts its
external installer and resolved runtime dependencies. Every invocation disables
the Anthropic-only inline classifier and routes the main model, aliases and
subagent settings to Muse.

The setup requires current human organization membership, repository write
permission, trusted workflow sources, and verified execution protections.
Repository write access alone is not membership. CODEOWNERS alone cannot prevent
a PR-modified workflow from executing. The model has no shell; project hooks,
skills, plugins, instruction discovery and unapproved MCP servers are suppressed
through non-bare restricted mode and explicit settings. Native read/search controls are runtime
permissions; search exclusions are best-effort. Only the dedicated CI-log
directory is added outside the checkout; runtime state and credential paths
remain excluded. Reviews preserve validated in-checkout symlinks, while
rejecting dangling, escaping, cyclic and credential-path aliases. Manual fixes
reject all symlinks. This is not an OS sandbox. A final stale-head check can diagnose findings already
posted; it cannot guarantee atomic publication against the latest commit.
Read the [security contract](../../plugins/muse-github/skills/muse-github-setup/references/security.md)
before activation.

## Install the skill

| Mode | Use |
|---|---|
| Plugin | Add `/plugin marketplace add smorinlabs/smorinlabs-skills`, then `/plugin install muse-github@smorinlabs-skills` |
| Development | In a local clone, use the installed skill manager to bind `plugins/muse-github/skills/muse-github-setup` to the intended tool; keep the placement on the durable source checkout |
| Direct copy | Copy that skill directory into `~/.claude/skills/muse-github-setup/` for Claude Code or `~/.agents/skills/muse-github-setup/` for Codex |

For Codex plugin installation, follow the local marketplace instructions in the
root README. Installing the skill does not install or activate a consumer workflow.

## Prepare or migrate a repository

> Migrate this organization's Muse reviews from OpenCode to the official Claude
> Code Action, preserving its model and manual fix support.

The skill verifies the existing repository, prepares changes in a worktree, and
runs `scripts/install.py` from its resolved skill directory. Default execution
prints a plan; `--apply` writes local files. `--migrate-opencode` deliberately
replaces recognized legacy managed snapshots. Unknown or modified managed files
are conflicts requiring reviewed reconciliation. The installer preserves root
`opencode.json`/`opencode.jsonc`, unrelated `.opencode/` content, existing model
choice and optional fix support. Repeating the same install must report no changes.

The cutover removes obsolete Muse workflows and deliberately updates exact path
policies and required checks. Activation stays unchanged until the replacement is
ready. The [acceptance guide](../../plugins/muse-github/skills/muse-github-setup/references/acceptance.md)
explains preview/apply, rollback, credentials, policy readback and required evidence.

## Validation and rollout

Future skill changes require validation against the edited source and an actual
pilot. Local installer/helper tests, workflow lint, manifests and skill
loading establish Gate A. One pilot must then demonstrate actual inline findings,
top-level follow-up, same-thread reply, visible progress, summary reuse, repeat
trigger and stale/failure handling. That is Gate B; a green job alone is insufficient.
Only afterward may consumer migration proceed in small verified batches.

The report distinguishes authored, locally validated, PR opened, merged,
installed, activated and live-verified states. It lists every failed or skipped
check and unresolved repository. Generated fix PRs are never approved or merged
as acceptance tests.

The [November 2026 validation report](muse-github-setup-validation.md) records
the completed two-repository rollout, exact live evidence, and remaining limits.

## Provenance

The current action pin is
`anthropics/claude-code-action@f3b070c88125d33dbae5653df5f143101d4ea9dc`.
The [source record](../../plugins/muse-github/skills/muse-github-setup/references/provenance.md)
documents the inspected runtime, source URLs and historical MIT-licensed Meta
cookbook origin. The helper and restricted settings are maintained by this
project; this is not a Meta-issued Action or the Muse Code CLI.
