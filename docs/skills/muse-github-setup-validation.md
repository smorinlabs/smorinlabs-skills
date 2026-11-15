# Muse GitHub Action migration validation

Validation snapshot: November 15, 2026. Muse GitHub **0.6.0** is delivered.
The original two review-Action consumers are migrated, activated, and live-verified.
The three additional audit-job installations are also migrated, with each existing
activation state preserved. The live audit pilot passed before the other audit
consumers were migrated incrementally. One audit consumer remains inactive;
installation does not imply model execution there.

The original 0.5.3 delivery covered direct OpenCode Action review workflows and
incorrectly excluded three audit jobs invoking `opencode run`. The continuation
below records the completed broader scope and its separate acceptance evidence.

Source [PR #122](https://github.com/smorinlabs/smorinlabs-skills/pull/122) merged as
[`28ec8c00a9581b1e7d7c813ebba13ba294a67930`](https://github.com/smorinlabs/smorinlabs-skills/commit/28ec8c00a9581b1e7d7c813ebba13ba294a67930).
The delivered skill runs Meta Muse through the official Anthropic Claude Code
Action. It preserves the installed model, root OpenCode configuration, and
optional fix-workflow selection while replacing recognized managed files.

## Original review runtime and source validation, version 0.5.3

| Item | Recorded result |
|---|---|
| Official Action | Immutable revision [`f3b070c88125d33dbae5653df5f143101d4ea9dc`](https://github.com/anthropics/claude-code-action/blob/f3b070c88125d33dbae5653df5f143101d4ea9dc/action.yml) |
| Claude Code | Version `2.1.325`, selected by the pinned Action and observed in pilot logs |
| Agent SDK | Manifest dependency `^0.3.325`; pilot installation resolved `0.3.325` |
| Model | Muse Spark 1.3 Contributor, identifier `muse-spark-1.3-contributor`, with model aliases routed to Muse |
| Provider configuration | Meta endpoint `https://api.meta.ai`; endpoint configuration alone is not independent network-destination proof |
| Final source CI suite | **1,587 passed, 2 skipped** |
| Focused Muse suite | **286 passed** |
| Workflow syntax | All **3** workflow templates passed actionlint |
| Other source checks | CodeQL, generated manifests, old-name, whitespace, and hook checks passed |
| Skill loading | Deep checks passed for Claude Code, Codex, and Muse; static checks reported no errors. Combined result: **0 errors, 2 warnings, 4 informational findings, 0 skips** |
| Independent agent review | Terra's implementation review found no blocker; its **94 targeted tests** passed |

The two static warnings are known limitations: Claude ignores generated
`_generated` manifest metadata, and Muse treats skill `allowed-tools` metadata
as advisory. They are not failed load checks. Runtime permissions are enforced
and tested separately from skill metadata.

The Action pin does not freeze every download or service. Its installer uses
the moving Claude installation script, and the SDK dependency is a version
range. See [source provenance](../../plugins/muse-github/skills/muse-github-setup/references/provenance.md)
for the inspected sources and dependency boundary.

## Repository rollout

| Repository | Installation and acceptance status |
|---|---|
| [`lost-sessions`](https://github.com/smorinlabs/lost-sessions) | **Pilot passed.** Final repair [PR #36](https://github.com/smorinlabs/lost-sessions/pull/36) merged as `9c1d51daf1c17a33546afe4d603f2e33a36084cb`. Generated output was read back, and `MUSE_CI_ENABLED=true` was restored. Deliberately defective acceptance [PR #34](https://github.com/smorinlabs/lost-sessions/pull/34) was **closed without merging**, at head `ffee1585f5130bfb261722f4230da29bed42798a`. |
| [`bitrot-sanitation-skill`](https://github.com/smorinlabs/bitrot-sanitation-skill) | **Batch of one passed.** Migration [PR #5](https://github.com/smorinlabs/bitrot-sanitation-skill/pull/5) merged as `97a533492796affc0c1676e1682fb986a4cb3d8a`. Generated files matched 0.5.3 after readback; the old workflow was removed, replacement workflow policies verified, and original `MUSE_CI_ENABLED=true` restored. Root OpenCode configuration, Contributor model, 60,000-byte diff limit, and unrelated PR #4 were preserved. Test [PR #6](https://github.com/smorinlabs/bitrot-sanitation-skill/pull/6) was **closed without merging**, at head `772573fe507d9aa0d416cd0dee4e0d2124006a77`. |

The final inventory refresh at **09:48 UTC on November 15, 2026** covered
**60 accessible repositories**, **45 workflow directories**, and **239 workflow
files**. All 60 default-branch heads were refreshed; all 21 workflow files across
the three changed repositories were fetched again and their blob hashes verified.
Unchanged heads retained their previously verified workflow snapshots. No
deprecated OpenCode Action references remained. The initial inventory identified
**2 Action consumers** among 237 workflow files.
Three CLI-wrapper integrations were excluded from that initial review-only
delivery; the continuation now includes them. This is accessible-repository coverage, not proof about
inaccessible repositories, historical workflows, or every use of OpenCode.

## Live pilot evidence

The acceptance PR removed required `--session ID` from one documentation
example. The unchanged CLI rejects that example with exit status 2 and
`Missing option '--session'.` No application behavior was deliberately changed.

The matrix spans successive skill versions. Initial automatic inline findings,
web access, and overlapping follow-ups passed on **0.5.2**. The two affected
publication checks were repeated successfully after installing **0.5.3**.

| Feature | Evidence and observed outcome |
|---|---|
| Automatic inline review and visible progress, 0.5.2 | [Run 43696856263](https://github.com/smorinlabs/lost-sessions/actions/runs/43696856263) posted the correct finding on documentation line 13 at reviewed commit `f2ea952f361aaf072e2ad98c8061f72953f31d24`. [Finding](https://github.com/smorinlabs/lost-sessions/pull/34#discussion_r4577742955). Its temporary progress comment was observed and removed after summary publication. |
| Top-level member follow-up, 0.5.2 | [Run 43697100239](https://github.com/smorinlabs/lost-sessions/actions/runs/43697100239) produced a relevant [answer](https://github.com/smorinlabs/lost-sessions/pull/34#issuecomment-6892034285). |
| Independent overlapping follow-up, 0.5.2 | [Run 43697144534](https://github.com/smorinlabs/lost-sessions/actions/runs/43697144534) produced its own [answer](https://github.com/smorinlabs/lost-sessions/pull/34#issuecomment-6892039363). The jobs overlapped for 50 seconds, their Action steps for 38 seconds, and SDK execution for 15.68 seconds. Both requests completed. |
| Actual web-tool behavior, 0.5.2 | The overlapping run recorded one successful WebFetch of public Click documentation and one WebSearch error. The successful job did not turn the search error into a passing WebSearch result. |
| Stale-head refusal, 0.5.2 | [Run 43697662340](https://github.com/smorinlabs/lost-sessions/actions/runs/43697662340) was cancelled after head `e42f77a0cda06c593f44329c990d99d858368ade` advanced to `36d5b4c8baf4d643a5c27437857832059d143206`. Its finalizer refused stale publication. Its earlier progress comment remained as evidence. |
| Latest-head summary reuse and final publication, 0.5.3 | [Run 43699848165](https://github.com/smorinlabs/lost-sessions/actions/runs/43699848165) completed against `ffee1585f5130bfb261722f4230da29bed42798a`. It updated the existing [summary comment 6892012903](https://github.com/smorinlabs/lost-sessions/pull/34#issuecomment-6892012903), retained exactly one summary marker, and removed its temporary progress comment. The guarded final-SDK-response publication path was exercised and read back successfully. |
| Inline child reply without a duplicate discussion, 0.5.3 | [Run 43699876154](https://github.com/smorinlabs/lost-sessions/actions/runs/43699876154) posted the verified [answer](https://github.com/smorinlabs/lost-sessions/pull/34#discussion_r4577842084) under original root `4577742955`. It created **0** new root comments and **0** new top-level issue comments. Successful updater-result publication and readback were verified. |

The final two runs reported 7 and 10 turns respectively, with zero permission
denials. Optional manual fix PRs were not enabled or exercised in this pilot;
their validation is offline only.

## Second repository evidence

The Bitrot migration passed 52 installer migration tests, workflow lint, helper
compilation, exact-template comparison, and independent review. Repeat installation
made zero changes. This requirements repository has no application build/test suite;
none was invented or claimed.

Its test PR added an intentional README link to a missing file. The actual target
was `docs/requirements.md`. Both live runs used Muse and recorded head
`772573fe507d9aa0d416cd0dee4e0d2124006a77` against base
`97a533492796affc0c1676e1682fb986a4cb3d8a`.

| Check | Observed outcome |
|---|---|
| [Automatic review, run 43701036663](https://github.com/smorinlabs/bitrot-sanitation-skill/actions/runs/43701036663) | Correct [inline finding](https://github.com/smorinlabs/bitrot-sanitation-skill/pull/6#discussion_r4577891891) on README line 4, verified [summary](https://github.com/smorinlabs/bitrot-sanitation-skill/pull/6#issuecomment-6892573060), and temporary progress removed. 13 turns, zero permission denials. |
| [Inline follow-up, run 43701223417](https://github.com/smorinlabs/bitrot-sanitation-skill/actions/runs/43701223417) | Relevant [reply](https://github.com/smorinlabs/bitrot-sanitation-skill/pull/6#discussion_r4577896191) in the original discussion, with no new root or top-level issue comment. 9 turns, zero permission denials. |

The repository's review policy now covers only the new review workflow. Its new
follow-up policy preserves the same actor restriction. Optional fixes remain
disabled. No secrets, broader repository access, or organization-wide policy changed.

## Failures, repairs, and remaining limits

The first attempt exhausted its 12-turn budget after posting the correct finding
and an unwanted schema-discovery placeholder. Version 0.5.2 raised review and
follow-up budgets to 24 turns, retained the 10-minute job bound, and instructed
the model to discover schemas without trial posts and reserve final-publication
time. An obsolete event/base mismatch was also refused before model use.

Two 0.5.2 runs exposed further defects. One inline follow-up answered correctly
but also created a separate answer thread. Another completed SDK execution
without calling the updater and therefore failed finalization. Version 0.5.3
denies new inline-comment creation only for inline follow-ups. It also permits
guarded publication of a successful, bounded final SDK response when no updater
was attempted. Failed updater attempts still refuse completion. Both affected
checks passed in lost-sessions runs `43699848165` and `43699876154`.

The following limitations remain part of the result:

- **Native WebSearch compatibility:** Meta rejected the permitted request with
  `API Error: 400 web_search field 'max_uses' is not supported`. Meta documents
  that restriction in its [Messages API](https://dev.meta.ai/docs/protocols/messages).
  No supported Claude Code override was identified. WebSearch remains allowed;
  successful WebFetch does not establish successful native WebSearch.
- **Tool discovery and final publication:** the successful summary-reuse run
  reported no matching updater during discovery. The guarded fallback published
  its actual final SDK text and verified the resulting GitHub comment. SDK
  success alone is not publication proof.
- **Transient model-authored content:** lost-sessions inline run `43699876154` briefly displayed
  body `test` before the verified answer replaced it. Prompt instructions do not
  guarantee that transient content never appears. The permission denial prevents
  new inline threads in that mode; it does not validate the meaning of every
  intermediate response.
- **Stale feedback:** prior comments can remain after cancellation or a head
  change. Finalization checks the head and records the reviewed commit, but
  publication is not atomic with subsequent PR updates.
- **Review-service status:** source CodeRabbit review was pending and later
  cancelled after merge; pilot CodeRabbit was rate-limited. The Bitrot migration's
  CodeRabbit review was still pending at the bounded merge gate. Greptile expired.
  These are unavailable reviews, not passing reviews. Owned CI and the independent
  Terra review provide separate evidence.
- **Tool-result counters:** sanitized logs count actual SDK tool invocations and
  reported results. They do not establish semantic correctness of tool output.
  Local permission probes likewise do not establish live provider behavior.

## Audit-triage continuation, version 0.6.0

Source [PR #124](https://github.com/smorinlabs/smorinlabs-skills/pull/124)
merged as `1a56c966f0b27ceb9ed0247da427b14fbb890b3f`; the existing installed
skill placement was refreshed to that revision. This extends the installer to
recognized audit jobs invoking `opencode run`, separately from ordinary reviews.
Existing documentation repair scope, model, credential scope, and activation
switches are preserved. Reviews do not gain write access.

The source CI suite passed **1,654 tests with 2 skips**. All **67** focused
installer/core/URL tests passed, along with four workflow-template syntax checks,
manifest checks, and Claude Code/Codex deep loads. Real CLI 2.1.325 probes against
a loopback mock verified permitted documentation edits and denied shell,
out-of-scope, and unsafe-symlink writes. Those probes establish permission
behavior, not live provider behavior. Sol and Terra independently reviewed the
shared changes; Terra, Sol, and Luna prepared the three consumer migrations.

CodeRabbit identified four shared-source defects: runtime-module selection,
DNS resolution changing between validation and connection, failure-log ordering,
and retries after a successful branch push but failed PR creation. All four were
verified, fixed or mitigated with regressions, answered, and resolved before merge.
The retry mitigation stops before model use when the exact remote branch exists;
recovery requires inspecting the existing branch rather than generating another
repair. Follow-up CodeRabbit reviews were rate-limited and Greptile was expired.
Those unavailable reviews are not counted as passing reviews.

### Live audit pilot

Lost-sessions [PR #37](https://github.com/smorinlabs/lost-sessions/pull/37)
installed the migration at `00d11b180ee7b030c2e0b31176a22e8510071832`.
No eligible historical failed documentation audit was available. A temporary,
manual-only harness supplied explicitly synthetic failed-run metadata and logs;
the Action, Muse model, scoped edit, prepublication validation, repair PR, and
URL verification were real. No deliberately broken fixture entered the default
branch.

| Check | Verified evidence |
|---|---|
| Live repair and publication | [Run 43745671254](https://github.com/smorinlabs/lost-sessions/actions/runs/43745671254) used CLI 2.1.325 and `muse-spark-1.3-contributor`, repaired only `docs/source/_muse_triage_acceptance.md`, and passed validation before commit/push/PR creation. |
| Output and URL verification | [PR #38](https://github.com/smorinlabs/lost-sessions/pull/38) contained only the test document. Its [URL report](https://github.com/smorinlabs/lost-sessions/pull/38#issuecomment-6899023989) recorded HTTP 200 for `https://example.com/`. The PR was closed without merging. |
| Production rejection | [Run 43745825675](https://github.com/smorinlabs/lost-sessions/actions/runs/43745825675) rejected the synthetic run with `Not a weekly-audit run`; credential/model/publication steps were skipped. This expected failed job is a passing rejection test. |
| Harness removal | [PR #39](https://github.com/smorinlabs/lost-sessions/pull/39) merged as `534b4a3c750a5f25d124fd30e156d72169d77666`. All three temporary files and their exact execution policy were removed. Production policies were retained. |
| Final readback | All six generated audit files matched the installed skill. `MUSE_AUDIT_TRIAGE_ENABLED=true`, the contributor model, root OpenCode config, and all existing review/follow-up files were preserved. |

The pilot's full local checks passed with **444 Python tests** and **20 Bun tests**;
three Python tests were skipped and three deselected. After removing the fifteen
temporary harness tests, the cleanup passed **429 Python tests** and **20 Bun
tests**, with the same skips/deselections. Its remote project checks and Muse
review passed. The large installation PR exceeded the existing Muse review
diff-size limit; that guard was preserved and its refusal was not called a review.

### Incremental audit rollout

Py-launch-blueprint [PR #608](https://github.com/smorinlabs/py-launch-blueprint/pull/608)
merged through its required merge queue as
`cfdfb0789cf7065cdac4f9b4c7046e1cfd186a2b`. Required checks and the queue's CI
passed without bypassing protection. Local checks passed **408 Python tests**
and **20 JavaScript tests**, with six Python skips and five deselections. All
**67** targeted audit tests passed. Press verification and an in-memory test
of its actual compiled transformation confirmed the new policy's organization
changes to the destination owner while its model stays unchanged.

[Run 43747079409](https://github.com/smorinlabs/py-launch-blueprint/actions/runs/43747079409)
replayed the real scheduled audit `42625355979`. Its documentation check had
passed and only its dependency audit failed. Preparation reported
`No docs failure in run 42625355979; agent run skipped`; the credential, model,
and publication steps were skipped. This verifies the production skip path,
not another live model repair. The existing `MUSE_CI_ENABLED=true` was preserved.
CodeRabbit remained pending at the bounded pre-queue review gate; Codex reported
no findings and Claude's explicitly limited review reported no issues. Greptile
was unavailable. No open inline review threads existed at that gate.

The third, private consumer was then installed and read back against the same
six generated templates. Its local checks passed **397 Python tests** and
**20 Bun tests**, with six Python skips and four deselections; **66** targeted
audit tests passed. A manual default-branch dispatch produced a skipped triage
job, confirming its existing inactive state. No credential was added and no
activation or model-tier choice changed. This is installation/inactivity evidence,
not live model acceptance. Repository identity, exact commits, run links, and
private CI limitations are retained in the private rollout ledger.

Final readbacks found no executable OpenCode invocation in the migrated GitHub
workflows. Existing ordinary review/follow-up files and unrelated configuration
were preserved. This continuation covers the three specifically authorized
audit consumers; it is not a fresh organization-wide inventory.

Audit events receive the helper's frozen failure bundle: the pinned Action does
not instantiate its GitHub CI MCP server outside PR contexts. Read-only tools
remain permitted, including native WebSearch with the existing documented Meta
compatibility limitation. Runtime permissions are not an OS sandbox.

## Rollback

Follow the existing [legacy cutover and rollback procedure](../../plugins/muse-github/skills/muse-github-setup/references/acceptance.md#legacy-cutover-and-rollback).
Rollback includes the reviewed installation change and any deliberately changed
workflow-path policies or activation value. Preserve unrelated configuration and
avoid running both workflow generations together.

Both original review consumers and the three audit installations passed their
applicable rollout gates. Keep the test PRs closed
without merging and retain their run/comment evidence. Refresh inventory and
repeat the relevant validation before extending this result to new repositories
or a different Action/runtime revision.
