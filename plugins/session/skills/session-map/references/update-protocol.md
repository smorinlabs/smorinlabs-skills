# Full, update, and render

The saved inventory is the durable record. Cache files improve collection
speed; losing them must not erase user corrections or previous assessments.
The HTML embeds one saved generation and can be regenerated independently.

## Full inventory

Use `full` for first collection or an explicit request to revalidate all
configured sources. Preserve record identities and user annotations. Recollect
the configured scope rather than deleting saved history or starting a second
unrelated map in the same directory.

“Full” does not mean reading every historical transcript from beginning to
end. Index historical conversations, then assess visible/loaded sessions,
unresolved mappings, related handoffs, and owner/closure candidates. Mark
unreviewed historical records as unassessed.

## Incremental update

Use `update` when saved state exists. A current update still enumerates
available managers and native indexes, then refreshes process liveness.
Unchanged transcripts can contain sessions that have just stopped or started.

Compare evidence fingerprints before parsing content. Read changed files or
new transcript records; reuse unchanged parser output. Reassess the changed
record and decisions that depend on it, including project ownership and
another session's closure recommendation. Use the helper's queue rather than
reconstructing that dependency set manually.

An explicitly scoped update limits deep reads to the selected project or
session and affected dependencies. Other records retain their original detail
and assessment timestamps. Explain those limits in the result.

The native collector's `--since` flag is a result filter. It is not a substitute
for the helper's persistent cache. A cache error may require rereading its
source; it does not authorize dropping old inventory records.

## Rendering saved state

`render` reads the saved map and template and writes HTML. It does not inspect
terminal managers, native stores, project files, Git state, or remote services.
Do not run those probes yourself when the user asked only for rendering.

The page's render time can be new while observations and assessments are old.
Preserve all three timestamps. Pending assessment and source errors remain
visible in the regenerated page.

## Partial failure and recovery

Distinguish an empty successful source from one that failed or was unavailable.
After successful enumeration, a previously present record may become
`not_observed`; that is not a claim that its work is done. Failed collection
keeps previous records with stale coverage.

The helper serializes writers and validates snapshot generations. If another
update changed the generation while you were preparing assessments, reread
the current queue. Do not retry an old assessment payload against a new
generation by changing only its identifier.

JSON publication and HTML publication are separate. If collection succeeds
but rendering fails, the previous page can show an older generation. Report
the mismatch and run `render` to repair the page from saved state. Avoid
recollecting the entire inventory solely to repair HTML.

Treat schema-version errors as recovery work. Preserve the original files;
never overwrite a newer unsupported map with a fresh empty inventory.

## Earlier prototype maps

Use the helper's `import` operation for a supported earlier inventory. Keep
the original file as evidence, retain its observation times, and mark imported
assessments stale until refreshed. Exact manager/native identifiers carry
identity; array positions and display ordinals do not.

After import, inspect reported unmatched records, then run an update and
review the assessment queue. Import success alone does not establish current
navigation targets or current project ownership.
