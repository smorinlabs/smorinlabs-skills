# session-map: a saved project and session inventory

Status: accepted design, implemented for session 0.19.0. GitHub delivery is tracked by the feature PR; no marketplace release tag is implied.

Create `session-map` in the public `session` plugin. It builds an interactive,
single-file HTML map from a saved inventory, then keeps that inventory current
without repeating unchanged discovery and assessment work.

The user should be able to answer: Where is this project? Which conversations
belong to it? Which session owns the next action? What is complete, open, or
blocked? Which sessions are candidates to close? How do I select the right tab?

## 1. Placement and boundaries

The proposed skill lives at `plugins/session/skills/session-map/`, relative to
the repository root. It uses the existing native-session collector owned by
[session-agent-list](../../plugins/session/skills/session-agent-list/SKILL.md).
It adds persistent state, terminal locations, project plans, evidence-backed
assessments, incremental updates, and an HTML interface.

The overlap scan covered the installed skill registry and both fleet source
repositories. No skill named `session-map` was found. The recommended verdict
is **create new and clarify the adjacent listing skill's trigger**.

| Neighbor | Boundary for this design |
|---|---|
| `session-agent-list` | Owns native discovery and immediate session cards. Add a description exclusion for persistent HTML project/session maps. Reuse its collector rather than copying native-store parsers. |
| `session-recap` | Orients inside one conversation. The map relates many conversations and projects. |
| `session-status` | Reports the active conversation's progress without probes. The map collects cross-session evidence. |
| `session-loose-ends` | Owns approved cleanup. The map recommends candidates and never closes them. |
| `session-handoff`, `session-spinoff`, `session-move` | Own transfer, launch, and relocation. The map records those relationships and provides navigation. |
| `project-next`, `project-audit`, `project-refine`, `project-add` | Own project selection and tracking changes. The map reads project records without editing them. |
| `rex`, `herdr`, `agent-deck` | Own manager-specific operations. Use supported read interfaces and verified identifiers. |
| `html-explain`, `html-codesign`, `show-me`, `system-atlas` | Produce explanations, decision pages, or architecture views. The map owns a persistent operational inventory and its refresh protocol. |
| `agent-fork`, `session-share`, `shelf`, `wayfinder` | Own copying, sharing, document storage, or planning future decisions. None supplies this inventory. |

The public package contains instructions, reusable code, templates, and synthetic
fixtures. Actual inventories, transcripts, usernames, machine addresses, and
project details stay in the user's local map directory.

## 2. User interface to the skill

These are **proposed skill invocations**, not currently installed commands.
Claude Code uses `/session-map`; Codex can invoke `$session-map` or the skill by
name in a request. The same arguments apply.

| Invocation | Behavior |
|---|---|
| `/session-map` | Create a full inventory if none exists; otherwise update it. Render and open the resulting map. |
| `/session-map full` | Re-enumerate all configured sources and revalidate cached evidence. Preserve stable identities, user annotations, and prior snapshots. |
| `/session-map update` | Refresh discovery and liveness, collect changed evidence, reassess affected records, and rebuild the HTML. |
| `/session-map update --project <id>` | Refresh that project's sessions, plans, and dependent ownership decisions. Other details keep their previous timestamps. |
| `/session-map update --session <id>` | Refresh that session and the project relationships affected by its changes. |
| `/session-map render` | Rebuild HTML solely from the saved inventory. No manager, process, transcript, Git, or network inspection. |

`<id>` comes from the map's copyable project or session identifier. These are
persistent identifiers, not a table row number. Project and session scope flags
are mutually exclusive in the initial version.

Common options: `--map-dir <path>` selects the saved map; `--no-open` suppresses
opening the browser. A default local map is discoverable across sessions under
`$XDG_STATE_HOME/session-map/maps/default`, falling back to
`~/.local/state/session-map/maps/default`. The agent resolves and displays the
actual path. Multiple maps remain separate unless the user requests a merge.

`update` requires existing state. If explicitly requested without saved state,
report that no baseline exists and offer a full inventory. The argument-free
invocation handles first creation automatically. Invalid or newer unsupported
schemas produce a clear error, never a silent replacement of saved work.

Suggested frontmatter argument hint:
`[full|update|render] [--map-dir <path>] [--project <id>|--session <id>] [--no-open]`.
Suggested tool grants are `Read`, `Glob`, `Grep`, `Bash`, `Write`, and `Edit`.
The body restricts writes to the map output and cache; source repositories,
agent stores, and terminal sessions remain read-only.

## 3. Saved state and stable identity

