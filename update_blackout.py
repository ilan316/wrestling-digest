"""
Fetch wrestling event schedules from cagematch.net and update blackout.json.
Run weekly to keep the schedule fresh.

Usage:
    python update_blackout.py
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime, timedelta

SOURCES = [
    {"promotion": "AEW", "url": "https://www.cagematch.net/?id=8&nr=2287&page=4&s=0"},
    {"promotion": "WWE", "url": "https://www.cagematch.net/?id=8&nr=1&page=4"},
]

BLACKOUT_PATH = os.path.join(os.path.dirname(__file__), "blackout.json")
LOOKAHEAD_DAYS = 120

# Regex to find date + event name pairs in cagematch HTML
# Matches: 15.03.2026</td>...(some cells)...<a ...>Event Name</a>
DATE_PATTERN = re.compile(
    r'(\d{2}\.\d{2}\.\d{4})</td>.*?<a[^>]+>([^<]+)</a>',
    re.DOTALL,
)


def _fetch_page(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; FeedlyDigest/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_events(promotion: str, url: str, until: datetime) -> list[dict]:
    print(f"[blackout] Fetching {promotion} schedule from cagematch...")
    html = _fetch_page(url)

    events = []
    for date_str, name in DATE_PATTERN.findall(html):
        try:
            event_date = datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            continue

        # Keep events within the lookback window (48h back) and lookahead window
        now = datetime.now()
        lookback = now - timedelta(hours=48)
        if event_date < lookback.replace(hour=0, minute=0, second=0) or event_date > until:
            continue

        # Clean up HTML entities in name
        import html as html_mod
        clean_name = html_mod.unescape(name.strip())

        # Skip weekly TV shows — blackout only for PPV/special events
        is_weekly = bool(re.search(
            r'(RAW|SmackDown|Dynamite|Collision|NXT)\s+#\d+|'
            r'(RAW|SmackDown|Dynamite|Collision|NXT)\s+Live',
            clean_name, re.IGNORECASE
        ))
        if is_weekly:
            continue

        events.append({
            "name": clean_name,
            "date": event_date.strftime("%Y-%m-%d"),
            "promotion": promotion,
            "blackout_hours": 48,
        })

    # Deduplicate by name+date
    seen = set()
    unique = []
    for e in events:
        key = (e["name"], e["date"])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    print(f"[blackout]   Found {len(unique)} upcoming events")
    return unique


def update() -> None:
    until = datetime.now() + timedelta(days=LOOKAHEAD_DAYS)
    all_events: list[dict] = []

    for source in SOURCES:
        try:
            events = fetch_events(source["promotion"], source["url"], until)
            all_events.extend(events)
        except Exception as e:
            print(f"[blackout] Error fetching {source['promotion']}: {e}")

    all_events.sort(key=lambda e: e["date"])

    with open(BLACKOUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_events, f, ensure_ascii=False, indent=2)

    print(f"[blackout] Saved {len(all_events)} events to blackout.json")

    # Preview next 14 days
    cutoff = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
    upcoming = [e for e in all_events if e["date"] <= cutoff]
    if upcoming:
        print("\n[blackout] Next 14 days:")
        for e in upcoming:
            print(f"  {e['date']}  {e['promotion']:4s}  {e['name']}")


if __name__ == "__main__":
    update()
