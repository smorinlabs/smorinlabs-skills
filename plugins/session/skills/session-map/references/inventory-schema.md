# Inventory and assessment interface

The map helper owns schema validation and publication. Use its commands to
change saved state instead of editing `inventory.json` directly.

## Snapshot

Schema version 1 contains these top-level fields:

| Field | Meaning |
|---|---|
| `schema_version` | Snapshot compatibility version; currently `1`. |
| `map_id` | Persistent identity of this local map. |
| `generation_id` | Current snapshot revision used for optimistic concurrency checks. |
| `config` | Persisted roots, sources, manager instances, and map configuration. |
| `sources` | Source attempts, success/coverage, capabilities, and errors. |
| `locations` | Terminal locations keyed by persistent ID. |
| `conversations` | Native agent conversations (Claude Code, Codex, Muse, OpenCode, Antigravity `agy`) keyed by persistent ID. |
| `projects` | Project/workstream records keyed by persistent ID. |
| `plans` | Source plans and their parsed phase/task records keyed by persistent ID. |
| `changes` | Added, changed, missing, and reassessment information for the update. |
| `metrics` | Collection/cache/assessment counts. |

Assessable records carry `id`, `fingerprint`, `observed_at`, `presence`,
`evidence_hash`, `assessment`, and `overrides`. Fields describing manager
targets, transcripts, repositories, and plans belong to their respective
record kinds. Refer to the saved records instead of inferring their shape
from an application's display label.

`fingerprint` and `evidence_hash` establish which observations support a
conclusion. They are opaque values supplied by the helper, not text the agent
should construct or alter. The map stores assessment dependencies so changed
evidence can invalidate conclusions that referred to another record.

## Assessment queue

`assessment-queue.json` contains `generation_id` and an `items` array. Each
item includes `id`, `kind`, `evidence_hash`, `reason`, and supporting evidence.
Use the queue's exact identifiers and hashes. The queue may include project
decisions affected by a changed conversation, not merely newly collected rows.

Write an assessment file in the map directory with this shape:

```json
{
  "generation_id": "example-generation",
  "assessments": [
    {
      "id": "example-session-id",
      "evidence_hash": "example-evidence-hash",
      "status": "Awaiting review",
      "summary": "Implementation is complete; the review is still open.",
      "next_action": "Review the implementation before merging.",
      "closure": "keep",
      "project_ids": ["example-project-id"],
      "phase_ids": ["P02"],
      "related_ids": [],
      "owner_ids": [],
      "evidence_ids": ["example-session-id", "example-project-id"],
      "rationale": "The session names the pending review as its next action."
    }
  ]
}
```

This is a synthetic shape example. Fill actual payloads from the current
queue and observations; do not submit the example identifiers.

| Assessment field | Contract |
|---|---|
| `id`, `evidence_hash` | Exact target and hash from the current queue. |
| `status` | Concise plain-language work status, independent of process liveness. |
| `summary`, `next_action` | What this work is and what remains actionable. |
| `closure` | `keep`, `candidate`, `review`, or `unknown`. |
| `project_ids` | Existing project IDs that the evidence links to this record. |
| `phase_ids` | Exact phase identifiers present in the record's linked projects' plans; arbitrary or unrelated phase IDs are rejected. |
| `related_ids` | Existing related record IDs. |
| `owner_ids` | Existing records responsible for the next action. |
| `selected_plan` | Optional known plan ID selected as authoritative for this assessment. |
| `evidence_ids` | Required nonempty list of known record IDs supporting the assessment. |
| `rationale` | Why the cited evidence supports the conclusion, including material uncertainty. |

Optional fields can be omitted when inapplicable. Never invent a project,
owner, or phase to fill an empty list. Use a pending or unknown assessment when
evidence cannot establish a conclusion.

Apply the file through `assess --map-dir PATH --file FILE`. `PATH` is the
resolved map directory and `FILE` is the assessment JSON you just wrote.
The helper checks its generation and known evidence identifiers. A refusal
means reread the current queue and reassess affected evidence; changing only
`generation_id` defeats the concurrency check.

## Explicit user corrections

Use `annotate --map-dir PATH --id ID --generation GENERATION --file FILE` for
an instruction supplied by the user. Take `ID` and `GENERATION` from the
current inventory. `FILE` contains a JSON object with one or more of:

| Key | User-controlled value |
|---|---|
| `title` | Preferred display name. |
| `project_ids` | Explicit project grouping. |
| `selected_plan` | Preferred known plan ID. |
| `owner_ids` | Explicit owner IDs. |
| `notes` | User notes to retain. |
| `container_id` | Exact known terminal-location ID that contains this location. The page adds its navigation only when both targets have verified commands and the container is observed. |

These overrides are separate from collected observations and automatic
assessments. Preserve them across full collection, update, and rendering.
If new evidence disagrees, display the conflict instead of replacing the
user's value or hiding the observed fact.

## Configuration and import

Use repeatable `--root PATH` to configure bounded local project discovery.
Use repeatable `--source native|rex|herdr|agent-deck` to select adapters.
Initial defaults are `native`, `rex`, and `agent-deck`; later updates retain
saved configuration unless options replace it. Select Herdr instances with
repeatable `--herdr-session NAME`. A focused or inherited Herdr instance is
not implicit authorization to inspect the wrong manager.

`import --map-dir PATH --file FILE` accepts the supported earlier prototype
inventory into a new map. It preserves exact native/manager identity and
available project/phase/task evidence. Imported judgments are stale, and old
commands stay disabled until revalidated. Import does not overwrite an
existing map or turn historical evidence into a fresh observation.

## Results and errors

Helpers print JSON summaries to stdout and diagnostics to stderr. Exit `0`
means success; exit `1` means partial source failure with usable output;
exit `2` means invalid usage or state. Inspect coverage before deciding an
exit `1` warrants retrying. Preserve a valid previous snapshot if collection,
assessment validation, or HTML rendering fails.