`inventory.json` is the authoritative, versioned snapshot. `index.html` is a
derived, self-contained view. Neither depends on the creating conversation's
memory or on a hand-written Python curation file.

| Local artifact | Purpose |
|---|---|
| `inventory.json` | Map configuration, observations, relationships, assessments, user overrides, source coverage, and generation identifier. |
| `index.html` | Embedded inventory and interface, usable offline without a server. |
| `changes.json` | Added, changed, no-longer-observed, stale, and reassessed records for the latest update. |
| `cache/` | Recoverable parser results, source fingerprints, and read cursors. Losing it costs performance, not annotations. |
| `evidence/` | Bounded local evidence excerpts and hashes, referenced by assessments. Full transcript copying is not the default. |
| `snapshots/` | Previous published inventories, retained under a documented size/count policy. Explicit pruning preserves the current and previous good snapshots. |

The minimum schema separates these concepts:

| Entity | Identity and essential fields |
|---|---|
| Map | `schema_version`, `map_id`, `generation_id`, creation/update/render times, collection scope, configured roots. |
| Source | Manager/store type, persisted machine and source-instance IDs, capabilities, adapter version, last attempt, last success, coverage, error. |
| Terminal location | Exact manager workspace/tab/pane identifiers, instance generation, observed process, working directory, containing terminal relationship. |
| Conversation | Agent tool and full native ID, source instance, parent/fork lineage, transcript or export reference, independent liveness evidence. |
| Repository/worktree | Persistent local identity, remote identity when available, common Git directory, location, branch, commit, dirty state, observation time. |
| Project/workstream | Persistent map ID, title, related repositories, plan candidates, selected plan with reason, current owner candidates. |
| Phase/task | Owning project and plan version, exact phase/task identifier, title, state, source path, line, content hash. |
| Assessment | Status, summary, next action, owner/closure recommendation, rationale, supporting evidence hashes, assessment time, freshness. |
| User override | Explicit grouping, title, selected plan, owner pin, or note; author/source, time, value, and conflicts with new observations. |
| Navigation | Structured target IDs, executable/capability used, generated command, last validation time, current availability. |

Conversations and terminal locations are separate records linked by evidence.
One conversation can appear in multiple surfaces; one pane can host successive
conversations. A loaded child thread need not have a terminal location.

Native identity includes machine, store instance, tool, and the full native ID.
Manager identity includes the source instance and exact manager IDs. Short IDs
that may be reused after restart also need a manager generation or an observed
incarnation. When reuse cannot be distinguished, create an unresolved new
location and flag the conflict instead of inheriting the old row's assessment.

Assign persistent project IDs once. `P01` is scoped to a project and plan, never
a global identifier. Labels, sort order, title, working directory, and display
ordinals are not identity. Repository paths and remote URLs are supporting
identity evidence; a move, changed remote, or second clone must not silently
merge or split projects. Explicit user grouping is retained.

## 4. Collection and incremental update protocol

An update is still a current inventory. It performs inexpensive discovery so
new sessions are found and stopped sessions are noticed. It avoids repeating
unchanged content parsing and semantic assessment.

1. Load and validate the saved map. Acquire one writer lock for that map.
2. Enumerate configured manager topology, native session indexes, and current
   process evidence. Record each source's start/end time and success separately.
3. Compare source identities and fingerprints against the saved snapshot.
   New records enter the assessment queue. Missing records are retained with
   `not_observed` only after a successful enumeration covering that record.
4. Read new or changed session evidence. Reuse parsed unchanged content.
   Refresh liveness independently, even when a transcript has not changed.
5. Discover project roots from observed working directories, known worktrees,
   explicit plan references, and configured search roots. Recheck those roots
   and linked plan files. Do not walk the entire home directory by default.
6. Reparse changed plans and refresh scoped Git observations. Invalidate the
   assessments that depend on changed evidence or changed membership.
7. The agent reviews the affected records and writes structured assessments.
   Unchanged assessments keep their original assessment times. Unresolved or
   conflicting records remain explicitly unassessed or stale.
8. Revalidate exact navigation targets against successfully observed topology.
   Compute the changes report, validate the snapshot, and publish it atomically.
9. Render HTML, validate it, and replace the previous HTML only on success.
   Open it and report the update counts, coverage gaps, and remaining uncertainty.

The scripts collect facts and enforce the update rules. The invoking agent
interprets ownership, related work, handoffs, and closure evidence. A script
must not declare work complete because a process exited or a transcript ended.
Direct script use may collect and render with pending assessments visible;
it must not pretend to have performed the agent's judgment step.

