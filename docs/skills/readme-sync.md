# readme-sync

Audits `README.md` for drift against the actual codebase — install
instructions vs the manifest, CLI commands and flags vs the implementation,
code examples vs the public API, documented project structure vs what's on
disk, internal links, and task-runner recipes — then reports each
inconsistency with what the README says next to what's actually true, and
applies fixes when asked.

**Triggers on:** "update README", "sync README", "check README", "is README
up to date", "are docs consistent", "does README match the code" ·
**Arguments:** `--check` (report only, default), `--fix` (apply fixes),
`--since <commit>` (scope to changes since a specific commit)

## Install

| Mode | When | How |
|---|---|---|
| Plugin (recommended) | Just use it | `/plugin install repo-hygiene@smorinlabs-skills` |
| Dev symlink | Tweak/iterate | `git clone https://github.com/smorinlabs/smorinlabs-skills` then `ln -s "$(pwd)/smorinlabs-skills/plugins/repo-hygiene/skills/readme-sync" ~/.claude/skills/readme-sync` |
| Direct copy | No marketplace access | copy `plugins/repo-hygiene/skills/readme-sync/` into `~/.claude/skills/` |

**Codex:** install from a terminal:

```sh
codex plugin marketplace add smorinlabs/smorinlabs-skills
codex plugin add repo-hygiene@smorinlabs-skills
```

For development, link the cloned skill into `~/.agents/skills` (Codex's current
skills location).

## Example session

> "Does the README match the code?"
> → reads `README.md` plus the recent git log, checks each category
> (install instructions, CLI usage, code examples, project structure,
> links, task-runner recipes), and reports inconsistencies with the quoted
> README text next to what's actually true — applying the fixes directly
> if `--fix` was requested.
