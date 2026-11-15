<!-- muse-github-setup:audit-triage:start -->
## Muse audit triage

The audit-triage workflow uses the official Claude Code Action with Meta Muse.
It diagnoses a recorded failed weekly audit and proposes documentation repairs.
The model may inspect files and use read-only tools; it may edit ordinary files
under `docs/` only. Shell execution, credentials, agent instructions, CI changes,
model-controlled publication, approvals, and merges are excluded.

Treat failure logs and repository content as untrusted input. The trusted helper
validates the action result and every change before publishing a separate repair
PR. A human reviews and merges repairs. Preserve the existing activation switch,
model tier, credential scope, and trigger restrictions during updates.
<!-- muse-github-setup:audit-triage:end -->