### Change detection by source

| Source | Update behavior |
|---|---|
| Manager topology | Re-enumerate workspace/tab/pane identifiers on each update. Inspect process identity and bounded output for scoped live panes; compare normalized output hashes. If no reliable output revision exists, a bounded recapture is required. |
| JSONL native stores | Cache parsed stable fields by file identity, size, high-resolution modification/change times, and parser version. Parse appended complete records from the saved byte cursor. Handle incomplete trailing lines without advancing past them. Truncation, replacement, or uncertain continuity triggers a rescan of that file. |
| SQLite native stores | Use read-only database access and tool-supported row timestamps/identifiers where available. Database/WAL mtimes alone cannot establish which sessions changed. Re-enumerate indexed rows to detect deletions; re-extract details only for changed records. |
| Liveness | Recheck process existence and identity independently of cached transcript content. Preserve `yes`, `no`, and `unknown` with their evidence. |
| Project plans | Compare content hashes of known plans and their linked files. Re-enumerate configured roots/worktree listings to find new plans. Invalidate only affected plan counts and their dependents. |
| Git state | Refresh selected worktree status, branch, commit, and worktree topology using read-only commands. A stable `HEAD` does not prove a clean or unchanged working tree. Local tracking refs remain labelled as local observations. |
| Optional remote PR/CI state | Record exact remote source and check time. Refresh when that evidence supports a changed ownership/completion decision; otherwise retain its last-check time. Offline or failed checks cannot imply a merge or release. |

Full mode revalidates all sources within the recorded map scope and bypasses
reusable parser results. It preserves annotations and record identity. It does
not require copying every historical transcript in full. Default deep review
covers visible/loaded sessions, unresolved mappings, related handoffs, and
previous owner/closure candidates. Historical indexed conversations without
deep review remain searchable and explicitly labelled as unassessed.

### Reuse and extend the native collector

The existing [session-inventory interface](../../plugins/session/docs/session-inventory-cli.md)
provides native IDs, lineage, liveness, coverage, and safe resume information.
Its current `cmd_list` calls `collect` before applying `--since`; that flag
reduces displayed rows, not collection work.

Add optional `--cache-dir <path>` and `--refresh-cache` support to that collector,
with unchanged behavior for callers that omit them. `--refresh-cache` requires
a cache directory. Cache parsed session metadata, not process liveness.
`session-map update` uses the cache; `full` forces cache revalidation. Keep the
existing partial-success output contract. Do not fork its store parsers inside
`session-map`, and do not claim `--since` alone supplies incremental collection.

Changes to an adapter, parser, schema, or assessment policy invalidate the
affected cache or assessments. Each cache entry records these versions. A cache
failure falls back to reading the affected source and never discards saved
annotations.

### Dependency-aware reassessment

Store the evidence dependencies of each assessment. A changed session may
change its project's owner recommendation and another session's closure
recommendation. A changed plan affects every session linked to that plan.
Reassess those dependents even if their own transcripts did not change.

A scoped update always refreshes discovery and liveness, but limits deep reads
to the selected scope and necessary dependencies. Mark untouched details with
their original timestamps. Never advertise the entire map as freshly assessed
because one project was refreshed.

Example: two sessions discuss a project's P02 phase. One advances to P03 and
names the other as a completed review. Update both relationship assessments,
the selected project's current owner, and its plan counts. Preserve unrelated
projects' assessments without rereading their transcripts.

## 5. Project interpretation and progress

Resolve project membership from explicit task/plan references, repository and
worktree identity, native metadata, process arguments, and conversation content.
Shared working directory or similar titles are insufficient on their own.
Conflicting native IDs remain visible; observed process resume arguments can
disprove stale manager metadata. Record the matching evidence and confidence.

Keep terminal manager, agent tool, and host application as different fields.
For example, Claude Code may run inside Herdr, which is itself inside Rex.
Count each category separately. Preserve an unknown tool's reported name;
do not silently rename an application to a familiar agent.

Read `PROJECTS.md`, linked project files, explicit `PLAN.md` files, and referenced
handoff documents. Retain plan variants across worktrees. Select a plan from
explicit authority or current-work evidence and show the reason; file mtime
alone does not establish authority. Contradictory variants remain inspectable.

Show implementation tasks and test tasks separately. Count exact numbered
identifiers once within their owning phase and plan. Exclude fenced examples;
show duplicate/conflicting task states instead of arbitrarily taking the last.
Open, in progress, complete, retired, redirected, and unknown are distinct.
Recognize repository-specific status conventions instead of imposing one.

