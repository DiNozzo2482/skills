---
name: implement
description: Work the next ticket in a ticket file — read its state, pick the frontier ticket, implement it, verify each acceptance criterion, tick only what passed, and hand off to /to-logbook.
disable-model-invocation: true
---

# Implement

Take one ticket from `development/02_tickets/` from "next" to "done, verified, recorded".

**Argument:** the ticket file. A path, a SPEC number (`SPEC-06`), or nothing — with nothing, list the ticket files that still have an open frontier and ask which one. An optional second argument names a specific ticket (`/implement SPEC-06 3`), which overrides the frontier pick.

Resolve the **project root** as the nearest ancestor of cwd containing `CLAUDE.md`. Ticket, spec and logbook paths below are relative to that root. The helper lives with this skill, not in the project: `~/.claude/skills/implement/ticket_status.py`. It is stdlib-only, so plain `python3` runs it — do not reach for a project venv.

---

## 1. Read the state

```
python3 ~/.claude/skills/implement/ticket_status.py status <ticket-file>
```

This prints every ticket with its box count, state, blockers and open-box line numbers, then the frontier — the tickets whose blockers are all done. Add `--json` when you want the line numbers in a form you can compute with.

How the helper decides:

- **The heading marker wins.** ` — DONE 27.07.2026`, ` — OPEN`, ` — DEFERRED`, ` — OBSOLETE` at the end of a `##` heading. DONE, DEFERRED and OBSOLETE are all off the frontier.
- **Box state is the fallback** when there is no marker: all boxes ticked reads as done, none as not started, some as in progress.
- **A DONE ticket with open boxes is finished work with outstanding checks** — it stays off the frontier, and the helper flags it. That is a real and common state; do not "fix" it by ticking the boxes.

Read the flagged conflicts before going further. If a ticket is marked OPEN but every box is ticked, or has every box ticked and no marker, say so and ask what it should be — do not guess.

## 2. Understand the ticket

Read the whole ticket, and the parts of the file outside it: the intro paragraph carries the context a fresh session needs, and the frontier note explains the intended order. Read the source spec in `development/01_spec/` and the topic's Logbook in `development/03_logbook/` — the Logbook is where the previous ticket recorded what it actually built, which is usually more current than the ticket text.

Ticket text goes stale. `file:line` references were written on the date the ticket was written; re-confirm every one before editing. If the code has moved on, work from the ticket's intent, and say what you found.

## 3. Show the plan and stop

Present, in this order:

1. **Which ticket and why** — the frontier pick, with its blockers and their states.
2. **What you will build** — the behaviour, not a file-by-file diff.
3. **How you will verify each acceptance criterion** — one line per box, naming the actual check. Mark any box you cannot verify yourself here, with the reason. Do not discover this at the end.
4. **Anything in the ticket that no longer matches the code.**

Then wait. Do not start editing until the user says go.

## 4. Implement

Match the surrounding code — its naming, its error handling, its logging idiom. The ticket's blast radius is the ticket; if you find something else broken, note it for the Logbook's follow-ups rather than fixing it silently.

If the work turns out to need something the ticket did not anticipate, and it changes the shape of what you are building, stop and say so before continuing.

## 5. Verify, then tick

**Run each check. Show its output. Tick only what passed.**

A criterion is verified when a check you ran produced evidence for it. Reading the code you just wrote and concluding it must work is not verification. Neither is a test that you wrote but did not run.

```
python3 ~/.claude/skills/implement/ticket_status.py tick <ticket-file> --lines 31,32,34
```

Line numbers come from `status`. The helper refuses to touch a line that is not an open checkbox and validates every line before writing any of them, so a stale line number fails loudly instead of editing prose. Re-run `status` after any edit that shifts line numbers.

For every box left open, write a **Notes (DD.MM.YYYY):** block into the ticket saying what was not checked and what would close it. That block is how a future session knows the difference between "nobody got to it" and "this cannot be checked here". Never tick a box for the user, and never widen a criterion to make it pass — if a criterion turned out to be based on a wrong premise, tick it against the verified behaviour and record the deviation in the Notes.

Then the heading:

```
python3 ~/.claude/skills/implement/ticket_status.py mark <ticket-file> <ticket> --status DONE
```

Mark DONE when the ticket's work has landed. Open boxes do not block the marker — they are recorded in the Notes and reported to the user. If the work did not land, leave the heading alone and say why.

## 6. Report and hand off

Tell the user:

- what landed, and where
- every check you ran, and its result
- **every box left open, and why** — this is the part that matters, so lead with it if the list is long
- anything surfaced that is not this ticket's job
- the next frontier ticket, from a fresh `status` run

Then run `/to-logbook` to amend the topic's Logbook, following the ticket's own **When done** line. Clear context before the next ticket.

---

## Conventions

**Dates** inside ticket files are `DD.MM.YYYY`. The helper's `mark` writes today's date unless you pass `--date`.

**Status markers** are one of `DONE` / `OPEN` / `DEFERRED` / `OBSOLETE`, always last in the heading, keyword-anchored — plenty of titles contain an em-dash of their own (`## Ticket 1 — Scaffold: global venv, ...`), so never split a heading on the dash.

**Ticket bodies** are ordered: what to build → `**Blocked by:**` → acceptance checkboxes → `**Verify:**` → `**Notes:**` → `**When done:**`.

- `**Verify:**` holds the checks that gate the boxes. It may be checkboxes, prose, or a shell block — prose and shell are checks for a human to run, so surface them rather than assuming they passed.
- `**Notes:**` is the record of what happened: deviations, open boxes and why, things a later session needs.

**Blockers** are read from the `**Blocked by:**` line. Text in parentheses is ignored, because parentheses are where tickets say which tickets are *not* blockers ("benefits from T8", "OCR in Ticket 5 is not a blocker"). Write real blockers outside the parentheses.

**Sub-agents:** if you spawn one, never set `model:` — omit it so it inherits the session model.
