---
name: session-move
allowed-tools: Bash, AskUserQuestion
argument-hint: "[destination-session] [--window <label|id> --session <label|id>]"
arguments: [destination]
description: Move a Rex window (a tab in the Rex app) from one Rex session to another on the same computer. Rex cannot move a window between sessions, so this recreates it in the destination with the same agent (Claude Code, Codex, or Muse), the same conversation resumed by ID, the same working directory, and the same window name, then closes the old window. Use when the user says "move this window to <session>", "move this tab to another session", "session move", or wants a running agent conversation relocated between Rex sessions. Not for launching a new side idea in a fresh agent (session-spinoff), continuing work in a new conversation or on another machine (session-handoff), copying a conversation into a new worktree (agent-fork), or general Rex tab and session control (rex).
---

# session-move

Relocate a running agent conversation from one Rex session to another. Rex has
no command for this (`rex window move` only reorders windows inside one
session), so the move is a recreation: a new window in the destination session
resumes the same conversation, and the old window closes.

> **ONE CONVERSATION, ONE LIVE COPY.** Two agents resumed on the same
> conversation ID both append to one transcript, and the copy that loaded first
> never sees the other's turns. The new window therefore waits, the old agent
> stops, and only then does the new window resume. If the old agent does not
> exit, nothing resumes.

## Contract

- **The unit is one Rex window with exactly one pane** running Claude Code,
  Codex, or Muse. Anything else is refused with the reason.
- **Same computer only.** A Rex session can span computers. A window that runs
  on another computer is refused; say that moving across computers is out of
  scope.
- **Everything stays the same:** the agent (never switch tools), the
  conversation ID (never `--fork-session`, which makes a different
  conversation), the working directory, and the window name. A name Rex
  generated itself (`Window 1a2b3c4d`) is not copied; Rex names the new window.
- **The destination is the user's choice.** An existing session is reused. A
  session that does not exist is created.
- **The helper decides, not prose.** `scripts/session-move` reads Rex and the
  agents, applies the refusal rules, builds the launch command, and checks the
  result. Do not hand-write `rex … -- claude --resume …`.
- **The new window falls back to a shell.** The helper launches through
  `--shell=none -- "$SHELL" -ilc '"$@"; exec "$0" -il' "$SHELL" …`, the same
  launch form `session-spinoff` uses, so quitting the agent leaves a prompt
  instead of closing the tab. When `$SHELL` is not zsh, bash, sh, dash, or
  ksh (fish and tcsh reject that wrapper), the helper uses `/bin/zsh`.
- **Prompts in the new window belong to the user.** If the resumed agent shows
  an update or folder-trust prompt, report it; never answer it.
- **Only this move's own leftovers are removed.** An emptied source session is
  left in place and reported.

## Resolve the helper

`scripts/session-move` lives beside this file. Resolve it through the real path
so it works from a symlinked placement:

```bash
MOVE="$(dirname "$(realpath "<skill-dir>/SKILL.md")")/scripts/session-move"
T="$(mktemp -d)"; echo "MOVE=$MOVE"; echo "T=$T"
```

Shell variables do not survive between tool calls, so use the two printed
paths literally wherever `$MOVE` and `$T` appear below.

Run it as `uv run --script "$MOVE" <verb> ...` (stdlib only, Python ≥ 3.11).
Each verb prints JSON; a refusal prints one line to stderr and exits 2. The
commands below save each result for the next verb and print it with the exit
code. The
helper finds Codex and Muse conversations through the sibling
`../session-agent-list/scripts/session-inventory`; if that file is missing it
says so in the refusal.

## Workflow

### 1. Pin the source and the destination

- **Source.** Default: the window this agent runs in (a *self-move*). To move
  a different window, the user names it; pass `--session` and `--window`.
- **Destination.** Use the session named in the arguments. If none was named,
  run `rex session list --json`, state the session labels in one line of
  visible text, and ask one question immediately after it: up to three
  existing sessions (not the source session) plus "New session", whose name
  the user types.

### 2. Plan (read-only)

```bash
uv run --script "$MOVE" plan --to "<destination>" > "$T/plan.json"; echo "exit=$?"; cat "$T/plan.json"
# another window:  plan --to "<destination>" --session "<S>" --window "<W>"
```

