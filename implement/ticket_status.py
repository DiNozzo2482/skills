#!/usr/bin/env python3
"""Read, report and update the state of a ticket file in development/02_tickets/.

Three commands:

    status  <file> [--json]                 parse the file, print every ticket's
                                            state and the frontier
    tick    <file> --lines 31,32,34         flip `- [ ]` to `- [x]` at the given
                                            1-indexed line numbers
    mark    <file> <ticket> --status DONE   append a status marker to a ticket
            [--date DD.MM.YYYY]             heading (default date: today)

Nothing here decides whether work is finished — it only records what a human or
an agent has already established. `tick` refuses to touch a line that is not an
open checkbox, so a wrong line number fails loudly instead of editing prose.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# A status marker is one of these keywords, optionally followed by a date, at
# the very end of the heading. Anchoring on a keyword rather than on the em-dash
# matters: plenty of ticket titles contain an em-dash of their own
# ("## Ticket 1 — Scaffold: global venv, ...").
STATUS_WORDS = ("DONE", "OPEN", "DEFERRED", "OBSOLETE")
STATUS_RE = re.compile(
    r"\s+[—-]\s+(" + "|".join(STATUS_WORDS) + r")(?:\s+(\d{2}\.\d{2}\.\d{4}))?\s*$"
)

# Matches the heading styles in use: "## 1. Title", "## Ticket 1 — Title",
# "## T1 — Title", and the design-ticket form "## D4a. Title" (a letter-prefixed
# id with an optional slice suffix, where D4a/D4b are two halves of one chapter).
# A heading that does not match is a prose section ("## Implementation order")
# and is skipped.
HEADING_RE = re.compile(r"^##\s+(?:Ticket\s+)?(T?D?\d+[a-z]?)\s*[.—:-]\s*(.+?)\s*$")

CHECKBOX_RE = re.compile(r"^(\s*-\s+\[)([ xX])(\]\s+.*)$")
BLOCKED_BY_RE = re.compile(r"^\*\*Blocked by:\*\*\s*(.*)$")
PARENS_RE = re.compile(r"\([^)]*\)")
TICKET_REF_RE = re.compile(r"\b(T?D?\d+[a-z]?)\b")

DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")


def norm_id(ident: str) -> str:
    """Normalize a ticket id for blocker matching: "T3" and "3" are one ticket.

    Case-insensitive, and the optional "T" prefix is dropped — but only when it
    is a bare "Ticket" marker, never the letter of a lettered id ("D4a" keeps
    its "d"), so D4a and D4b stay distinct tickets rather than collapsing.
    """
    key = ident.strip().lower()
    if key.startswith("t") and len(key) > 1 and key[1].isdigit():
        key = key[1:]
    return key


@dataclass
class Ticket:
    ident: str  # as written: "1", "T3", "D4a"
    key: str  # normalized, for blocker matching
    title: str
    heading_line: int  # 1-indexed
    status: str | None = None  # DONE / OPEN / DEFERRED / OBSOLETE, or None
    status_date: str | None = None
    blockers: list[str] = field(default_factory=list)
    blocked_by_raw: str = ""
    boxes: list[tuple[int, bool]] = field(default_factory=list)  # (line, ticked)

    @property
    def total(self) -> int:
        return len(self.boxes)

    @property
    def ticked(self) -> int:
        return sum(1 for _, t in self.boxes if t)

    @property
    def open_lines(self) -> list[int]:
        return [ln for ln, t in self.boxes if not t]

    @property
    def finished(self) -> bool:
        """Is this ticket off the frontier?

        The heading marker wins. A DONE ticket with open boxes is finished work
        with outstanding checks, not unfinished work — the open boxes are
        reported, but they do not put it back on the frontier. OBSOLETE and
        DEFERRED are off the frontier for different reasons: one will never be
        built, the other is not being built now.
        """
        if self.status in ("DONE", "OBSOLETE", "DEFERRED"):
            return True
        if self.status == "OPEN":
            return False
        # No marker: fall back to box state.
        return self.total > 0 and self.ticked == self.total

    @property
    def state(self) -> str:
        if self.status:
            return self.status
        if self.total == 0:
            return "no criteria"
        if self.ticked == self.total:
            return "all boxes ticked, no marker"
        if self.ticked == 0:
            return "not started"
        return "in progress"

    @property
    def conflict(self) -> str | None:
        """Where the heading marker and the box state disagree."""
        if self.status == "DONE" and self.open_lines:
            return f"marked DONE but {len(self.open_lines)} of {self.total} boxes open"
        if self.status == "OPEN" and self.total and self.ticked == self.total:
            return "marked OPEN but every box is ticked"
        if self.status is None and self.total and self.ticked == self.total:
            return "every box ticked but no DONE marker on the heading"
        return None


def parse(path: Path) -> tuple[list[Ticket], list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    tickets: list[Ticket] = []
    warnings: list[str] = []
    current: Ticket | None = None

    for i, raw in enumerate(lines, start=1):
        if raw.startswith("## "):
            m = HEADING_RE.match(raw)
            if not m:
                current = None  # a prose section — stop attributing lines
                continue
            ident, title = m.group(1), m.group(2)
            status = status_date = None
            sm = STATUS_RE.search(title)
            if sm:
                status, status_date = sm.group(1), sm.group(2)
                title = title[: sm.start()].rstrip()
            current = Ticket(
                ident=ident,
                key=norm_id(ident),
                title=title,
                heading_line=i,
                status=status,
                status_date=status_date,
            )
            tickets.append(current)
            continue

        if current is None:
            continue

        bm = BLOCKED_BY_RE.match(raw)
        if bm:
            current.blocked_by_raw = bm.group(1).strip()
            current.blockers = parse_blockers(bm.group(1))
            continue

        cm = CHECKBOX_RE.match(raw)
        if cm:
            current.boxes.append((i, cm.group(2).lower() == "x"))

    known = {t.key for t in tickets}
    for t in tickets:
        if not t.blocked_by_raw:
            warnings.append(f"ticket {t.ident}: no **Blocked by:** line")
        for b in t.blockers:
            if b not in known:
                warnings.append(
                    f"ticket {t.ident}: blocked by {b}, which is not a ticket in this file"
                )
            elif b == t.key:
                warnings.append(f"ticket {t.ident}: lists itself as a blocker")
    return tickets, warnings


def parse_blockers(text: str) -> list[str]:
    """Pull ticket references out of a **Blocked by:** line.

    Parenthesised asides are stripped first — they routinely name tickets that
    are explicitly *not* blockers ("benefits from T8", "OCR in Ticket 5 is not a
    blocker"), and reading those as edges would freeze the frontier.
    """
    text = text.strip()
    if re.match(r"^none\b", text, re.IGNORECASE):
        return []
    stripped = PARENS_RE.sub(" ", text)
    seen: list[str] = []
    for m in TICKET_REF_RE.finditer(stripped):
        n = norm_id(m.group(1))
        if n not in seen:
            seen.append(n)
    return seen


def frontier(tickets: list[Ticket]) -> list[Ticket]:
    done = {t.key for t in tickets if t.finished}
    return [
        t
        for t in tickets
        if not t.finished and all(b in done for b in t.blockers)
    ]


def cmd_status(args: argparse.Namespace) -> int:
    path = Path(args.file)
    tickets, warnings = parse(path)
    if not tickets:
        print(f"No tickets found in {path}", file=sys.stderr)
        return 1

    front = frontier(tickets)
    if args.json:
        print(
            json.dumps(
                {
                    "file": str(path),
                    "tickets": [
                        {
                            "id": t.ident,
                            "title": t.title,
                            "heading_line": t.heading_line,
                            "status": t.status,
                            "status_date": t.status_date,
                            "state": t.state,
                            "blockers": t.blockers,
                            "boxes_total": t.total,
                            "boxes_ticked": t.ticked,
                            "open_lines": t.open_lines,
                            "finished": t.finished,
                            "conflict": t.conflict,
                        }
                        for t in tickets
                    ],
                    "frontier": [t.ident for t in front],
                    "warnings": warnings,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    width = max(len(t.ident) for t in tickets)
    print(f"{path}\n")
    for t in tickets:
        boxes = f"{t.ticked}/{t.total}" if t.total else "—"
        blockers = ",".join(str(b) for b in t.blockers) or "none"
        flag = "→" if t in front else " "
        print(
            f" {flag} {t.ident:<{width}}  {boxes:>7}  {t.state:<26}"
            f"  blocked by: {blockers:<12}  {t.title[:60]}"
        )
        if t.conflict:
            print(f"   {'':<{width}}  ! {t.conflict}")
        if t.open_lines and t.status != "OBSOLETE":
            print(f"   {'':<{width}}    open boxes at lines: "
                  f"{', '.join(str(n) for n in t.open_lines)}")

    print()
    if front:
        print("Frontier (blockers all done, work can start):")
        for t in front:
            print(f"  {t.ident}. {t.title}")
    else:
        print("Frontier: empty — every ticket is done, deferred or obsolete.")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  - {w}")
    return 0


def cmd_tick(args: argparse.Namespace) -> int:
    path = Path(args.file)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    targets = [int(n) for n in args.lines.split(",") if n.strip()]

    for n in targets:
        if not 1 <= n <= len(lines):
            print(f"line {n} is outside {path} (1–{len(lines)})", file=sys.stderr)
            return 1
        m = CHECKBOX_RE.match(lines[n - 1].rstrip("\n"))
        if not m:
            print(
                f"line {n} is not a checkbox: {lines[n - 1].rstrip()!r}",
                file=sys.stderr,
            )
            return 1
        if m.group(2).lower() == "x":
            print(f"line {n} is already ticked", file=sys.stderr)
            return 1

    for n in targets:
        raw = lines[n - 1]
        newline = "\n" if raw.endswith("\n") else ""
        m = CHECKBOX_RE.match(raw.rstrip("\n"))
        assert m
        lines[n - 1] = f"{m.group(1)}x{m.group(3)}{newline}"
        print(f"ticked line {n}: {m.group(3)[2:].strip()[:70]}")

    path.write_text("".join(lines), encoding="utf-8")
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    path = Path(args.file)
    tickets, _ = parse(path)
    match = [t for t in tickets if t.ident.lower() == args.ticket.lower()]
    if not match:
        print(
            f"no ticket {args.ticket!r} in {path} "
            f"(found: {', '.join(t.ident for t in tickets)})",
            file=sys.stderr,
        )
        return 1
    ticket = match[0]

    stamp = args.date or date.today().strftime("%d.%m.%Y")
    if not DATE_RE.match(stamp):
        print(f"date must be DD.MM.YYYY, got {stamp!r}", file=sys.stderr)
        return 1

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    idx = ticket.heading_line - 1
    heading = lines[idx].rstrip("\n")
    newline = "\n" if lines[idx].endswith("\n") else ""

    heading = STATUS_RE.sub("", heading)  # replace any existing marker
    suffix = f" — {args.status}"
    if args.status == "DONE":
        suffix += f" {stamp}"
    lines[idx] = heading + suffix + newline

    path.write_text("".join(lines), encoding="utf-8")
    print(f"heading now: {lines[idx].rstrip()}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="report ticket states and the frontier")
    s.add_argument("file")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_status)

    t = sub.add_parser("tick", help="tick open checkboxes by line number")
    t.add_argument("file")
    t.add_argument("--lines", required=True, help="comma-separated 1-indexed lines")
    t.set_defaults(func=cmd_tick)

    m = sub.add_parser("mark", help="write a status marker onto a ticket heading")
    m.add_argument("file")
    m.add_argument("ticket", help='ticket id as written, e.g. "3" or "T7"')
    m.add_argument("--status", default="DONE", choices=STATUS_WORDS)
    m.add_argument("--date", help="DD.MM.YYYY (default: today)")
    m.set_defaults(func=cmd_mark)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
