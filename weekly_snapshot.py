#!/usr/bin/env python3
"""Write a weekly radar JSON snapshot. Exit 2 if there is nothing meaningful to commit."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import generate as g

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else None


def sunday_date_utc(now: datetime) -> str:
    # Label with the most recent Sunday (UTC), including today if Sunday.
    from datetime import timedelta
    days_since_sunday = (now.weekday() + 1) % 7
    sunday = now.date() - timedelta(days=days_since_sunday)
    return sunday.isoformat()


def main() -> int:
    payload = g.collect_radar()
    snap = g.snapshot_dict(payload)
    total = sum(snap["counts"].values())
    if total <= 0:
        print(json.dumps({"ok": False, "reason": "no_repos", "counts": snap["counts"], "errors": snap["errors"]}))
        return 2
    date_label = sunday_date_utc(g.now_utc())
    out = OUT or Path("data/weekly") / f"{date_label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    snap["snapshot_date"] = date_label
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "path": str(out), "snapshot_date": date_label, "counts": snap["counts"], "errors": snap["errors"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
