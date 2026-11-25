# session-map

Build a saved, interactive map of projects and agent sessions. Browse related
work, project phases, complete/open task counts, current owner candidates,
remaining actions, and evidence-backed closure recommendations. Each located
session includes its manager, agent, working directory, and copyable command
for selecting its existing tab.

The map is a self-contained `index.html` backed by a local `inventory.json`.
Future sessions can update the saved inventory instead of repeating the whole
assessment. Rendering the saved inventory can rebuild the page without
inspecting any source session or project.

**Triggers on:** “map my sessions”, “build a project and session dashboard”,
“update the session map”, and “regenerate the map from its inventory”. For an
immediate text listing, use [session-agent-list](session-agent-list.md). For
returning to one conversation, use [session-recap](session-recap.md).

**Arguments:** `[full|update|render] [--map-dir <path>]
[--project <id>|--session <id>] [--root <path>] [--herdr-session <name>]
[--source <name>] [--no-open]`

| Mode | Result |
|---|---|
| No mode | Create the first map; update it on later invocations. |
| `full` | Recollect configured sources while preserving identities and user corrections. |
| `update` | Refresh discovery/liveness and changed evidence, then reassess affected work. |
| `render` | Rebuild HTML from saved state without recollecting evidence. |

`--map-dir` chooses the saved map. Project/session scopes use persistent IDs
shown in that map. Repeat `--root` for bounded project search directories.
Select Herdr instances explicitly with `--herdr-session`. `--source` selects
native sessions, Rex, Herdr, or Agent Deck; omitted source options preserve an
existing map's configuration. `--no-open` leaves the generated file on disk
without opening a browser.

The default map lives under `$XDG_STATE_HOME/session-map/maps/default`, or
`~/.local/state/session-map/maps/default` when `XDG_STATE_HOME` is unset.
Private inventories remain separate from the installed public skill.

## What updates preserve

Persistent IDs keep project relationships and user corrections attached to the
same records when tabs are renamed or reordered. Updates retain your titles,
groupings, selected plans, owner pins, and notes. New contradictory observations
remain visible for review.

The collector caches parsed metadata but checks liveness separately. An
unchanged transcript can belong to an agent that has stopped since the last
map. A failed source stays visibly stale; its sessions are not silently
declared closed. Unchanged assessments keep their original timestamps.

The agent reviews affected records using an assessment queue. A project plan
change can invalidate the ownership or progress assessment of several sessions.
Pending or unresolved assessments stay visible instead of being presented as
completed research.

Task counts describe checklist items, not elapsed time or estimated effort.
Shared phase counts are not added across sessions. Missing decomposition means
remaining work is unknown. Current owners and closure candidates include their
supporting evidence; the skill does not execute cleanup.

## Sources and requirements

Python 3.11 or newer on macOS or Linux runs the bundled helper using the standard library.
Native Claude Code, Codex, Muse, OpenCode, and Antigravity (`agy`) discovery
comes from the sibling `session-agent-list` collector. Manager-specific
collection requires the corresponding installed CLI. Missing sources appear as
coverage gaps.

Manager, agent, and host remain separate: a Claude Code session inside Herdr
inside Rex is not three independent conversations. Loaded child threads
without terminal locations remain identifiable without invented navigation
commands. Unknown agent names are retained as reported.

The page is an offline snapshot with no server or external asset dependency.
Its update control copies an invocation for an agent session; it cannot run
arbitrary local commands from the browser. Navigation commands select targets
that existed when checked and can become stale until the next update.

## Install

| Mode | When | How |
|---|---|---|
| Plugin (recommended) | Use the complete session bundle | `/plugin install session@smorinlabs-skills` |
| Dev symlink | Iterate on an existing clone | From the parent of the `smorinlabs-skills` clone, link both `session-map` and `session-agent-list` as shown below. |
| Direct copy | No marketplace access | Copy both skill directories from `plugins/session/skills/` into the tool's skills directory. |

For a new Claude Code marketplace registration:

```text
/plugin marketplace add smorinlabs/smorinlabs-skills
/plugin install session@smorinlabs-skills
```

Codex marketplace installation from a terminal:

```sh
codex plugin marketplace add smorinlabs/smorinlabs-skills
codex plugin add session@smorinlabs-skills
```

Antigravity (`agy`) plugin installation:

```sh
agy plugin install https://github.com/smorinlabs/smorinlabs-skills/tree/main/plugins/session
```

For development, start in the parent directory of your existing
`smorinlabs-skills` clone. If the repository is not downloaded, clone it first
with `git clone https://github.com/smorinlabs/smorinlabs-skills`.
The following creates Claude Code placements; omit any placement that already
resolves to the intended skill source:

```sh
mkdir -p "$HOME/.claude/skills"
ln -s "$(pwd)/smorinlabs-skills/plugins/session/skills/session-map" "$HOME/.claude/skills/session-map"
ln -s "$(pwd)/smorinlabs-skills/plugins/session/skills/session-agent-list" "$HOME/.claude/skills/session-agent-list"
```

For Codex, Muse, OpenCode, or Antigravity, use `~/.agents/skills` instead of
`~/.claude/skills` for both placements. Direct-copy installations likewise need
both skill directories or an available `session-inventory` executable on PATH.
The skill resolves its helper and sibling references through the installed
source directory, so invocation does not depend on the current repository.

## Example session

> “Build a map of my sessions and projects.”
> → The skill collects available sources, reads plans, assesses the queued
> sessions and project relationships, then opens the local HTML map. Sources
> that could not be read remain visible in its coverage view.
>
> “Update the map for this project.”
> → The skill reuses the saved map, refreshes that project's changed evidence
> and affected ownership decisions, and preserves unrelated assessments with
> their previous timestamps.
>
> “Regenerate the HTML from the saved inventory.”
> → The skill runs `render`; it does not inspect terminals, transcripts, or
> project files again.

An earlier supported prototype inventory can be imported into a new map using
the helper. Its assessments remain historical until an update revalidates
them. Importing or exporting local data does not publish it.
