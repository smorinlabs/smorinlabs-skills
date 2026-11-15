# session-move

The mover of the session septet. You have an agent conversation running in one
Rex session and you want it in another: a tab that ended up in the wrong
session, or a set of sessions you are reorganizing. Rex has no command for
this, because `rex window move` only reorders windows inside one session.
`session-move` recreates the window in the destination session and closes the
old one.

What stays the same:

- **The agent.** A Claude Code window reopens in Claude Code, a Codex window in
  Codex, a Muse window in Muse.
- **The conversation.** It is resumed by its ID (`claude --resume <id>`,
  `codex resume <id>`, `muse resume <id>`), never forked into a copy.
- **The working directory**, read from the running agent.
- **The window name.** A name Rex generated itself, such as `Window 1a2b3c4d`,
  is not copied; Rex names the new window.

The destination is your choice. An existing session is reused, and a session
that does not exist is created.

Two agents resumed on one conversation ID both write to the same transcript,
and each misses the other's turns. The move therefore runs in a fixed order.
The new window starts a small waiting program. The old agent's turn ends, the
old window closes, the old agent exits, and only then does the new window
resume the conversation. If the old agent does not exit, nothing resumes.

The new window runs the agent inside your login shell
(`--shell=none -- "$SHELL" -ilc '"$@"; exec "$0" -il' "$SHELL" …`), the same
launch form `session-spinoff` uses, so quitting the agent leaves the tab open
at a normal shell prompt. When `$SHELL` is not zsh, bash, sh, dash, or ksh
(fish and tcsh reject that wrapper), the new window uses `/bin/zsh`.

When the agent moves its own window, the tab closes as soon as its final
message ends. The waiting program then tries to switch the Rex app to the new
tab; it does so only when exactly one Rex app is connected and that app's
Remote Control setting allows it. When it moves a
different window, it stays put, waits for the conversation to come up in the
destination, and reports the check: the same agent is running, and (for Claude
Code and Muse) the agent's own record shows the same conversation ID.

Every decision that can be checked is made by the bundled stdlib
`scripts/session-move` helper: what can move, the launch command, and the
result check.

**Triggers on:** "move this window to <session>", "move this tab to another
session", "session move", or any ask to relocate a running agent conversation
between Rex sessions. NOT starting a new agent on a side idea
(`session-spinoff`), not continuing in a new conversation or on another
computer (`session-handoff`), and not copying the conversation into a worktree
(`agent-fork`).

**Arguments:** `[destination-session] [--window <label|id> --session <label|id>]`

| Argument | Meaning |
|---|---|
| `destination-session` | The session to move to, by label or ID. Created when it does not exist. Asked when omitted. |
| `--window`, `--session` | Move a different window instead of the one the agent runs in. |

**Refused, with the reason:**

| Case | Why |
|---|---|
| The window runs on another computer | A Rex session can span computers; moving across them is out of scope. |
| The window has more than one pane | Only a single-pane window can be recreated faithfully. |
| The window is not running Claude Code, Codex, or Muse | There is no conversation to resume. |
| Another window's agent is mid-turn, or has a background shell running | The move would cut it off. |
| The conversation cannot be identified | For example, several live Codex conversations started in one directory; name one with `--conversation`. |

**Limits:**

- Flags given when the old agent started (a model, a permission mode) are not
  repeated on resume.
- Muse prints a warning on resume that its previous run ended without a clean
  shutdown. The conversation is intact.
- For Codex and Muse, the waiting program reads the turn-end record in the
  transcript. Only a transcript with no turn records falls back to six quiet
  seconds.
- Under Codex, the skill finds its own tab by the conversation ID, because the
  Rex IDs that Codex passes to commands belong to another tab.
- Codex and Muse ask for approval before each helper command, because the
  helper needs the Rex socket. In a Codex folder that is not trusted, the move
  cannot run.
- If the source window was its session's only window, that session is left
  empty and the skill says so.

**Requires:** Rex with the `rex` CLI, `uv`, the agent CLI being moved
(`claude`, `codex`, or `muse`), and the sibling `session-agent-list` skill,
whose inventory script identifies Codex and Muse conversations.

## Install

| Mode | When | How |
|---|---|---|
| Plugin (recommended) | You just want to use it | `/plugin install session@smorinlabs-skills` |
| Dev symlink | You want to tweak/iterate | `git clone https://github.com/smorinlabs/smorinlabs-skills` then `ln -s "$(pwd)/smorinlabs-skills/plugins/session/skills/session-move" ~/.claude/skills/session-move` |
| Direct copy | No marketplace access | copy `plugins/session/skills/session-move/` and `plugins/session/skills/session-agent-list/` into `~/.claude/skills/` |

**Codex:** install from a terminal:

```sh
codex plugin marketplace add smorinlabs/smorinlabs-skills
codex plugin add session@smorinlabs-skills
```

For development, link the cloned skill into `~/.agents/skills` (Codex's current
skills location). **Muse and OpenCode** both load skills from
`~/.agents/skills`, so the same dev symlink serves them.

## Example session

> A security review is running in a Claude Code tab named `security-review`
> inside the `storefront` session. "Move this window to audit."
> → The skill reads the window: one pane, Claude Code, on this computer, in
> `~/code/storefront/web`. No session is named `audit`, so it says it will create
> one. It opens a tab named `security-review` in the new `audit` session,
> where a waiting program starts in `~/code/storefront/web`, and confirms that
> program is running in the right place. Its last message says the tab is
> closing. When that message ends, the old tab closes, the conversation resumes
> in `audit` with its full history, and the Rex app is switched to it. Later,
> typing `/exit` there leaves a shell prompt in the tab.
