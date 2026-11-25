# session-inventory — CLI interface spec

| | |
|---|---|
| **Binary** | `session-inventory` (lowercase, kebab-case — R1.4) |
| **Location** | `plugins/session/skills/session-agent-list/scripts/session-inventory` |
| **Profile** | Small-CLI, verb-first (Appendix A — criteria hold: 1 fixed command, single implicit resource "agent session", unlikely to grow; migration trigger: a second resource type ⇒ noun-verb in the next major) |
| **Tier** | minimal, plus the scripted-consumer rules (R4.2, R7.2, R7.8) |
| **Standard** | CLI Design Standard v1.4.14 |
| **Shape** | Single-file uv-shebang Python script (argparse), stdlib only |

Purpose: one read-only inventory of the agent sessions on this machine across
Claude Code, Codex, Muse, OpenCode, and Antigravity (`agy`) — identity, session
name, spawn directory, times, lineage, whether the session is running right now,
and the resume command a reader may safely run. The `session-agent-list` skill
renders cards from this output; judgment work (titles from turns, handoff
evidence, end-state classification) stays with the skill.

## Command tree

| Command | Purpose | Exit on "nothing" |
|---|---|---|
| `list` | Enumerate sessions from every selected tool, newest activity first | `0` — an empty set is success (R6.2) |

Bare `session-inventory` prints help to stdout and exits `0` (R7.9). `list` is
a core verb (R2.1).

## Flags

Global:

| Long | Short | Type | Default | Notes |
|---|---|---|---|---|
| `--help` | `-h` | flag | — | stdout, exit 0 (R4.1) |
| `--version` | `-V` | flag | — | stdout, exit 0 (R4.1) |
| `--output` | `-o` | enum `text\|json` | `text` | machine output (R4.2) |
| `--json` | — | flag | — | ≡ `-o json` (R4.2) |

`list`:

| Long | Type | Default | Notes |
|---|---|---|---|
| `--tool` | enum `claude\|codex\|muse\|opencode\|agy`, repeatable | all five | restrict to these tools (R3.7) |
| `--live` | flag | off | only sessions that may be running: `live` is `yes`, or `unknown` (rendered `live?`) |
| `--since` | `<n>m\|h\|d\|w` or ISO date | none | only sessions updated at or after this point |
| `--include-subagents` | flag | off | also list subagent and guardian threads (hidden by default, always counted in the census) |
| `--cache-dir` | path | none | reuse parsed JSONL metadata in this local directory; native stores remain read-only |
| `--refresh-cache` | flag | off | bypass saved metadata and rebuild the cache; requires `--cache-dir` |

`--` terminator honored; no command reads stdin, so `-` has no file role
(R3.1/R3.2 N/A). No credential flags exist (R5.5).

## Sources

Paths honor `HOME`; Codex honors `CODEX_HOME`; Muse and OpenCode honor
`XDG_DATA_HOME` (default `~/.local/share`). A tool whose store is absent is
reported as `absent`, not as an error. SQLite stores are opened read-only
(`mode=ro` URI) and never written.

### Optional incremental metadata cache

`list --cache-dir <directory>` stores disposable parsed metadata in
`metadata-v1.json` under the selected directory. Without this option, the
collector creates no cache and keeps its existing output shape. The cache
contains metadata such as names and working directories, so it belongs in the
user's private map/cache directory rather than a public repository.

Unchanged Claude, Codex, and Antigravity JSONL files need only a file-stat
check. The fingerprint includes device, inode, size, nanosecond modification
time, and nanosecond change time. Changed Claude transcripts reread their
bounded head and title/name tail; changed Codex transcripts reread the first
metadata line; changed Antigravity transcripts reread the bounded first line for
`created_at`. Hashes let unchanged regions reuse their parsed values. Other
appended message content is not parsed because this collector supplies session
metadata, not conversation assessments. Truncation and replacement trigger
current metadata reads instead of retaining the former file's fields.