- **Exit 2:** relay the reason and stop. See [Refusals](#refusals).
- **`destination.exists` is false and `destination.near` is not empty:** the
  name is close to an existing session. Ask whether to use that session or
  create the new one.
- **`destination.exists` is false and `near` is empty:** say the session will
  be created. Do not ask.

Then state the move in one line: window name, agent, the first eight
characters of `conversation_id`, `cwd`, source session, destination session.

### 3. Self-move only: check for background work

If `self` is true and this agent has background shells, subagents, or scheduled
wakeups running, they end when the window closes. Say which, and ask once
whether to move anyway.

### 4. Arm the destination window

```bash
uv run --script "$MOVE" arm < "$T/plan.json" > "$T/armed.json"; echo "exit=$?"; cat "$T/armed.json"
```

This creates the destination window (and the session, when new). The window
runs the helper's `handoff`, which waits. Nothing has changed in the source
window yet.

- **Exit 0, `armed` true:** the handoff is waiting on the same computer, in the
  same directory, under the same window name.
- **Exit 3:** read `checks` and report which one is false. The helper already
  removed the new window (and a session it had just created). Stop.

To cancel after this point, run `uv run --script "$MOVE" abort < "$T/armed.json"`.
It removes the waiting window and refuses if the conversation already resumed.

### 5. Release

**Moving another window:**

```bash
uv run --script "$MOVE" go --wait < "$T/armed.json"; echo "exit=$?"
```

The handoff closes the old window, waits for the old agent to exit, and resumes
the conversation. `go --wait` returns when the destination window runs the
agent. Report:

| Field | Meaning |
|---|---|
| `resumed` | The destination window runs the same agent. |
| `same_conversation` | `true`: the agent's own record shows the same conversation ID (Claude Code and Muse). `null`: Codex keeps no such record, so only the process was checked. `false`: a different conversation; say so plainly. |
| `old_window_closed` | The source window is gone. |
| `jump` | The command that switches the Rex app to the new window. Print it and offer to run it. It names the app with `-C` when exactly one is connected; with several, ask which device. |

If `source.only_window` was true in the plan, add that the source session is
now empty and was left in place. On exit 3, report the fields and tell the user
to look at the destination window: it shows the helper's last message and, if
the resume command failed, a shell prompt with that command printed above it.

**Self-move:**

```bash
uv run --script "$MOVE" go < "$T/armed.json"
```

Then write the final message and stop. Make no further tool calls.

> Moving this conversation to session "<destination>". This tab closes when
> this message ends, and the conversation continues there.

The handoff waits for this turn to end, closes this window, and resumes the
conversation in the destination. It then tries to switch the Rex app to the new
tab: it does so only when exactly one Rex app is connected, and the app may
refuse (its Remote Control setting). Otherwise the user opens the destination
session themselves. A long final message delays the move, and anything after
`go` that keeps the turn running delays it too.

## Refusals

| The helper says | Tell the user |
|---|---|
| `runs on a different computer` | Moving across computers is out of scope. Suggest `session-handoff` for continuing elsewhere. |
| `cannot confirm the window runs on this computer` | Rex reported no host for the pane. Nothing was changed. |
| `has N panes` | Only a single-pane window can move. |
| `not running Claude Code, Codex, or Muse` | Name the foreground program the helper reported. |
| `cannot tell which … conversation` | Relay the detail. For several live Codex conversations in one directory, rerun `plan` with `--conversation <id>` once the user picks one. |
| `not idle (status: busy)` | The other agent is mid-turn. Wait or ask the user. |
| `background shell running` | The move would end that shell. Ask the user. |
| `transcript changed Ns ago` | Codex and Muse have no idle signal; wait a few seconds and plan again. |
| `already in that session` | Nothing to do. |
| `N sessions are labelled …` | Ask which one and pass its session ID. |

## Limits to state when they apply

- **Launch flags are not carried over.** The resume command is
  `claude --resume <id>`, `codex resume <id>`, or `muse resume <id>`. A model,
  permission mode, or other flag given when the old agent started is not
  repeated.
- **Muse prints a warning on resume** that the previous run ended without a
  clean shutdown. That is the old window closing; the conversation is intact.
- **A self-move needs a turn-end signal.** Claude Code publishes its status;
  for Codex and Muse the handoff waits until the transcript has been quiet for
  six seconds.

## Red Flags

| Thought | Reality |
|---|---|
| "Start the new one first, check it, then close the old one" | That is two live copies on one transcript. The new window waits; the helper enforces the order. |
| "`--fork-session` avoids the conflict" | It creates a different conversation ID. The user asked for the same conversation. |
| "I'll close my own window with `rex window close`" | That kills this agent mid-tool-call and the resumed conversation shows an interrupted turn. Run `go` and end the turn. |
| "I'll launch `rex window new … -- claude --resume <id>` myself" | That tab closes when the agent exits and skips every check. Use `arm`. |
| "The window opened, so the move worked" | Read `resumed` and `same_conversation` from `go --wait`. |
| "An update or trust prompt is blocking the new window, I'll press Enter" | Those are the user's decisions. Report the prompt. |

## See also

- `session-spinoff` — starts a *new* agent on a side idea in a Rex tab; it
  never moves an existing conversation.
- `session-handoff` — continues the work in a *new* conversation, including on
  another computer.
- `session-agent-list` — lists agent conversations and their resume commands.
- `agent-fork` — copies this conversation into a new worktree.
- `rex` — the full Rex CLI guide (`rex skill show`).
