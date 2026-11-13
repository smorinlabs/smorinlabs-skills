# Session close-out — is this session done, and should it close?

The last thing the reader sees. It answers one question: **can I close this
session window now?** It is additive. It renders after everything the skill
already prints, and it never replaces or rewrites that output.

## Scope: this session only

Judge only what **this session** set out to do and what it left behind. Work
owned by other sessions, other worktrees, or other people is out of scope, even
when it touches the same repo. A handoff this session wrote **is** in scope, and
it counts as evidence for closing: the work it carries now lives in that
document, not in this window.

## Step 1 — split the main work from the small items

- **Main work** — the session's goal: what the user asked for, or the items in
  its plan of record (a `PROJECTS.md` project, a plan file, a todo list).
- **Small items** — everything else still open: cleanup (a worktree, a branch,
  a background job), a status flip, an issue to file, a suggestion nobody
  answered, a doc touch-up.

When it is unclear whether an item is main work, ask whether the session's goal
is met without it. If yes, it is a small item.

## Step 2 — three buckets

Render three short lists, main work first in each, small items after:

| Bucket | Holds |
|---|---|
| ✅ **Done** | Finished and verified (merged, committed, written, or carried by a handoff document this session wrote) |
| ❓ **Needs a decision** | Open forks only the user can settle, each with a recommendation |
| ⬜ **Not done** | Remaining work, each tagged **main** or **small** |

Reuse the IDs the skill already issued (`D1`, `C2`, `W1`, …). Never restate an
item in full that the report above already explains; name it by ID and a few
words. An empty bucket renders as one line (`❓ Needs a decision — none`), never
silently disappears. Exception: when the skill's own output is at its smallest
size (for example, `session-recap`'s tiny tier) and the verdict is ✅, the whole
close-out may collapse to one line: `🚪 ✅ Close this session — <evidence>`.

Items that belong to another session (its worktree, its branch, its open PR)
are out of scope: leave them out of all three buckets.

## Step 3 — the verdict

| Verdict | When |
|---|---|
| ✅ **Close this session** | All main work is done, and every small item is done, dropped, or already captured somewhere durable |
| 🟡 **Main work done — close out N small items?** | All main work is done, and some small items have no home yet |
| 🔵 **Continue** | Some main work is not done, or a main-work decision is still open |

**Lean toward closing.** Small items never force 🔵. They turn ✅ into 🟡. A
session whose main work is done should end at ✅ or 🟡.

Every verdict carries **evidence** — the concrete facts it rests on, e.g.
`merged #102 · handoff docs/handoffs/2026-11-13-x.md written · 2 follow-ups
captured in PROJECTS.md P67`.

### 🟡 — offer to close out the small items

List each small item once, with one recommended disposition:

- **Do now** — small and safe in this session (remove a merged worktree, flip a
  checkbox).
- **Drop** — not worth doing; say why in a few words.
- **Capture** — keep it, but outside this session: a `PROJECTS.md` entry, a
  commit, a GitHub issue, or a Linear issue (via `a2l`).

Then make the offer. Once each item is done, dropped, or captured, the verdict
becomes ✅. The offer's form depends on whether the skill can act:

- **Acting skill** (`session-loose-ends`) asks: **"Main work is done. Want me
  to close out these N items?"** It then carries out the dispositions item by
  item. The user's yes to a specific item is the user's call, so it also
  covers ❓ and 💡 items the sweep otherwise marks report-only — for example,
  capturing an `S#` idea with `/project-add` after the user says yes to it.
- **Read-only skill** (`session-recap`) never executes. Its offer is a launch:
  `▶ Prompt — paste this to close out N items: /session-loose-ends "S1 — …"`.

A prompt handed to the user (a paste-ready `▶ Prompt`) is not a durable
capture. An item whose only home is such a prompt still counts as open, so the
verdict stays 🟡.

### Shape

Rendered last, after everything else the skill prints (in `session-recap`,
after the reader-steps block, still inside the `🏁 Close` zone). Its label is
bold text, not a heading, so it never reads as a new top-level section.
Example from the acting skill:

```
**🚪 Close-out — this session only**
✅ Done        main: P67 shipped (merged #104) · small: C1 worktree removed
❓ Decisions   none
⬜ Not done    small: S1 retry-backoff idea (unrecorded)

🟡 Main work done — close out 1 small item?
   Evidence: merged #104 · tree clean · handoff not needed
   S1 → Capture as a PROJECTS.md idea (`/project-add`)
   Want me to close out this 1 item?
```

## When the skill already printed a verdict

Some skills keep their own verdict line (for example, `session-recap`'s
`🏁 Close`). That line stays exactly as written. When the two answers differ,
add one line naming why, e.g. `🏁 says Continue only because of C1 (cleanup);
main work is done → 🟡`. Never edit the earlier verdict to match.