Progress means checklist progress, not a percentage of effort or time. Report
the complete/open counts, denominator, source, and unnumbered acceptance gates.
Missing decomposition means **remaining work unknown**. Shared phase counts
must not be summed across the sessions that reference them. A completed phase
heading with open test items is a visible conflict.

The “cutting edge” view names the session currently responsible for the next
action and explains why. Evidence may include an accepted handoff, current
phase, implementation branch, review status, and last meaningful work. Show
multiple owners or “owner unresolved” when appropriate. Recent output alone
does not prove ownership.

Closure recommendations use separate states: keep, candidate to close, needs
review, and unknown. Each candidate includes the completed/superseded work,
remaining obligations, successor where established, and evidence freshness.
Disappearance, age, a manager's `done` label, or an idle prompt is not enough.
The skill never closes, kills, sends commands to, resumes, or relocates agents.

## 6. HTML application

Preserve the useful views from the prototype: overview, projects, sessions,
closure review, conversation history, and sources/coverage. Add **Changes since
last update** and a visible **Update this map** action that copies a skill
invocation with the resolved map directory.

Each project exposes its locations, phases, task counts, remaining work,
current owner candidates, supporting sessions, plan conflicts, and source
links. Each session exposes its manager/agent, location, workstream, status,
next action, assessment time, evidence, and available navigation command.
Project and session views have stable hash routes so they can be reopened.

Navigation actions select existing verified targets. Prefer structured target
IDs rendered through adapter-specific command builders. Resolve executables
on the local machine, quote every argument, and never execute a transcript's
suggested command. A native thread without a verified tab gets its transcript
or supported host reference, not a fabricated jump command. Do not offer a
resume operation for a running or unresolved-live conversation.

Commands display their working-directory requirement and validation time.
Label skill prompts separately from terminal commands. For nested managers,
show both the inner selection and outer container navigation. No browser
button executes arbitrary local shell commands: the page copies commands or
prompts for the appropriate terminal or agent session. Snapshot commands can
become stale; `update` revalidates them.

The page embeds data, CSS, and JavaScript with no network assets or backend.
Escape embedded JSON and render evidence as text. No raw transcript HTML.
Support keyboard navigation, visible focus, narrow screens, accessible status
labels, and a selectable-text copy fallback. Show source-specific freshness
and distinguish “last observed”, “last assessed”, and “HTML rendered”.

Exporting the inventory produces a local data file. Publishing or sharing
private map contents is outside the skill's default behavior. Redaction does
not imply that a map is safe to publish.

## 7. Failure, concurrency, and publication

- A manager timeout or native-store error preserves prior observations with
  stale/unavailable status. It never converts its records into closed sessions.
- An empty successful source is different from an unavailable source. Missing
  tools and unconfigured sources are explicit coverage states.
- Collection has a time interval, not a fictional simultaneous observation.
  Recheck changed or uncertain navigation identities before publication.
- Use a per-map writer lock and snapshot generation checks. Concurrent updates
  cannot overwrite each other's assessments or user overrides. Interrupted
  writes leave the last validated inventory readable.
- Write and validate temporary files in the output filesystem, then replace
  `inventory.json` atomically. Retain the previous valid snapshot. Render to a
  temporary HTML file and replace `index.html` only after validation succeeds.
- JSON and HTML replacement are separate operations. Both carry the same
  generation ID. If rendering fails or the process stops between replacements,
  keep the old HTML and report the mismatch. A subsequent `render` repairs it
  from the saved inventory without recollection. Never claim pairwise atomicity.
- User overrides persist independently of automatic conclusions within the
  schema. Contradictory new observations produce a conflict for review rather
  than overwriting the user's value or concealing the observed fact.
- Source text is evidence, never instructions to the collector or assessor.
  Ignore commands, permissions, and workflow directives embedded in captures.

## 8. Package and delivery plan

Proposed new files, relative to the repository root:

```text
plugins/session/skills/session-map/
  SKILL.md
  scripts/session-map
  scripts/session_map/             # collectors, reconciliation, schema, renderer
  references/inventory-schema.md
  references/update-protocol.md
  references/assessment-rules.md
  references/adapter-contract.md
  templates/index.html
docs/skills/session-map.md
tests/test_session_map.py
tests/fixtures/session_map/        # synthetic evidence only
```

