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

Reuse the IDs the skill already issued (`D1`, `C2`, `W1`, …). In the buckets,
never restate an item in full that the report above already explains; name it
by ID and a few words. The 🟡 offer below is different: there, every small item
gets its full block, because that is where the reader decides. An empty bucket renders as one line (`❓ Needs a decision — none`), never
silently disappears. Exception: when the skill's own output is at its smallest
size (for example, `session-recap`'s tiny tier) and the verdict is ✅, the whole
close-out may collapse to one line: `🚪 ✅ Close this session — <evidence>`.

Items that belong to another session (its worktree, its branch, its open PR)
are out of scope: leave them out of all three buckets.

## Step 3 — the verdict

| Verdict | When |
|---|---|
| ✅ **Close this session** | All main work is done, and every small item is done, ignored, spun off, or already captured somewhere durable |
| 🟡 **Main work done** · *Close out N small items, then this session can close* | All main work is done, and some small items have no home yet |
| 🔵 **Continue** | Some main work is not done, or a main-work decision is still open |

**Lean toward closing.** Small items never force 🔵. They turn ✅ into 🟡. A
session whose main work is done should end at ✅ or 🟡.

Every verdict carries **evidence about the main work** — the concrete facts it
rests on, e.g.
`merged #102 · handoff docs/handoffs/2026-11-13-x.md written · 2 follow-ups
captured in PROJECTS.md P67`.

### 🟡 — offer to close out the small items

The 🟡 verdict is two lines: `🟡 Main work done`, then, indented beneath it,
`Close out N small items, then this session can close`. A blank line, then
the evidence line. Then another blank line, and each small item as its own
indented block, with a blank line between blocks. The examples here are fenced
only so their structure is legible: real output is not fenced, and keeps the
indents and the `What` / `Why` / `▶` label column as shown.

```
  S1  <action title — what closing this item means, in plain words>
      What  <the exact artifact by name (file, path, branch, commit, PR)>; <its current state, including whether anything tracks it>
      Why   <the consequence if it is left>
      ▶     <Recommended answer> — <one-clause reason>      Else: <other sensible answers>
```

- **Self-contained.** A reader who saw nothing above the block can still answer
  it. `What` always names the exact thing, even when a table above already
  listed it, and always states its current state: "mentioned only in this
  conversation; nothing tracks it" is a state.
- **`What` and `Why` are one line each.** Add nothing else; the block stays four
  lines.
- **`▶`** gives one recommended answer and its reason, then lists only the
  other answers that make sense for this item. **Ignore**, when listed, always
  carries its risk in a few words.

Every item is answered with one of four words:

| Answer | Meaning | Counts as closed when |
|---|---|---|
| **Do here** | This session does it now (remove a merged worktree, flip a checkbox) | It is done and verified |
| **Spin off** | A new dedicated session does it, launched with `/session-spinoff` | The new session is launched with its brief |
| **Capture** | Keep it for later, outside this session: a `PROJECTS.md` entry, a commit, a GitHub issue, or a Linear issue (via `a2l`) | The record exists |
| **Ignore** | Not worth doing; the block says what risk that accepts | The user says ignore |

The reply names each item and its answer, e.g. `C1 do here, S1 capture`. Words,
not per-item letters, so one reply can never mean different things for
different items. Once every item is closed, the verdict becomes ✅.

The block ends with the reply line, and then the offer, whose form depends on
whether the skill can act:

- **Acting skill** (`session-loose-ends`) asks: **"Reply per item, e.g. `C1 do
  here, S1 capture`."** It then carries out each answer: **Do here** it executes
  and verifies, **Spin off** it launches through `/session-spinoff`, **Capture**
  it records. The user's answer to a specific item is the user's call, so it
  also covers ❓ and 💡 items the sweep otherwise marks report-only — for
  example, capturing an `S#` idea with `/project-add` after the user says
  capture.
- **Read-only skill** (`session-recap`) never executes. Its offer is a launch
  with the recommended answers filled in, for the user to edit:
  `▶ Prompt — paste this to close out N items: /session-loose-ends "C1 do here, S1 capture"`.

A prompt handed to the user (a paste-ready `▶ Prompt`, or a spin-off that was
offered but not launched) is not a durable capture. An item whose only home is
such a prompt still counts as open, so the verdict stays 🟡.

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

🟡 Main work done
   Close out 1 small item, then this session can close

   Evidence (main work): merged #104 · tree clean · handoff not needed

     S1  Record the retry-backoff idea
         What  exponential backoff for `fetch_runs()` retries, floated in this session; nothing tracks it
         Why   the flaky-CI retries it would fix keep failing, and the idea is lost when this window closes
         ▶     Capture — a PROJECTS.md idea via `/project-add`      Else: Spin off · Ignore (risk: the idea is lost)

   Reply per item, e.g. "S1 capture".
```

## When the skill already printed a verdict

Some skills keep their own verdict line (for example, `session-recap`'s
`🏁 Close`). That line stays exactly as written. When the two answers differ,
add one line naming why, e.g. `🏁 says Continue only because of C1 (cleanup);
main work is done → 🟡`. Never edit the earlier verdict to match.

## Compact form (context-only skills)

A skill that reads no live state (`session-status`) renders the verdict, one
evidence line about the main work followed by its source, and, for 🟡, the
small-item blocks exactly as above. It never prints the buckets, because its
own ledger already shows done and left. Its ledger tracks only planned work,
so a small item usually appears nowhere else, which is why the block must
stand on its own.

It never acts and never offers to act: it prints the answers and ends. A reply
such as `S1 capture` is a new instruction, carried out by the session or by
`/session-loose-ends`, not by the context-only skill.

```
🟡 Main work done
   Close out 2 small items, then this session can close

   Evidence (main work): design merged (PR #3) · P01 merged (PR #4), tagged `v0.1.0` · P02 handed to its own agent
   Source: from plan + conversation; not checked against git/PR/CI — /session-recap confirms

     C1  Remove the P01 worktree
         What  `../proj-p01` on branch `feat/p01`, left behind after PR #4 merged; clean
         Why   nothing uses it, and it blocks deleting `feat/p01`
         ▶     Do here — one command, safe (merged, clean)      Else: Ignore (risk: clutter only)

     S1  Get a second review of the deletion-design fixes
         What  `design.md` §9, fixed in commit `95c9592`; reviewed once; mentioned only in this conversation, nothing tracks it
         Why   P05 builds on §9, so an error in the fixes would carry into P05's code
         ▶     Capture — a gating task on P05 in PROJECTS.md      Else: Spin off · Do here · Ignore (risk: a §9 flaw reaches P05)

   Reply per item, e.g. "C1 do here, S1 capture".
```
