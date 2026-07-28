"""Persistent cross-run story memory.

Wrestling sites re-chew the same story for days on end, so every morning's run
would otherwise re-cluster an ongoing story as if it were fresh news. This module
keeps the last few days of story titles + TL;DRs in docs/history.json so the
clusterer can tell a genuine development from yesterday's leftovers.

The file lives under docs/ on purpose: the GitHub Action already does
`git add docs/`, so the state survives between runs with no workflow change.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any

HISTORY_FILENAME = "history.json"
DEFAULT_DAYS = 5


def _path(docs_dir: str) -> str:
    return os.path.join(docs_dir, HISTORY_FILENAME)


def _prune(entries: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    """Keep only entries from the last `days` days, newest first."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    kept = [e for e in entries if isinstance(e, dict) and e.get("date", "") >= cutoff]
    kept.sort(key=lambda e: e.get("date", ""), reverse=True)
    return kept


def load(docs_dir: str, days: int = DEFAULT_DAYS) -> list[dict[str, Any]]:
    """Return the last `days` days of digest history, newest first.

    Never raises — a missing or corrupt file just means "no memory", which
    degrades to the old behaviour (everything looks new) rather than killing
    the pipeline.
    """
    try:
        with open(_path(docs_dir), encoding="utf-8") as f:
            entries = json.load(f)
        if not isinstance(entries, list):
            return []
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"[history] Could not read history file ({e}) — treating as empty")
        return []

    pruned = _prune(entries, days)
    total = sum(len(e.get("stories", [])) for e in pruned)
    print(f"[history] Loaded {total} stories from the last {len(pruned)} day(s)")
    return pruned


def append(
    docs_dir: str,
    date_str: str,
    digest: list[dict[str, Any]],
    days: int = DEFAULT_DAYS,
) -> None:
    """Record today's stories and prune anything older than `days`.

    `date_str` is an ISO date (YYYY-MM-DD). Re-running on the same date replaces
    that day's entry rather than duplicating it.
    """
    entries = load(docs_dir, days=days)
    entries = [e for e in entries if e.get("date") != date_str]
    entries.append({
        "date": date_str,
        "stories": [
            {
                "title": s.get("story_title", ""),
                "tldr": s.get("tldr", "") or s.get("summary", "")[:300],
                "promotion": s.get("promotion", "Other"),
            }
            for s in digest
        ],
    })
    entries = _prune(entries, days)

    os.makedirs(docs_dir, exist_ok=True)
    with open(_path(docs_dir), "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    print(f"[history] Saved {len(digest)} stories for {date_str} ({len(entries)} day(s) retained)")


def as_prompt_block(entries: list[dict[str, Any]]) -> str:
    """Render history as a plain-text block for a Claude prompt."""
    lines = []
    for entry in entries:
        for s in entry.get("stories", []):
            title = s.get("title", "").strip()
            if not title:
                continue
            lines.append(f"[{entry.get('date', '')}] {title}")
            tldr = (s.get("tldr") or "").strip()
            if tldr:
                lines.append(f"    {tldr[:300]}")
    return "\n".join(lines)
