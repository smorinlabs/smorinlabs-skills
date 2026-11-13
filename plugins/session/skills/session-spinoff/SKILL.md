---
name: session-spinoff
allowed-tools: Bash, Read, Skill, AskUserQuestion
argument-hint: "[idea] [--new | --session <label|id>] [--name <session-name>] [--repo <name|path>] [--claude | --codex | --muse] [--dry-run]"
arguments: [idea]
description: Spin an idea that came up mid-session (a bug, feature, or fix, often in another repo) off into a fresh Claude Code, Codex, or Muse agent in a Rex tab, on a new worktree, with a self-contained brief as its first prompt, so the current session keeps its focus and context. Use when the user says "spin this off", "launch this in Rex", "start a new session for this in <repo>", or wants a side idea worked on separately. Not for continuing the current work elsewhere (session-handoff), forking this conversation (agent-fork), or general Rex tab and session control (rex).
---

# session-spinoff

Take a side idea out of the current session and start it somewhere clean: its
own worktree, its own Rex tab, its own agent, with a brief that carries
everything the new agent needs. The current session ("session A") continues
unchanged.

> **THE NEW AGENT KNOWS ONLY THE BRIEF.** It has no scrollback, starts from
> `origin/<default-branch>`, and cannot see session A's uncommitted work. A
> brief that says "the bug we just saw" launches an agent that cannot act.

## Contract

- **Every flag answers one question in advance.** Without flags, ask. With
  flags, skip exactly the matching question. When flags answer everything,
  launch without asking.
- **Placement is always the user's choice** unless `--new`, `--session`, or
  `--name` decided it: present Rex sessions ranked by fit plus "New session".
- **Nothing is created before the questions are answered.** The order is
  questions → worktree → launch. `--dry-run` stops before the worktree and
  prints the commands.
- **Session A is never modified.** No commits, no stashes, no edits to its
  checkout. The only writes are the new worktree and the new Rex tab or session.
- **Rex Remote Control is the user's setting.** If a jump command is refused,
  print it and say why; never change the setting.

## Resolve the helper

`scripts/spinoff-plan` lives beside this file. Resolve it through the real path
so it works from a symlinked placement:

```bash
PLAN="$(dirname "$(realpath "<skill-dir>/SKILL.md")")/scripts/spinoff-plan"
```

Run it as `uv run --script "$PLAN" <verb> ...` (stdlib only, Python ≥ 3.11).

## Workflow

### 1. Gate the arguments

```bash
uv run --script "$PLAN" args -- <each argument as its own word>
```

Shell-split the invocation's argument string first, so `--new --codex` arrives
as two words, never one. Once idea text has started, an unknown `--word` is
part of the idea ("add a `--version` flag"); a bare `--` makes everything after
it idea text, even a known flag name. Exit 2 means a refused combination (`--new` with `--session`, `--name` with
`--session`, two agent flags, an unknown flag, a value flag with no value).
Show the message and stop — do not guess what was meant. The JSON gives
`idea`, `placement` (`ask` | `new` | `session`), `session`, `name`, `repo`,
`agent`, `dry_run`.

### 2. Pin the idea

Use `idea` if given; otherwise take the most recent side idea from the
conversation and show it back in one line. Several candidates, or none →
ask which. Derive:

- **type**: `fix` (bug), `feat` (new capability), or `chore` (upkeep);
- **topic**: a short slug, for example `repo-finder-worktrees`.

### 3. Find the target repo

`--repo` given → resolve it to a local checkout and confirm it exists.
Otherwise infer the repo from the idea and resolve it with the `repo-finder`
skill. If inference is weak, ask; never pick between two candidates silently.
Record the checkout path (absolute) and the remote's current default branch:
`git -C <repo> ls-remote --symref origin HEAD` prints
`ref: refs/heads/<branch>	HEAD`. Ask the remote, because the local
`origin/HEAD` is not updated when the default branch is renamed. Only if the
remote is unreachable, fall back to
`git -C <repo> symbolic-ref --short refs/remotes/origin/HEAD` and say so; it
prints `origin/main`, and the helper strips the `origin/` prefix.

### 4. Write the brief

Invoke the `session-handoff` skill in `--inline` mode with the goal **fixed to
the spun-off idea** — not session A's work. Its content contract applies, with
these adjustments:

- **Outcome**: the idea and what "done" means; session A's work is out of scope.
- **Portability preflight**: state that the agent starts from
  `origin/<default-branch>` and that session A's uncommitted changes are absent.
  If the idea depends on them, say so and say what to do.
