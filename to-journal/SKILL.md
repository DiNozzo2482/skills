---
name: to-journal
description: Write a dated journal entry for this session to journal/YYMMDD_journal.md (durable memory), then copy your LAST response before the /to-journal call to the clipboard via pbcopy so it can be pasted into the next session for seamless continuation. Use when the user types /to-journal or asks to "log this session to the journal" / "save a journal entry".
---

# /to-journal — session journal logger + last-response clipboard

You type `/to-journal`. No arguments. I do two things:

1. **Durable memory:** write a dated journal entry for this session to
   `journal/YYMMDD_journal.md` in the **main project root** (the git
   repository top-level — never a subproject root, see Paths).
2. **Continuation aid:** copy **your last response before this
   `/to-journal` call** to the clipboard via `pbcopy`, so you can paste
   it into the next session (after `/clear`) and continue seamlessly.

Then I tell you to run `/clear`.

This is a pure file-I/O task — no external app, no driver script. Steps
use only Bash (date/session-id/transcript-parse/clipboard) and
Read/Write/Edit (the journal file).

This skill supersedes the old `/to-diary` skill (renamed 24 Jul 2026):
the old name collided with a different project that stored its log in a
`Diary/` folder, so a `/to-diary` run there had no `diaries/` folder and
contaminated another project's diary. The new name + explicit
`journal/`-folder lookup makes the target unambiguous per project.

## Why the clipboard gets the *last response*, not the journal entry

You clear context between tasks to stay out of the context-window "dumb
zone" and to save tokens. To continue a task in the next session you
paste in my last response from the previous one. So the clipboard must
hold **my last response before the `/to-journal` call** — the journal
entry is a separate, structured record on disk, not what you paste.

## Paths

The project root is **resolved**, never assumed to be the current
working directory. cwd is often a subfolder (e.g.
`development/03_logbook/` during a logbook session); writing `journal/`
relative to cwd would spawn a stray `journal/` there.

