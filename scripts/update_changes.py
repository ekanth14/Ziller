"""Rebuild CHANGES.md: a dated record of every modification, upgrade, fix and deletion.

Source of truth is the git history, so nothing is ever missed or invented:
    python scripts/update_changes.py

Each commit becomes one entry with its date and time (IST), type, summary, short hash and the
files it added, modified and deleted. Run it after every commit (or let the assistant do it).
"""
from __future__ import annotations

import re
import subprocess
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "CHANGES.md"
IST = timezone(timedelta(hours=5, minutes=30))
SEP, END = "\x1f", "\x1e"

TYPES = [  # (label, test on subject/stats)
    ("Deletion", lambda s, st: bool(re.match(r"(?i)(remove|delete|drop|cleanup|chore\(cleanup\))", s)) or (st["D"] > 0 and st["D"] >= st["A"] + st["M"])),
    ("Fix", lambda s, st: s.lower().startswith("fix")),
    ("Upgrade", lambda s, st: s.lower().startswith(("feat", "perf", "upgrade")) or "upgrade" in s.lower()),
    ("Docs", lambda s, st: s.lower().startswith("docs")),
    ("Security", lambda s, st: s.lower().startswith(("sec", "security"))),
    ("Test", lambda s, st: s.lower().startswith("test")),
    ("Modification", lambda s, st: True),
]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout


def commits():
    raw = git("log", "--no-merges", "--date=iso-strict", f"--pretty=format:{END}%h{SEP}%aI{SEP}%an{SEP}%s{SEP}%b{SEP}", "--name-status")
    for chunk in raw.split(END):
        if not chunk.strip():
            continue
        h, date, author, subject, body, files = chunk.split(SEP, 5)
        st = {"A": [], "M": [], "D": [], "R": []}
        for line in files.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0]:
                kind = parts[0][0]
                st.setdefault(kind, []).append(parts[-1])
        yield h, datetime.fromisoformat(date).astimezone(IST), author, subject.strip(), body.strip(), st


def classify(subject, st):
    counts = {k: len(v) for k, v in st.items()}
    for label, test in TYPES:
        if test(subject, counts):
            return label
    return "Modification"


def fmt_files(paths, limit=12):
    shown = ", ".join(f"`{p}`" for p in paths[:limit])
    return shown + (f" … and {len(paths) - limit} more" if len(paths) > limit else "")


def main():
    by_day: "OrderedDict[str, list]" = OrderedDict()
    totals = {"Upgrade": 0, "Fix": 0, "Modification": 0, "Deletion": 0, "Docs": 0, "Security": 0, "Test": 0}
    for h, when, author, subject, body, st in commits():
        label = classify(subject, st)
        totals[label] = totals.get(label, 0) + 1
        if st.get("D") and label != "Deletion":
            label += " + Deletion"          # never hide a deletion inside a feature/fix commit
            totals["Deletion"] = totals.get("Deletion", 0) + 1
        by_day.setdefault(when.strftime("%Y-%m-%d (%A)"), []).append((h, when, author, subject, body, st, label))
    out = [
        "# ZILLERS — Change Record",
        "",
        "Every modification, upgrade, fix and deletion, newest first, with date and time (IST, UTC+05:30).",
        "Generated from git history by `python scripts/update_changes.py`; regenerate after each commit.",
        "Deleted code remains recoverable from git with `git show <hash>^:<path>`.",
        "",
        "Totals: " + " · ".join(f"{k} {v}" for k, v in totals.items() if v),
        "",
        "Types: **Upgrade** = new feature or capability · **Fix** = bug fix · **Modification** = change/refactor/chore · "
        "**Deletion** = code or files removed · **Docs** · **Security** · **Test**.",
        "",
    ]
    for day, entries in by_day.items():
        out += [f"## {day}", ""]
        for h, when, author, subject, body, st, label in entries:
            n = {k: len(v) for k, v in st.items()}
            out.append(f"- **{when.strftime('%H:%M')} IST** · **{label}** · {subject} (`{h}`, {author})")
            out.append(f"  - Files: +{n.get('A', 0)} added · ~{n.get('M', 0)} modified · −{n.get('D', 0)} deleted"
                       + (f" · {n.get('R', 0)} renamed" if n.get("R") else ""))
            if st.get("D"):
                out.append(f"  - Deleted: {fmt_files(st['D'])}")
            if st.get("A"):
                out.append(f"  - Added: {fmt_files(st['A'], 8)}")
            detail = [l.strip("-* ").strip() for l in body.splitlines()
                      if l.strip() and not l.lower().startswith(("co-authored-by", "signed-off-by"))]
            if detail:
                out.append("  - Details: " + " ".join(detail)[:600])
        out.append("")
    OUT.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote {OUT.name}: {sum(len(v) for v in by_day.values())} entries over {len(by_day)} days")


if __name__ == "__main__":
    main()