- **Critical context**: the evidence that surfaced the idea — error text, file
  and line, command output — quoted, not paraphrased.
- **First action**: one concrete step in the target repo.

Keep it as short as it can be while still standing alone. It becomes the
agent's first prompt, not a file.

### 5. Take the snapshot

```bash
uv run --script "$PLAN" snapshot --repo <checkout>
```

Read-only, about 3 seconds. A tab's start directory is often a parent such as
the code root, and the agent then works in repos below it, so the helper also
reads the recent transcript of the agent running in each tab (found by its
process ID through the sibling `session-inventory`) and counts paths per repo,
with worktrees counted toward their repo. Returns `sessions`, each with
`tier`, `repo_tabs`, `repo_hits` (transcript path hits in the target repo),
`label_names_repo`, `agents`, `dirs` (the distinct working directories of its
tabs), and `facts`, plus `transcript_evidence` (`ok`, or why it was skipped), `current_agent`, `app_clients`, and `labels_in_use`. The order
is by facts only: tier 1 (a tab started in the target repo or one of its
worktrees, or its agent touched the repo at least 3 times recently; started
tabs first, then more hits), then tier 2 in Rex's order. "Label names this
repo" is a fact for step 5a, never a tier. If `transcript_evidence` is not
`ok`, say so in the placement question: tiers then rest on start directories
alone.

### 5a. Order within tiers

The helper does not judge what a label means. Do that here, under three rules:

- **Never move a session across tiers.** Every tier-1 session stays above every
  tier-2 session.
- **Within a tier, order by how closely the session label relates to the idea
  or the target repo.** `T8-muse-lost-sessions` relates to a Muse bug;
  `hailwire-design` relates to a Hailwire idea even in another repo. Opaque
  labels (`dex`, `drifting-summit`) keep their helper order at the end of
  their tier.
- **Within tier 2, a session whose label names the repo comes first.**
- **Reasons come only from `facts`, `dirs`, or the label.** Write "agent
  touched this repo 34× recently" or "label names this repo". Never infer history ("you worked on this
  yesterday") that the snapshot does not show.

### 5b. Choose the launch directory

The agent starts where the Rex tab opens. Default: the worktree root. Propose
something else only when the idea calls for it:

- **A subdirectory of the worktree** when the idea lives in one package of a
  monorepo (the evidence names files under `packages/api/`, say) and that
  package has its own build or agent instructions (`AGENTS.md`, `CLAUDE.md`,
  its own manifest).
- **A parent of the worktree** (for example the code root holding several
  repos) when the idea spans more than one repo. The worktree is still created
  only in the target repo; say in the brief which other repos it may read.

The helper accepts only the worktree, a directory inside it, or a parent of it.

### 6. Ask what is still open — one question

Combine the open items into a single AskUserQuestion:

- **Placement** (if `placement` is `ask`): the top 3 sessions from step 5a,
  each with its reason and its `dirs` (home shortened to `~`, at most three,
  then "+N more"), then "New session". The dialog holds at most four
  options; the built-in Other takes any other session by label. The first
  session is marked Recommended only when it is tier 1 or its label clearly
  relates; otherwise "New session" is the recommendation.
- **Agent** (if `agent` is null): `claude`, `codex`, `muse`, with
  `current_agent` listed first and marked Recommended. Outside Rex
  `current_agent` is null; recommend `claude` then.
- **Launch directory** (always): the step-5b proposal first and marked
  Recommended, with why; the worktree root as the alternative when they
  differ. When the proposal is the worktree root, offer it with the nearest
  sensible alternative (a parent or a package directory), so the choice is
  visible.

Then, if placement is new and `--name` was not given, propose a session name
(`<type>-<topic>`, at most 40 characters) and ask the user to confirm or edit
it. A name already in `labels_in_use` is never used silently: ask again.
`--session <label|id>` resolves against the snapshot: exactly one match → use
its `session_id`; several → ask which; none → show the top sessions and ask.
Always pass the resolved `session_id` on, never the label.

### 7. Build the commands

Write the brief to a temporary file with a quoted heredoc, so quotes, braces,
and newlines in quoted evidence pass through untouched. **The delimiter must
not occur as a line in the brief**: a line equal to it ends the heredoc, and
every line after it runs as a shell command. Use a fresh delimiter each run,
`SPINOFF_BRIEF_` plus 8 random hex characters, and check that the finished
brief contains no line equal to it. Then pipe the plan, which now holds only
simple values, to the helper:

