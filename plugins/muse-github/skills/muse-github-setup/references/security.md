# Security and compatibility

This installation keeps Muse as the model backend of the official Claude Code
Action. Meta documents that integration; Anthropic explicitly excludes
non-Claude models from support. Runtime permissions reduce the capabilities of
a trusted Claude runtime. They do not create an operating-system sandbox.

## Authorized actors and workflow sources

| Surface | Required conditions |
|---|---|
| Automatic review | Open, non-draft, same-repository PR into the default branch; PR author, original actor, and rerun actor are current human organization members with repository write access |
| Follow-up | Same eligible PR; newly created top-level or inline review comment containing `@muse`; comment author equals original actor; original/rerun actors meet the same member/write checks |
| Manual fix | `workflow_dispatch` from the default branch; original/rerun actors meet the same member/write checks |
| Excluded | Forks, bots, outside collaborators, drafts, issue triage, edited/deleted comments, personal-owner repositories, reused/self-hosted runners |

The helper checks organization membership and repository permission separately.
The Members-read App token belongs only in authorization. Its private key never
reaches the model step. A failed lookup refuses execution; `author_association`
is not proof of current membership.

Require active GitHub workflow execution policies for the exact installed paths
and their permitted events, scoped to the approved organization team or existing
explicitly approved maintainers. Preserve inherited policies. Verify either that
all workflow writers are trusted members or that server-enforced file-path
restrictions block outside writers with only the approved member bypass. Inspect
open PRs for pre-existing workflow edits. CODEOWNERS and required human reviews
protect merge; they cannot stop a modified PR workflow from executing beforehand.
Unavailable enforcement is an activation blocker, not permission to weaken the
boundary. Do not add organization-wide policies or privileged Apps implicitly.

