#!/usr/bin/env python3
"""Feedly Daily Digest Agent — entry point."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import config
import feedly_client
import clusterer
import summarizer
import email_sender
import history

PROMO_ORDER = {"AEW": 0, "WWE": 1, "Other": 2}


def run(dry_run: bool = False) -> None:
    print("=" * 50)
    print("Feedly Daily Digest Agent" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 50)

    # DST-proof scheduling guard. GitHub Actions cron is UTC-only, so run.yml fires
    # at both 04:43 and 05:43 UTC and we let the run that lands on ~07:xx Israel time
    # do the work — no manual cron edits at DST changeovers. Delay-tolerant: a late
    # run only lands *later* than 07:00 (still >= 7), never earlier, so a day is
    # never silently dropped. Manual workflow_dispatch bypasses the guard entirely.
    docs_dir = os.path.join(os.path.dirname(__file__), "docs")
    manual = os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"
    if not manual and not dry_run:
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

    # 3. Drop stories we already sent in the last few days. Wrestling sites rehash the
    # same story daily, so without this the digest repeats itself every morning.
    # Fails open — on any error every cluster survives.
    history_entries = history.load(docs_dir)
    all_clusters = clusterer.filter_against_history(
        clusters=all_clusters,
        history_block=history.as_prompt_block(history_entries),
        api_key=config.CLAUDE_API_KEY,
        model=config.CLAUDE_MODEL,
    )
    if not all_clusters:
        print("[main] Every story was already sent in a previous digest. Nothing to send.")
        return

    # 4. Tally clusters by promotion (articles are already lookback-filtered in fetch_all)
    by_promo: dict[str, int] = {}
    for cluster in all_clusters:
        key = cluster[0].get("promotion", "Other")
        by_promo[key] = by_promo.get(key, 0) + 1
    print(f"[main] AEW={by_promo.get('AEW', 0)}  WWE={by_promo.get('WWE', 0)}  Other={by_promo.get('Other', 0)} clusters")

    # 5. Summarize all clusters together
    digest = summarizer.summarize_all(
        clusters=all_clusters,
        api_key=config.CLAUDE_API_KEY,
        model=config.CLAUDE_MODEL,
    )

    # Sort: AEW → WWE → Other, fresh stories before continuations, then by source count
    digest.sort(key=lambda s: (
        PROMO_ORDER.get(s.get("promotion", "Other"), 2),
        bool(s.get("is_update")),
        -s["count"],
    ))

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

    if dry_run:
        print("\n[main] DRY RUN — final digest (nothing written, nothing sent):")
        for s in digest:
            tag = "🔄 " if s.get("is_update") else "   "
            print(f"  {tag}[{s.get('promotion', 'Other')}] {s['story_title']} ({s['count']} sources)")
        print(f"\n[main] {len(digest)} stories would be sent.")
        return

    # 6. Save one combined GitHub Pages file
    pages_url = email_sender.save_combined_page(
        digest=digest,
        date_str=date_range,
        docs_dir=docs_dir,
    )

    # Record today's stories so tomorrow's run can recognise them as already sent.
    history.append(docs_dir, datetime.now().strftime("%Y-%m-%d"), digest)

    # 7. Send ONE combined email
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
    dry = "--dry-run" in sys.argv
    try:
        run(dry_run=dry)
    except Exception:
        tb = traceback.format_exc()
        print(tb)
        if not dry:
            _send_error_email(
                subject="⚠️ Wrestling Digest — Pipeline Error",
                body=f"The wrestling digest pipeline failed.\n\n{tb}",
            )
        raise
