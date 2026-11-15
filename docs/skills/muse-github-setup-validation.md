# Muse GitHub Action migration validation

Validation snapshot: November 15, 2026. Muse GitHub **0.5.3** is delivered.
Both identified Action consumers are migrated, activated, and live-verified.
The first pilot passed before the second repository was migrated.

Source [PR #122](https://github.com/smorinlabs/smorinlabs-skills/pull/122) merged as
[`28ec8c00a9581b1e7d7c813ebba13ba294a67930`](https://github.com/smorinlabs/smorinlabs-skills/commit/28ec8c00a9581b1e7d7c813ebba13ba294a67930).
The delivered skill runs Meta Muse through the official Anthropic Claude Code
Action. It preserves the installed model, root OpenCode configuration, and
optional fix-workflow selection while replacing recognized managed files.

## Runtime and source validation

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
Three CLI-wrapper integrations were excluded because they are outside this
Action migration. This is accessible-repository coverage, not proof about
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

## Rollback

Follow the existing [legacy cutover and rollback procedure](../../plugins/muse-github/skills/muse-github-setup/references/acceptance.md#legacy-cutover-and-rollback).
Rollback includes the reviewed installation change and any deliberately changed
workflow-path policies or activation value. Preserve unrelated configuration and
avoid running both workflow generations together.

Both identified consumers passed their rollout gates. Keep the test PRs closed
without merging and retain their run/comment evidence. Refresh inventory and
repeat the relevant validation before extending this result to new repositories
or a different Action/runtime revision.