The Codex names index uses a complete-line byte cursor. Before reusing a cursor,
the collector verifies the entire committed prefix against its saved hash.
An append then parses only new index records. Prefix rewrites, truncation, and
replacement rebuild the index. A final record without a newline can contribute
a provisional name, but its cursor does not advance; the next append retries
that line, including a previously incomplete JSON record.

Every invocation still enumerates stores, queries SQLite indexes, and checks
process liveness. Process IDs, registry state, locks, and resume decisions are
never cached. Cache corruption, parser-version changes, and cache-write failure
fall back to source reads or uncached results; the `cache.warnings` field records
the degraded cache. Cache files are replaced atomically and use private file
permissions. A concurrent source write invalidates that file's cache entry so
the next update reads it again.

`--refresh-cache` is suitable for a full inventory. `--since` still filters
results after collection and does not itself enable caching.

| Tool | Sessions | Name | Title | Liveness signal |
|---|---|---|---|---|
| `claude` | `~/.claude/projects/*/<uuid>.jsonl` (top level only; sidecar dirs skipped) | last `custom-title` record (`/rename`) | last `ai-title` record | `~/.claude/sessions/<pid>.json` registry: PID alive **and** its UTC start time equals `procStart` |
| `codex` | `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-*.jsonl` | `thread_name` in `$CODEX_HOME/session_index.jsonl` | — | `$CODEX_HOME/thread-writer-locks/<uuid>.lock` held open by a process (one `lsof` call) |
| `muse` | `session-index.db` table `sessions` | canonical claim in `session-names.db` (see below), else `session_name` | `title` | `<session_dir>/.session.lock`: same host, PID alive, process is `muse` or its versioned `muse-bin-*` binary |
| `opencode` | `opencode.db` table `session_v2` (newer OpenCode releases), plus `session` rows missing from it (`legacy_only`); else `session` | `slug` | `title` | a running `opencode` process: `--session <id>` in its argv, else its working directory (see `opencode_directory_liveness`) |
| `agy` | `~/.gemini/antigravity-cli/conversation_summaries.db` table `conversation_summaries` + line 1 of `brain/<id>/.system_generated/logs/transcript.jsonl` (`created_at`) | — | `title` (fallback `preview`) | a running interactive `agy` process (excluding non-TUI subcommands): `--conversation`/`--resume`/`-r <id>` in its argv (`live: yes`), else its working directory newest-only (`live: unknown`) |

Hidden by default (counted as `hidden_subagents`): Codex threads whose
`thread_source` is `subagent` or `guardian_review`; OpenCode sessions with a
`parent_id`; Antigravity rows with `nesting_depth > 0`. Codex `forked_from_id`,
Muse `msp_fork_source_session_id`, OpenCode v2 `fork_session_id`, and
Antigravity rows with `nesting_depth == 0` and a `parent_conversation_id` mark
user forks — listed, with lineage.

Antigravity (`agy`) scans strictly `~/.gemini/antigravity-cli` (Antigravity
CLI). Separate Antigravity App (`~/.gemini/antigravity`) and IDE
(`~/.gemini/antigravity-ide`) stores are not merged because `agy --conversation`
cannot resume them. Resume uses `cd '<spawn_dir>' && agy --conversation <id>`
(blocked if `live == "yes"` or `spawn_dir` is absent).

## Exit codes (R6.1)

| Code | Meaning here |
|---|---|
| `0` | Success, including an empty result. Individual transcripts that fail to parse are listed with `unreadable: true` and counted; they do not fail the run. |
| `1` | Partial failure (R6.3): a store exists but could not be read (locked, corrupt, or an unexpected schema). The other tools' sessions are still printed; the failed source is named. |
| `2` | Usage error (unknown flag, bad `--since`, unknown `--tool`) |
| `130` | SIGINT |

## Output contract

Text (default): one line per session, stable tab-separated field order —
`tool  id  name  live  updated  spawn_dir  title`. After the sessions, one
`# census` line per selected tool (listed, hidden subagents, unreadable, live,
source status) — census is data, so it stays on stdout (R7.1). Absent fields
print `-`.