The journal always lives at the **main project root** — the git
repository top-level — even when the session works inside a subproject
that has its own `CLAUDE.md` (subproject roots exist so `/to-spec`,
`/to-tickets` and `/to-logbook` write development documents to the right
place; the journal is deliberately exempt — one journal per repository,
so a day's record never splits across folders). Resolve it with git,
falling back to the nearest `CLAUDE.md` ancestor of cwd when outside a
git repository:

```bash
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$ROOT" ]; then
  ROOT="$PWD"
  while [ "$ROOT" != "/" ] && [ ! -f "$ROOT/CLAUDE.md" ]; do
    ROOT="$(dirname "$ROOT")"
  done
  [ -f "$ROOT/CLAUDE.md" ] || { echo 'to-journal: no git repo and no CLAUDE.md above cwd — cannot resolve project root' >&2; exit 1; }
fi
```

Note: `git rev-parse` must run in the session's *launch* directory, not
wherever the shell's persistent cwd has drifted — a `cd` into a nested
git repo during the session would otherwise re-root the journal there.
If in doubt, resolve `$ROOT` from the session's original working
directory (the environment block's "Primary working directory").

All paths below are absolute under `$ROOT`:

- Journal folder: `$ROOT/journal/`
- Today's file: `$ROOT/journal/YYMMDD_journal.md` (YYMMDD = today, no week
  suffix — this is a session log, not a `YYMMDD_WW-YY_` report per
  CLAUDE.md)

## Environment detection — Claude Code vs. pi

This skill runs under two harnesses with different env vars and
transcript formats. Detect which one you are in **once, at the start**,
and branch every session-ID / transcript / model step on the result:

```bash
if [ -n "$PI_SESSION_FILE" ]; then
  HARNESS=pi
  SID="$PI_SESSION_ID"
  TRANSCRIPT="$PI_SESSION_FILE"          # pi hands us the path directly
elif [ -n "$CLAUDE_CODE_SESSION_ID" ]; then
  HARNESS=claude
  SID="$CLAUDE_CODE_SESSION_ID"
  TRANSCRIPT=$(find ~/.claude/projects -name "$SID.jsonl" 2>/dev/null | head -1)
else
  echo 'to-journal: neither PI_SESSION_FILE nor CLAUDE_CODE_SESSION_ID set — unknown harness' >&2
  exit 1
fi
```

| | Claude Code | pi |
|---|---|---|
| Session ID | `$CLAUDE_CODE_SESSION_ID` | `$PI_SESSION_ID` |
| Transcript | `~/.claude/projects/<slug>/<sid>.jsonl` (found via `find`) | `$PI_SESSION_FILE` (exact path, no lookup) |
| Model name | read from the session's environment block (step 3) | `$PI_MODEL` (+ `$PI_PROVIDER`) |
| JSONL shape | top-level `"type": "user" \| "assistant"` | `"type": "message"` with `message.role` = `user` \| `assistant` \| `toolResult` |

The step-7 extraction script handles both shapes — feed it
`$TRANSCRIPT` and it branches internally.

## What I do

1. **Get today's filename stem and current time:**
   ```bash
   date +%y%m%d      # → YYMMDD for the filename
   date +%H:%M:%S    # → time of the record
   ```

2. **Detect the harness and get the session ID** — run the detection
   block under "Environment detection" above. It sets `$HARNESS`,
   `$SID`, and `$TRANSCRIPT` from `PI_SESSION_FILE`/`PI_SESSION_ID`
   (pi) or `CLAUDE_CODE_SESSION_ID` (Claude Code). `$SID` matches the
   session's own transcript file and goes into the journal entry.

3. **Get the model name** — branch on `$HARNESS`:

   - **pi:** read the env vars — no context reading needed:
     ```bash
     echo "$PI_MODEL ($PI_PROVIDER, via pi)"   # e.g. "k3-256k (kimi-coding, via pi)"
     ```
   - **Claude Code:** read it from this session's own environment
     block, not from a tool call. Every session's environment block
     includes a line of the form:
     > "You are powered by the model glm-5.2."
     or
     > "You are powered by the model named **Sonnet 5**. The exact model
     > ID is **claude-sonnet-5**."

     Capture whatever that line states — a bare name (`glm-5.2`) or a
     friendly name + exact ID pair (`Sonnet 5 (claude-sonnet-5)`).
     There is no tool that returns this — read it directly from
     context. Do **not** assume an Anthropic model; this workspace may
     run against a non-Anthropic endpoint (Zhipu GLM, Aliyun, etc.).

4. **Summarize the session** in 3-8 concise bullet points covering:
   major decisions, findings, results, and actions. Note what was
   asked, what was done/decided, what files changed, what's left open.
   Bullet points, not prose (per CLAUDE.md house style).

5. **Resolve the main project root** into `$ROOT` (see Paths — do this
   once, before any file operation, and from the session's launch
   directory, not a drifted shell cwd), then **locate or create the
   `journal/` folder** under it:
   ```bash
   [ -d "$ROOT/journal" ] || mkdir "$ROOT/journal"
   ```

6. Set `JFILE="$ROOT/journal/YYMMDD_journal.md"`. **Check whether
   `$JFILE` already exists** for today's date.

   - **Does not exist:** create the file (Write) with a top header and
     one entry (first-entry template below). Pass the absolute path
     `$JFILE` to Write/Edit.
   - **Exists:** append a new `## Entry — HH:MM:SS` section to the
     bottom of the file (use Edit on `$JFILE`, not Write, so earlier
     entries are preserved verbatim). Separate entries with a `---` rule
     (subsequent-entry template below).

   **Template (first entry / whole new file):**
   ```markdown
   # Journal — DD MMM YYYY

   ## Entry — HH:MM:SS
   - **Model:** <name from step 3>
   - **Session ID:** <value of $SID>

   <3-8 bullet points summarizing the session>
   ```

   **Template (subsequent entry, appended):**
   ```markdown

   ---

   ## Entry — HH:MM:SS
   - **Model:** <name from step 3>
   - **Session ID:** <value of $SID>

   <3-8 bullet points summarizing the session>
   ```

7. **Extract your last response before this `/to-journal` call and copy
   it to the clipboard.** The response to copy is the assistant text
   immediately **before the human message that invokes `/to-journal`** —
   whether `/to-journal` is called standalone (`/to-journal`) **or chained
   inside another command** (e.g. `/to-logbook` with args `and then
   /to-journal`). Extract it from the transcript JSONL and pipe it to
   `pbcopy`. `$TRANSCRIPT` comes from the detection block (see
   "Environment detection"); the parser below handles both JSONL shapes:

   ```bash
   LASTRESP=$(python3 - "$TRANSCRIPT" <<'PY'
   import sys, json
   path = sys.argv[1]
   msgs = []  # (kind, text): kind in {human, assistant}; human = real user msg (not tool_result)
   try:
       with open(path) as f:
           for line in f:
               line = line.strip()
               if not line:
                   continue
               try:
                   o = json.loads(line)
               except Exception:
                   continue
               t = o.get('type')
               if t == 'message':
                   # pi shape: {"type":"message","message":{"role":"user"|"assistant"|"toolResult",...}}
                   m = o.get('message') or {}
                   role = m.get('role')
                   if role == 'toolResult':
                       continue
                   if role not in ('user', 'assistant'):
                       continue
                   content = m.get('content')
               elif t in ('user', 'assistant'):
                   # Claude Code shape: {"type":"user"|"assistant","message":{"content":...}}
                   role = t
                   content = (o.get('message') or {}).get('content')
               else:
                   continue
               parts, is_tool_result = [], False
               if isinstance(content, str):
                   parts.append(content)
               elif isinstance(content, list):
                   for b in content:
                       if not isinstance(b, dict):
                           continue
                       if b.get('type') == 'text':
                           parts.append(b.get('text', ''))
                       elif b.get('type') == 'tool_result':
                           is_tool_result = True
               text = '\n'.join(p for p in parts if p)
               if role == 'user' and not is_tool_result:
                   msgs.append(('human', text))
               elif role == 'assistant' and text.strip():
                   msgs.append(('assistant', text))
   except FileNotFoundError:
       msgs = []
   # trigger = the human message that invokes /to-journal — standalone
   # ("/to-journal") OR chained inside another command (e.g. "/to-logbook"
   # with args "and then /to-journal"). Skill bodies are injected as
   # user-role text messages beginning with "Base directory for this skill:";
   # they are NOT human commands and MUST be excluded, otherwise the
   # trigger becomes the to-journal skill body and the walk-back grabs the
   # chained skill's narration ("Now chaining to /to-journal:") instead of
   # the real reply.
   def is_journal_call(txt):
       # Claude Code injects skill bodies as user-role text beginning with
       # "Base directory for this skill:"; pi injects the skill body as a
       # <skill name="to-journal" ...> XML block inside the invoking message
       # itself — that block IS the call, so it must stay eligible.
       return '/to-journal' in txt and not txt.startswith('Base directory for this skill:')
   human_idx = [i for i, (k, txt) in enumerate(msgs) if k == 'human' and is_journal_call(txt)]
   if not human_idx:
       print('(No prior response found — transcript unreadable or empty.)')
   else:
       trig = human_idx[-1]
       found = None
       for i in range(trig - 1, -1, -1):
           k, txt = msgs[i]
           if k == 'assistant':
               found = txt
               break
       print(found if found else '(No prior assistant response in this session to copy.)')
   PY
   )
   printf '%s' "$LASTRESP" | pbcopy && echo "pbcopy OK"
   ```

   The trigger is the human `/to-journal` call itself, and the extraction
   only ever looks at messages **before** that call — so the skill's own
   narration/tool calls during this turn, the chained skill's body, and
   any chaining narration ("Now chaining to `/to-journal`:") are never
   copied. If the session has no prior assistant response (e.g.
   `/to-journal` was the first message), a clear fallback string is
   copied instead.

8. **Tell the user** the journal entry was written (new file vs.
   appended, with the path) and that your last response has been copied
   to the clipboard, then in that same final message instruct them to
   run `/clear`.

## Gotcha — `/copy` and `/clear` cannot be triggered programmatically

There is no tool that lets the agent invoke `/copy` or `/clear`. In
Claude Code both are client-side REPL commands handled by the CLI
itself when *you* type them; pi's REPL commands are likewise
client-side. Text the model outputs (even the literal string `/copy`
or `/clear`) is not intercepted as a command. Confirmed directly
against the installed Claude Code binary:
```
grep -a -o 'name:"copy"[^}]\{0,200\}' claude
# → name:"copy",description:"Copy Claude's last response to clipboard
#   (or /copy N for the Nth-latest)",requires:{ink:!0
```
`requires:{ink:!0}` means it needs the terminal UI layer — REPL-only.

That is why step 7 reads the transcript and pipes the extracted last
response through `pbcopy` (a real shell command the agent *can* run)
rather than "calling `/copy`." `/clear` has no shell equivalent, so it
remains a spoken instruction for you to run.

Note: `/copy` and this skill's `pbcopy` step differ in one edge case.
`/copy` copies the model's single most recent response; this skill
copies the last response **before** the `/to-journal` call (i.e. the
previous turn's final reply), which is what you want for continuation.

## Output

No chat-facing report — the journal entry on disk is the durable
artifact; the clipboard holds the continuation text. Final chat message
is a one-line confirmation (journal path written + last response copied
to clipboard) + the `/clear` reminder.
