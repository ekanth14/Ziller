#!/usr/bin/env python3
"""CLI utility to view and inspect all received collaboration requests for ZILLERS."""
import json
import sys
from pathlib import Path

COLLAB_FILE = Path(__file__).resolve().parents[1] / "data" / "collaborations.json"

def main():
    print("=" * 80)
    print("  ZILLERS // ZIEN ORGANISATION — INCOMING COLLABORATION PROPOSALS")
    print("=" * 80)

    if not COLLAB_FILE.is_file():
        print(f"\n[INFO] No collaboration proposals file found yet at:\n  {COLLAB_FILE}\n")
        print("Proposals submitted via the website form or POST /api/collaborate will appear here.\n")
        return

    try:
        records = json.loads(COLLAB_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[ERROR] Failed to read {COLLAB_FILE}: {exc}")
        sys.exit(1)

    if not records:
        print("\n[INFO] 0 collaboration proposals recorded yet.\n")
        return

    print(f"\nTotal proposals logged: {len(records)}\n")
    print("-" * 80)

    for i, rec in enumerate(records, 1):
        collab_id = rec.get("id", "UNKNOWN")
        ts = rec.get("timestamp", "UNKNOWN")
        name = rec.get("name", "N/A")
        email = rec.get("email", "N/A")
        github = rec.get("github", "N/A")
        linkedin = rec.get("linkedin", "N/A")
        website = rec.get("website", "") or "None provided"
        track = rec.get("track", "General Quantitative Engineering")
        msg = rec.get("message", "") or "No custom message provided"
        ip = rec.get("client_ip", "N/A")

        print(f"[{i}/{len(records)}] REF: {collab_id}  |  DATE: {ts}")
        print(f"  Researcher : {name} <{email}>")
        print(f"  GitHub     : {github}")
        print(f"  LinkedIn   : {linkedin}")
        print(f"  Website    : {website}")
        print(f"  Focus Track: {track}")
        print(f"  Client IP  : {ip}")
        print(f"  Proposal   :\n    {msg}")
        print("-" * 80)

if __name__ == "__main__":
    main()
