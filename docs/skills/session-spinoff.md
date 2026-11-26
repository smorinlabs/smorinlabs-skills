# session-spinoff

The launcher of the session septet. An idea comes up mid-session — a bug in
another repo, a feature worth building, something that needs fixing — and you
don't want it to derail what you're doing or fill your context window.
`session-spinoff` writes a self-contained brief for that idea (using
`session-handoff`'s content contract, scoped to the new idea), finds the target
repo (`repo-finder`), creates a worktree from `origin/<default-branch>`, and
launches a fresh Claude Code, Codex, Muse, or Antigravity (`agy -i`) agent in a
Rex tab with the brief as its first prompt. Your current session is never
modified.

Placement is always your choice. A read-only snapshot sorts your Rex sessions
into tiers from facts — tier 1 has a tab that started in the target repo or one
of its worktrees, or an agent whose recent transcript shows it working in that
repo (so sessions started from a parent directory such as `~/c` still match) — and the agent orders sessions within each tier by how
closely their labels relate to the idea. The top three are offered with the
directories their tabs work in, and "New session" is always an option. The
same question confirms the launch directory: the worktree root by default, a
package directory for monorepo work, or a parent directory for ideas that span
repos. After launch the skill verifies that the agent is running in that
directory, prints the receipt, and monitors the new Rex pane for 5–10 minutes
(at the agent's judgment) across all four agents (`claude`, `codex`, `muse`,
and `agy`) to make sure kickoff takes hold. By default it inspects the terminal
output and clears workspace trust prompts and early permission prompts that
would otherwise stall startup, re-verifying after each approval while still
surfacing hard failures (crashes, auth errors) or substantive task questions.
Pass `--monitor-only` to watch and surface blockers without sending input to
the pane. The agent runs inside your login shell, so quitting it leaves the
tab open at a normal shell prompt instead of closing the tab. A
new session gets a proposed `<type>-<topic>` name you confirm or edit. The
agent you are running now is the default. The skill finishes with a kickoff
summary and offers to run the `rex -C <client> do session.select …` command
that jumps the Rex app to the new tab. The jump needs Rex's Remote Control
setting; the skill never changes it.

Deterministic steps — the argument gate, the snapshot, building the commands,
and bounded Rex pane watching (`watch`) — run through the bundled stdlib
`scripts/spinoff-plan` helper.

**Triggers on:** "spin this off", "launch this in Rex", "start a new session
for this in <repo>", "open a new agent for that bug", or any ask to work a side
idea in its own session. NOT continuing the current work elsewhere
(`session-handoff`), not forking this conversation (`agent-fork`), and not
moving a running conversation to another Rex session (`session-move`).

**Arguments:** `[idea] [--new | --session <label|id>] [--name <session-name>]
[--repo <name|path>] [--claude | --codex | --muse | --agy] [--monitor-only]
[--dry-run]`

| Argument | Skips |
|---|---|
| `idea` | Inferring the idea from the conversation |
| `--new` | The placement question; always creates a new Rex session |
| `--session <label\|id>` | The placement question; adds a tab to that session |
| `--name <session-name>` | The name confirmation; implies `--new` |
| `--repo <name\|path>` | Inferring the target repo |
| `--claude` / `--codex` / `--muse` / `--agy` | The agent question |
| `--monitor-only` | Auto-clearing kickoff trust and permission prompts; monitors and surfaces blockers instead |
| `--dry-run` | All writes; prints the brief and the commands |

Refused before anything runs: `--new` with `--session`, `--name` with
`--session`, more than one agent flag.

**Requires:** Rex with the `rex` CLI, `git`, `uv`, and the
agent CLI you launch (`claude`, `codex`, `muse`, or `agy`).

## Install

| Mode | When | How |
|---|---|---|
| Plugin (recommended) | You just want to use it | `/plugin install session@smorinlabs-skills` |
| Dev symlink | You want to tweak/iterate | `git clone https://github.com/smorinlabs/smorinlabs-skills` then `ln -s "$(pwd)/smorinlabs-skills/plugins/session/skills/session-spinoff" ~/.claude/skills/session-spinoff` |
| Direct copy | No marketplace access | copy `plugins/session/skills/session-spinoff/` into `~/.claude/skills/` |

**Codex:** install from a terminal:

```sh
codex plugin marketplace add smorinlabs/smorinlabs-skills
codex plugin add session@smorinlabs-skills
```

**Antigravity (`agy`):** install the `session` plugin directly:

```sh
agy plugin install https://github.com/smorinlabs/smorinlabs-skills/tree/main/plugins/session
```

For development, link the cloned skill into `~/.agents/skills` (Codex's current
skills location). **Muse, OpenCode, and Antigravity** also load skills from
`~/.agents/skills`, so the same dev symlink serves them.

## Example session

> Working in `smorin-skills`, you notice `repo-finder` reports a worktree as a
> plain checkout. "Spin this off into the repo-finder repo."
> → The skill writes a brief quoting the misreport and the path that triggered
> it, resolves `smorinlabs-skills`, and asks one question: placement, with
> any session with a tab already in that repo ranked first, then other
> sessions, then "New session"; agent, with `claude` marked as current. You
> pick "New session" and confirm the name `fix-repo-finder-worktrees`. It
> creates `../smorinlabs-skills-repo-finder-worktrees` on
> `fix/repo-finder-worktrees` from `origin/main`, starts `claude` there with
> the brief, prints the receipt and the jump command, and offers to switch the
> Rex app to the new tab.