```bash
BRIEF="$(mktemp -t spinoff-brief)"
cat > "$BRIEF" <<'SPINOFF_BRIEF_<8 random hex>'
<brief text>
SPINOFF_BRIEF_<8 random hex>
uv run --script "$PLAN" commands --brief-file "$BRIEF" <<'JSON'
{"repo": "<absolute checkout>", "default_branch": "<branch>",
 "branch": "<type>/<topic>", "worktree": "<path>",
 "placement": "new|session", "name": "<session name>", "session": "<session_id>",
 "tab_label": "<topic>", "agent": "<agent>",
 "launch_dir": "<chosen dir; relative means relative to the worktree>",
 "client": "<the single app client id, or null>"}
JSON
```

Exit 2 names the missing or invalid field (including a `launch_dir` outside
the allowed range); fix it and re-run. The output's `launch_dir` is the
absolute directory the tab will open in. A relative
`worktree` is resolved against the repo, so `git` and Rex agree on the path.

Worktree path: follow the repo's existing convention from
`git -C <repo> worktree list`; otherwise `../<repo>-<topic>` beside the
checkout. If the branch or path already exists, ask before reusing anything.
The brief file is only the helper's input: the brief reaches the agent as its
first-prompt argument. Remove the file after launch.

**`--dry-run`**: print the brief and the `shell` strings, then stop.

### 8. Create and launch

1. Run `worktree`, then `worktree_add`. A failure stops here; nothing in Rex
   was touched.
2. Run `launch`. Adding a tab to an existing session does not move the
   user's focus (`--focus=false`); the jump in step 9 does that. Save `session_id` (new session) and `window_id` / `block_ids`
   from its JSON. If it times out, inspect with `rex ls` / `rex window ls`
   before retrying; the tab may already exist.
3. Check that the agent started in the right directory:

   ```bash
   uv run --script "$PLAN" verify-launch --session <session_id> \
     --block <block_ids[0]> --expect-dir <launch_dir> --agent <agent>
   ```

   Exit 0: the agent is running and its working directory is `launch_dir`.
   Exit 3: the JSON says which check failed (`cwd_ok`, `agent_ok`). An agent
   still starting shows the shell; wait a few seconds and run it once more. A
   wrong directory after that is a failure: report it with both paths and
   leave the tab for the user to inspect. Never relaunch on top of it.

### 9. Report and offer the jump

Print a receipt:

```
Spun off: <idea, one line>
  Rex:      <session label> › <tab label>   (<new session | existing session>)
  Agent:    <agent>
  Worktree: <path>  on  <branch>  (from origin/<default-branch>)
  Runs in:  <launch_dir>   (verified)
  Jump:     rex -C <client> do session.select session_id=<id> window_id=<id>
```

Then offer to run the jump command. With exactly one app client, use it. With
several, ask which device. If the app refuses (Remote Control is off), say so
and leave the printed command for the user.

Return to session A's work.

## Red Flags

| Thought | Reality |
|---|---|
| "The brief can reference what we discussed" | The new agent has none of it. Quote the evidence. |
| "I'll put it in the obvious session" | Placement is asked unless a flag answered it. |
| "This label sounds closer, move it above the repo match" | Tiers are facts. Reorder only within a tier. |
| "Branch from local main, it's right here" | Local `main` may be stale. Always `origin/<default-branch>`. |
| "Commit session A's changes so the new agent sees them" | Session A is never modified. State the dependency in the brief instead. |
| "The tab opened, so it's in the right place" | Run `verify-launch`. A tab can open in the wrong directory and the agent works on the wrong tree. |
| "A fixed heredoc delimiter is fine, it's quoted" | Quoting stops expansion, not collisions. A brief line equal to the delimiter turns the rest of the brief into shell commands. Random delimiter, checked. |
| "The launch timed out, run it again" | It may have succeeded. Inspect first, or you get two tabs and two agents. |
| "Turn on Remote Control so the jump works" | That is the user's setting. Print the command. |

## See also

- `session-handoff` — writes the brief (step 4); on its own it continues the
  current work rather than spinning off a new idea.
- `repo-finder` — resolves the target repo (step 3).
- `rex` — the full Rex CLI guide (`rex skill show`).
- `agent-fork` — copies *this* conversation and its dirty files into a
  worktree of the same repo; the opposite trade-off.
