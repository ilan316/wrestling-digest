#!/usr/bin/env python3
"""Feedly Daily Digest Agent — entry point."""
from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import config
import feedly_client
import clusterer
import summarizer
import email_sender

PROMO_ORDER = {"AEW": 0, "WWE": 1, "Other": 2}


def run() -> None:
    print("=" * 50)
    print("Feedly Daily Digest Agent")
    print("=" * 50)

    # DST-proof scheduling guard. GitHub Actions cron is UTC-only, so run.yml fires
    # at both 04:43 and 05:43 UTC and we let the run that lands on ~07:xx Israel time
    # do the work — no manual cron edits at DST changeovers. Delay-tolerant: a late
    # run only lands *later* than 07:00 (still >= 7), never earlier, so a day is
    # never silently dropped. Manual workflow_dispatch bypasses the guard entirely.
    docs_dir = os.path.join(os.path.dirname(__file__), "docs")
    manual = os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"
    if not manual:
        il_now = datetime.now(ZoneInfo("Asia/Jerusalem"))
        if il_now.hour < 7:
            print(f"[main] Israel time {il_now:%H:%M} is before 07:00 — the other scheduled run will send. Skipping.")
            return
        today_file = os.path.join(docs_dir, f"{il_now:%Y-%m-%d}-digest.html")
        if os.path.exists(today_file):
            print(f"[main] Digest for {il_now:%Y-%m-%d} already sent — skipping duplicate run.")
            return

    # 1. Fetch all articles
    articles = feedly_client.fetch_all(
        opml_path=config.OPML_PATH,
        categories_filter=config.CATEGORIES_FILTER,
        lookback_hours=config.LOOKBACK_HOURS,
    )
    if not articles:
        print("[main] No articles found. Exiting.")
        return

    # 2. Cluster ALL articles at once (Claude classifies each by promotion)
    print(f"\n[main] Clustering {len(articles)} articles...")
    all_clusters = clusterer.group_by_story(
        articles=articles,
        api_key=config.CLAUDE_API_KEY,
        model=config.CLAUDE_MODEL,
    )

    # 3. Tally clusters by promotion (articles are already lookback-filtered in fetch_all)
    by_promo: dict[str, int] = {}
    for cluster in all_clusters:
        key = cluster[0].get("promotion", "Other")
        by_promo[key] = by_promo.get(key, 0) + 1
    print(f"[main] AEW={by_promo.get('AEW', 0)}  WWE={by_promo.get('WWE', 0)}  Other={by_promo.get('Other', 0)} clusters")

    if not all_clusters:
        print("[main] No stories after filtering. Exiting.")
        return

    # 4. Summarize all clusters together
    digest = summarizer.summarize_all(
        clusters=all_clusters,
        api_key=config.CLAUDE_API_KEY,
        model=config.CLAUDE_MODEL,
    )

    # Sort: AEW → WWE → Other, then by source count descending
    digest.sort(key=lambda s: (PROMO_ORDER.get(s.get("promotion", "Other"), 2), -s["count"]))

    # Date range across all articles
    date_str = datetime.now().strftime("%d/%m")
    all_pub = [
        a["published"]
        for cluster in all_clusters
        for a in cluster
        if a.get("published")
    ]
    if all_pub:
        date_from = datetime.fromtimestamp(min(all_pub) / 1000).strftime("%d/%m")
        date_to   = datetime.fromtimestamp(max(all_pub) / 1000).strftime("%d/%m")
        date_range = date_from if date_from == date_to else f"{date_from} – {date_to}"
    else:
        date_range = date_str

    # 5. Save one combined GitHub Pages file
    pages_url = email_sender.save_combined_page(
        digest=digest,
        date_str=date_range,
        docs_dir=docs_dir,
    )

    # 6. Send ONE combined email
    email_sender.send(
        digest=digest,
        gmail_user=config.GMAIL_USER,
        gmail_app_password=config.GMAIL_APP_PASSWORD,
        recipient=config.RECIPIENT_EMAIL,
        title="Wrestling Digest",
        emoji="🤼",
        date_range=date_range,
        pages_url=pages_url,
    )

    print("\n[main] Done.")


def _send_error_email(subject: str, body: str) -> None:
    try:
        email_sender.send_error(
            gmail_user=config.GMAIL_USER,
            gmail_app_password=config.GMAIL_APP_PASSWORD,
            recipient=config.RECIPIENT_EMAIL,
            subject=subject,
            body=body,
        )
    except Exception as e:
        print(f"[main] Failed to send error email: {e}")


if __name__ == "__main__":
    import traceback
    try:
        run()
    except Exception:
        tb = traceback.format_exc()
        print(tb)
        _send_error_email(
            subject="⚠️ Wrestling Digest — Pipeline Error",
            body=f"The wrestling digest pipeline failed.\n\n{tb}",
        )
        raise
