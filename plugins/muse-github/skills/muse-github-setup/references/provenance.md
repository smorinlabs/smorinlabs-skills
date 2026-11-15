# Source snapshots

Source review refreshed November 14, 2026. GitHub's comparison reported current
`v1` identical to `f3b070c88125d33dbae5653df5f143101d4ea9dc`. These are inspected
sources, not live workflow acceptance results.

| Source | Revision and use |
|---|---|
| [Official Claude Code Action](https://github.com/anthropics/claude-code-action/blob/f3b070c88125d33dbae5653df5f143101d4ea9dc/action.yml) | Immutable action pin; inputs, public outputs, dependency installation, classifier post-step |
| [Runtime orchestrator](https://github.com/anthropics/claude-code-action/blob/f3b070c88125d33dbae5653df5f143101d4ea9dc/src/entrypoints/run.ts) | Claude Code `2.1.325` installer; setup, model execution, finalization |
| [Mode detector](https://github.com/anthropics/claude-code-action/blob/f3b070c88125d33dbae5653df5f143101d4ea9dc/src/modes/detector.ts) | Tracking forces tag mode; dispatch tracking unsupported |
| [SDK argument mapping](https://github.com/anthropics/claude-code-action/blob/f3b070c88125d33dbae5653df5f143101d4ea9dc/base-action/src/parse-sdk-options.ts) | Tool-rule merging, setting-source mapping, extraArgs, empty-value limitation |
| [GitHub MCP configuration](https://github.com/anthropics/claude-code-action/blob/f3b070c88125d33dbae5653df5f143101d4ea9dc/src/mcp/install-mcp-server.ts) | Minimal comment/inline servers versus broader GitHub server |
| [Initial comment creation](https://github.com/anthropics/claude-code-action/blob/f3b070c88125d33dbae5653df5f143101d4ea9dc/src/github/operations/comments/create-initial.ts) | Inline thread replies, fallback behavior, Claude-specific sticky matcher |
| [Inline classifier](https://github.com/anthropics/claude-code-action/blob/f3b070c88125d33dbae5653df5f143101d4ea9dc/src/entrypoints/post-buffered-inline-comments.ts) | Direct Anthropic classifier request; disabled for Muse |
| [Meta coding agents](https://dev.meta.ai/docs/coding-agents) | Meta base host, bearer auth, supported Muse model routing and aliases |
| [Gateway action recipe](https://code.claude.com/docs/en/llm-gateway-connect#github-actions) | Bearer token plus `anthropic_api_key` launch-check input |
| [Anthropic support boundary](https://code.claude.com/docs/en/llm-gateway) | Non-Claude backends excluded from Anthropic support |
| [CLI restricted mode](https://code.claude.com/docs/en/cli-reference) | Non-bare read-only tool exposure with restricted file access and explicit settings |

The direct action selects Bun `1.4.4` through SHA-pinned setup-bun and installs
Claude Code `2.1.325` through the moving `https://claude.ai/install.sh` script.
Its manifest declares Agent SDK `^0.3.325`; installation uses
`bun install --production`. Record actual resolved versions. A direct SHA pin
does not pin every external installer, dependency, download, or service.

## Legacy origin

The earlier skill adapted Meta Platforms, Inc. and affiliates'
[MIT-licensed cookbook](https://github.com/meta-models/meta-model-cookbook/tree/c5a9882b4c7f3900e9c93122249d37317c8abff4/03_use_cases/11_github_repo_agent)
with locally authored restricted profiles and helpers. Its former action was
[OpenCode v1.18.31](https://github.com/anomalyco/opencode/blob/a97622c801f4ca571530ddc51076af659a9c32cd/github/action.yml).
The [OpenCode action removal](https://github.com/anomalyco/opencode/pull/59032)
is the migration motivation, not the selected runtime.

`references/legacy/` holds exact managed-file snapshots used for deliberate
migration. The cookbook notice remains in `.github/muse-ci/NOTICE`. Upstream
Actions are referenced rather than copied. The helper, permission settings,
summary consolidation/thread relocation and workflow policy are maintained by this project;
they are not a Meta-issued Action or an unmodified Anthropic example. This runs
Muse through Claude Code, not the Muse Code CLI.

The pinned action can fall back to top-level progress when asked to reply to a
child review comment. GitHub requires the top-level review-comment ID; the helper
validates that root and relocates the completed answer after publication proof.
Source: [GitHub reply API](https://docs.github.com/en/rest/pulls/comments#create-a-reply-for-a-review-comment).

## Validation status

Claude Action migration validation remains pending until the current worktree's
local checks and pilot matrix are recorded. Historical OpenCode results establish
only that historical installation. See [acceptance](acceptance.md) for the gates
and required evidence.