Sources: [execution protections](https://docs.github.com/en/actions/how-tos/administer/control-workflow-execution),
[push-ruleset path restrictions](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#restrict-file-paths).

## Credentials and capabilities

Review policy permits available read-only tools. File reads/searches, web tools,
MCP resource inspection, runtime/task listings, and CI status/log inspection are
allowed. Editing and writing require the separately authorized optional fix
workflow. Permission does not establish backend support for a web tool.

| Control | Review and follow-up | Optional manual fix |
|---|---|---|
| Repository token | `contents: read`, `pull-requests: write`; optional read permissions for CI metadata | `contents: write`, `pull-requests: write` for helper publication |
| Model built-ins | Read-only inspection tools; no shell or edits | Read-only inspection tools plus ordinary-file edits; no shell |
| GitHub model tools | Action's tracking-comment updater and explicit inline-comment tool; CI metadata/log inspection | No model-controlled GitHub publication |
| Input revision | Recorded exact PR base/head commits | Exact default-branch dispatch commit |
| Publication | Immediate inline findings; progress; helper summary consolidation after successful checks | Helper validates, commits, pushes new branch, creates separate PR |

`pull-requests: write` permits top-level PR comments through GitHub's issue-comment
endpoints. `issues: write` is not needed for this PR-only integration. Optional
CI inspection may need `actions: read` and `checks: read`; grant only what the
chosen feature uses. Sources: [PR comment permissions](https://docs.github.com/en/rest/issues/comments#create-an-issue-comment).

The action receives an explicit repository `github_token`, so it skips the Claude
GitHub App token exchange. No `id-token: write` is required for that path. The
repository token can do more than the exposed model tools; the trusted action,
helper, and runtime remain part of the security boundary.

The Meta secret `META_MUSE_CI_API_KEY` is supplied as `ANTHROPIC_AUTH_TOKEN` and as
action `anthropic_api_key`. The latter satisfies its launch check. Routing uses
`ANTHROPIC_BASE_URL=https://api.meta.ai`, with every main/alias/subagent model
variable set to the chosen Muse ID. Do not configure an Anthropic fallback.
`classify_inline_comments: 'false'` is mandatory on every invocation: the pinned
classifier otherwise sends the supplied key and buffered comments directly to
Anthropic. The false setting publishes inline findings immediately.

## Configuration and execution isolation

Configuration and the helper come from the trusted base/default revision. The
helper verifies the exact commit reported by the checkout step separately from
the PR comparison base. Follow-ups can therefore use current default-branch
configuration when an older PR still records an earlier comparison base. The
helper copies runtime settings, state, and itself outside the checkout; it sets
isolated `CLAUDE_CONFIG_DIR` and XDG directories without overriding `HOME`.
It supplies a trusted absolute settings path explicitly with `--settings`.
Profiles accept only the supported permission and isolation fields. Environment,
provider credentials, and executable helper configuration are rejected before
runtime settings are written. Workflow environment controls Muse routing.

The action uses non-bare `--restricted`, `--disable-slash-commands`, nonempty
`--setting-sources user`, and `--strict-mcp-config`. Explicit settings set
`disableAllHooks: true`, `autoMemoryEnabled: false`, and
`claudeMdExcludes: ["**"]`. This retains native read-only tools while suppressing
project settings, instructions, hooks, skills, and unapproved MCP discovery.
The profile does not depend on undocumented environment switches. Do not add
plugins, project executable tools, dependency installs, or broad GitHub MCP
permissions. Shell execution remains denied. The runtime probe must confirm
that project-controlled hooks, skills, and executable plugins do not load.

`--tools` supplies a nonempty exclusive built-in list. `--allowedTools` only
pre-approves calls and is not an exclusive inventory. Bare-name denials remove
Bash, edit tools in reviews, subagents, skills, and file-operation MCP tools.
An explicit final permission mode overrides tag mode's default `auto`/`acceptEdits`
and injected git-wrapper allow rules. Do not use an empty `--tools ""` argument:
the pinned action parser does not preserve empty option values correctly.
When updating the runtime, compare its available read-only tools with both the
built-in inventory and approval rules. Add newly available read-only tools;
do not carry forward a narrower inventory without checking it.

Generated settings block file-tool reads and writes outside working directories,
deny credential-like filenames, and deny Git/runtime credential locations.
Exact tracked regular data fixtures such as `tests/fixtures/x.env.json` receive
escaped read exceptions after checkout validation. These do not grant edits or
allow `.env.local` and other credential-like files. Supplied trusted deny rules
remain effective. Filename classification does not establish that a file's
contents are safe to disclose.
CLI 2.1.325 permits direct Read and file-targeted Grep for these exact exceptions;
directory-wide Grep can still omit them. Use the known path from the PR diff
when inspecting such a fixture. This runtime limitation does not remove the
read-only tools from the model.
The action configures Git authentication, so `persist-credentials: false` alone
is insufficient. The helper rejects submodules and credential-like files before model use.
Manual fixes reject every symlink. Reviews and follow-ups allow an existing
in-checkout file or directory alias only after bounded validation of every link
hop and target descendant. Targets must exist inside the checkout and remain
regular files/directories. Links into `.git`, sensitive filenames, or known
credential trees fail, as do dangling links, escapes and cycles. Inspection is
bounded to 10,000 path components, 40 link hops per resolution, and 64 directory
levels. The validator preserves accepted aliases; it does not rewrite consumer
symlinks or enable the skills/instructions they point to. Filename rules cannot find secrets
embedded in arbitrary source; inspect repository-specific conventions.

The pinned action dereferences symlinks when snapshotting startup configuration.
To keep final workspace verification reliable, preparation rejects a symlink
located at or beneath `.claude`, `.husky`, `.mcp.json`, `.claude.json`,
`.gitmodules`, `.ripgreprc`, `CLAUDE.md`, or `CLAUDE.local.md` before model use.
A safe alias originating elsewhere may point into a regular directory under
those paths. For example, an alias in `.agents/skills/` may point to a regular
directory in `.claude/skills/`; configuration discovery remains disabled.

The helper creates `RUNNER_TEMP/github-ci-logs` and exposes only that directory
through `--add-dir`, alongside the checkout. The action's read-only CI log tool
writes `job-<numeric-job-id>.log` files there. The model may inspect those logs;
the rest of runner temp remains outside its working directories. The helper's
own runtime directory retains explicit Read/Edit denials. Model inspection of
CI logs does not authorize running the commands printed inside them.
Source: [CI server](https://github.com/anthropics/claude-code-action/blob/f3b070c88125d33dbae5653df5f143101d4ea9dc/src/mcp/github-actions-server.ts).

Native Read denials apply to Grep/Glob on a best-effort basis. Do not describe
these permissions as OS isolation or as restrictions on arbitrary subprocesses.
Runtime acceptance must probe shell/edit denials, project startup suppression,
fake credential reads/searches, safe alias reads/searches, denial through
unsafe aliases, and permitted log reads. Sources:
[CLI restricted mode and settings flags](https://code.claude.com/docs/en/cli-reference),
[permission rules](https://code.claude.com/docs/en/permissions#read-and-edit),
[outside-directory file access](https://code.claude.com/docs/en/settings-reference#permissionsblockreadsoutsideworkingdirectories).

`WebSearch` and `WebFetch` are permitted. Their operation depends on the provider,
network, and Claude runtime. A local mock proves tool exposure and permission
behavior, not real web access. In the inspected runtime, WebFetch performs a
claude.ai domain-safety request; do not claim all network traffic stays on the
Meta endpoint or that a mock proves external web success. The main model and
all model aliases remain routed to Muse. Record actual provider/tool failures
rather than silently disabling the requested read-only capability.

The action fetches the current base branch when restoring sensitive startup
files and saves PR variants under `.claude-pr/`. Those variants are untrusted
review data. Final verification records the action-fetched restoration revision,
requires it to descend from the trusted checkout, and compares restored bytes
against that revision. The PR comparison base may be older. Unrelated workspace
changes and rewritten base history are still rejected. Configuration restoration
is an additional defense, not a substitute for suppressed discovery.

## Progress, summaries, and stale findings

`track_progress: true` selects tag mode even with an explicit prompt. An explicit
prompt bypasses the upstream mention check, so the trusted helper must enforce
`@muse` on follow-ups. The action creates a progress comment and updates it through
its minimal comment tool. Inline review events attempt a discussion reply. The pinned action addresses
the triggering comment ID, but GitHub accepts only the top-level discussion ID.
When a member replies to a reply, upstream progress may therefore fall back to a
top-level comment. Preparation validates the real discussion root without
changing the original member event. Finalization posts the completed fallback
answer to that root, verifies the new reply, then deletes the fallback. Progress
may temporarily appear at top level; final thread placement must pass the pilot.

Set `use_sticky_comment: 'false'`. Its upstream matcher targets Claude bot
identities, which do not reliably match `github-actions[bot]`. For automatic
reviews, the helper locates the new run-linked bot comment, upserts the marked
summary, and deletes the transient comment only after successful publication.
Finalization requires action outcome and conclusion success, a successful
`update_claude_comment` tool result in the SDK execution log, and new bot-comment
readback matching its exact ID and URL. Normal responses must contain the exact
run URL. The pinned action cannot append that link to an inline event's top-level
fallback, so the helper appends the trusted run link when repairing that specific
case and verifies the resulting thread reply. An untouched initial progress
comment is not completion evidence. Ambiguous matching or wrong-thread
publication fails.
Follow-ups retain their individual responses.
There may briefly be two comments; consolidation is not atomic.

The helper records the reviewed SHA and checks the live head before finalization.
Every inline finding must name that recorded SHA. The upstream inline tool can
otherwise default to the latest head. Concurrency cancels older PR runs, but
findings already published may remain after cancellation or a stale-head failure.
Follow-ups use a separate concurrency group for each triggering comment. Distinct
comments may run concurrently; a newer request does not replace an older pending
request, and an automatic review does not cancel a follow-up. Each response is
correlated with its own run and comment IDs before placement or cleanup.
When finalization runs after an unsuccessful action, it attempts to report an
advanced head before refusing publication. A hard cancellation can prevent the
finalizer from running; no stale diagnostic is guaranteed in that case.
The recorded run summary is the authoritative input record. Never claim atomic
publication against the latest commit or automatic retraction of stale findings.

## Fix and dependency limits

The manual model edits ordinary files only. A trusted helper validates all changed
paths before committing, pushing a fresh branch, and creating a PR for human
review. Invalid or failed runs do not publish; an empty diff creates no PR.
Protected CI/agent files, credentials, symlinks, approval, and merging remain
outside the model's capability contract. Ordinary PR CI runs tests afterward.

The direct action SHA is pinned; its installer URL and transitive resolution
remain external dependencies. See [provenance](provenance.md). Record actual
runtime versions at acceptance and recheck isolation when updating them.