`--json` (R7.2 open-by-default, additive-only): one object

```json
{
  "sessions": [
    {
      "tool": "muse",
      "id": "01a0ca24-4bbc-7ec1-bd58-21281a1af2bf",
      "name": "copper-umbra",
      "name_resumable": true,
      "title": "can you look at the CI bottleneck issue",
      "spawn_dir": "/home/alex/c",
      "branch": null,
      "created": "2026-09-22T19:10:04Z",
      "updated": "2026-09-22T21:31:27Z",
      "transcript": "/home/alex/.local/share/muse/sessions/2026/09/22/01a0ca24-…/session.jsonl",
      "lineage": null,
      "archived": false,
      "unreadable": false,
      "live": "yes",
      "live_basis": "lock pid 23981 alive (muse)",
      "live_host": "cli",
      "pid": 23981,
      "tmux": null,
      "resume": null,
      "resume_by_name": null,
      "resume_blocked": "running",
      "export_command": "muse export --session 01a0ca24-4bbc-7ec1-bd58-21281a1af2bf"
    }
  ],
  "census": {"muse": {"listed": 146, "hidden_subagents": 0, "unreadable": 0, "live": 6}},
  "sources": {"muse": {"status": "ok", "path": "/home/alex/.local/share/muse/session-index.db"}}
}
```

- `live` is `yes`, `no`, or `unknown`; `live_basis` states the evidence.
  `live_host` is `cli` (a terminal session) or `app-server` (a Codex thread
  loaded in an IDE, desktop-app, or companion-plugin host), `null` when not live.
- `transcript` is the session file; OpenCode has none (`null`) and instead
  carries `export_command`. Muse also carries `export_command`.
- Muse names come from `~/Library/Application Support/Muse/session-name-authority/session-names.db`
  (`kind = 'canonical'` claims), falling back to the index's `session_name`
  column, which is only a projection and can be empty.
- The census `live` count covers listed sessions only (hidden subagents excluded).
- `lineage` is `null` or `{"kind": "fork"|"subagent", "parent_id": "…"}`.
- `resume` is `null` whenever `resume_blocked` is set: `running` (resuming a
  running session puts two writers on one transcript), `no_workspace` (the
  tool recorded no directory to resume from), or `legacy_only` (an OpenCode
  session only in the old `session` table: OpenCode stops importing that table
  into `session_v2` once its migration is marked done, so neither `resume` nor
  `export_command` is offered). `sources.opencode.legacy_only` counts them.
- Sort: `updated` descending, then `tool`, then `id` (deterministic).
- Times are UTC ISO 8601 with a `Z` suffix; paths are absolute.

With `--cache-dir`, JSON also includes a `cache` object. Text output adds one
`# cache` line containing that object. Counters describe this invocation:

| Field | Meaning |
|---|---|
| `hits` / `misses` | Metadata files reused from an identical fingerprint / inspected after a new or changed fingerprint. |
| `parsed_files` | Metadata files requiring at least one JSON parse attempt. A changed Codex transcript with unchanged metadata can have a miss but no parse. |
| `parsed_records` | JSON parse attempts, including incomplete or invalid records. |
| `sections_reused` | Bounded metadata regions whose bytes matched their saved hash. |
| `bytes_read` | Source bytes read by the cached metadata readers, including name-index prefix verification; excludes process probes and SQLite queries. |
| `index_appends` | Grown Codex name-index files that reused a verified complete-line cursor. |
| `raced_files` | Files changed during a read and therefore not saved in the cache. |
| `status` / `warnings` | `ok` or `degraded`, plus cache recovery/write diagnostics. Source failures remain in `sources` and retain exit code `1`. |
| `parser_version` | Metadata cache compatibility version. |

Errors under `--json` are a single object on stderr (R7.8):
`{"error": {"code": "source_unreadable", "message": "…", "sources": ["muse"]}}`.
Code: `source_unreadable`. Usage errors (exit `2`) are argparse's plain-text
usage message on stderr, not a JSON object.