Python 3.11+ standard library is the proposed runtime, matching the existing
native collector; repository development uses its configured Python version.
HTML uses browser-native JavaScript. The runtime needs no model API key: the
agent running the skill supplies the assessment step. Native discovery resolves
the sibling collector relative to the installed skill's real path, then a
verified PATH/placement fallback. If the dependency is unavailable, report the
capability gap and preserve partial manager data.

Initial sources: native Claude Code, Codex, Muse, and OpenCode through the
existing collector; Rex and explicitly selected Herdr instances; Agent Deck
registry plus corroborating process/tmux evidence when available; local project
plans and Git worktrees. Record unsupported managers without inventing support.
Remote-machine collection is deferred; retain machine identity now so it can
be added without record collisions. Remote PR checks are an optional source.

Suggested implementation sequence:

1. Confirm the new-skill conflict verdict; settle the description boundary with
   `session-agent-list`. The requested public home and `session-map` name are
   already established.
2. Define versioned state, stable IDs, evidence dependencies, override behavior,
   and snapshot publication using synthetic fixtures.
3. Add cached parsing to `session-inventory` with compatibility tests. Implement
   manager and project adapters with explicit capability/error reporting.
4. Implement full/update collection and reconciliation. Expose a structured
   assessment queue and validate the agent's returned assessments before merging.
5. Implement saved-state rendering and HTML interactions. Include copied update
   prompts and per-view stable links. Exercise a second update, not only creation.
6. Write the skill and documentation, update the listing skill's exclusion,
   record project tasks, bump the affected plugin version, and regenerate
   manifests with the repository's generator.
7. Run quality checks against the worktree. Complete the repository's required
   checks and a live private full → update → render smoke test. Report browser
   verification separately from DOM tests.
8. Complete the normal release/install workflow. Verify installed placements
   resolve to the retained source checkout, not a disposable worktree.

The existing private prototype is a behavioral reference, not a package to
copy wholesale. Its index-based curation and machine-specific paths cannot be
the public implementation. Importing that snapshot is a separate, explicit
migration: translate exact source IDs, preserve its evidence timestamps and
annotations, and flag unmapped rows. Never import by matching array ordinals.

## 9. Acceptance checks

| Check | Required result |
|---|---|
| First inventory | Every configured source has coverage; all discovered records are included or explicitly excluded by recorded scope. |
| No-change update | Zero unchanged transcript bodies or plan bodies reparsed; zero unchanged semantic assessments repeated. Discovery and liveness still run. Report cache hits, parsed records, and reassessment counts. |
| One changed transcript | Only its changed content and dependent assessments are processed; unrelated records retain their assessment timestamps. |
| New/missing tab | New location appears; disappearance after successful enumeration is retained as not observed, without implying completed work. |
| Source failure | Prior records survive with stale/error coverage; usable partial results remain available. |
| Reused manager ID | New incarnation cannot inherit the former conversation's identity or closure recommendation. |
| Liveness-only change | A stopped or newly loaded process is detected even when transcript bytes are unchanged. |
| Nested managers | Outer Rex container and inner Herdr tabs remain related without inflating the distinct conversation count. |
| Plan conflict | Worktree variants and inconsistent task states remain visible; P01 in two repositories never collides. |
| User correction | Manual grouping, owner/plan pins, and notes survive full, update, and render. New contradictory evidence is shown. |
| Scoped update | Selected scope and dependent decisions refresh; other assessment timestamps remain unchanged. |
| Append/truncate/rotate | JSONL cursors handle partial lines, file replacement, and truncation without losing or double-counting records. |
| Render-only | Fixture asserts zero discovery/process/network calls and reproduces the same semantic data and routes. |
| Recovery | Interrupting collection, assessment, JSON replacement, or HTML generation leaves a recoverable last good snapshot. |
| Command correctness | Fixtures cover spaces/metacharacters, missing executables, stale targets, unresolved native IDs, and exact nested navigation. No destructive action is emitted. |
| HTML behavior | Search, filters, project/session links, counts, changes, copy fallback, export, keyboard access, and narrow-screen layout work. Evidence cannot inject script. |
| Public package | Secret/personal-data scan passes; shipped examples and test evidence are synthetic. Existing collector consumers still pass. |

Implementation notes: evidence excerpts are embedded in the saved inventory
rather than duplicated in a separate evidence directory. Previous snapshots
are retained without automatic pruning. Remote checks are supplied by the
invoking agent when needed; the collector makes no remote API requests.
Agent Deck records provide registry evidence and exact native corroboration,
not an assumed live tmux tab. Runtime support is macOS/Linux.

The implemented workflow and current command interface are documented in
[the skill guide](../skills/session-map.md).
