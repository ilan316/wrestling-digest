#!/usr/bin/env python3
"""Feedly Daily Digest Agent — entry point."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import config
import feedly_client
import clusterer
import summarizer
import email_sender
import history
import llm

PROMO_ORDER = {"AEW": 0, "WWE": 1, "Other": 2}

# Lookback spans back to the last successful send, so a failed day's news is not
# lost — capped so a long outage does not flood one digest. Lives under docs/ so
# the workflow's `git add docs/` persists it (same trick as history.json).
STATE_FILENAME = "state.json"
MAX_LOOKBACK_HOURS = 72
_LOOKBACK_MARGIN_HOURS = 1


def _lookback_hours(docs_dir: str) -> float:
    try:
        with open(os.path.join(docs_dir, STATE_FILENAME), encoding="utf-8") as f:
            last_ts = float(json.load(f)["last_run_ts"])
    except Exception:
        return config.LOOKBACK_HOURS
    since = (time.time() - last_ts) / 3600 + _LOOKBACK_MARGIN_HOURS
    hours = min(max(since, config.LOOKBACK_HOURS), MAX_LOOKBACK_HOURS)
    print(f"[main] Last successful run {since - _LOOKBACK_MARGIN_HOURS:.1f}h ago — lookback {hours:.1f}h")
    return hours


def _save_last_run(docs_dir: str, ts: float) -> None:
    with open(os.path.join(docs_dir, STATE_FILENAME), "w", encoding="utf-8") as f:
        json.dump({"last_run_ts": ts}, f)


def run(dry_run: bool = False) -> None:
    print("=" * 50)
    print("Feedly Daily Digest Agent" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 50)

    # A dry run exercises the full pipeline, so left alone it spends the strong
    # model's 20/day allowance on a test — and that allowance does not reset until
    # after the next scheduled run. Keep manual testing off that budget entirely.
    if dry_run:
        llm.disable_heavy_model("dry run — leaving the daily budget for the scheduled run")

    # run.yml has no native `schedule:` trigger anymore — GitHub's own cron
    # repeatedly fired hours late or not at all (see wrestling-digest loop notes
    # 2026-08-29). The sole daily trigger is now an external cron-job.org job
    # (10:00 Asia/Jerusalem, native timezone — no UTC/DST math needed) plus
    # watchdog.yml as a fallback, both firing via workflow_dispatch. Same-day
    # dedup still applies to every non-dry-run trigger so a watchdog fallback (or
    # a manual re-run) landing after the primary trigger already sent is a no-op
    # instead of a duplicate email.
    docs_dir = os.path.join(os.path.dirname(__file__), "docs")
    if not dry_run:
        il_now = datetime.now(ZoneInfo("Asia/Jerusalem"))
        today_file = os.path.join(docs_dir, f"{il_now:%Y-%m-%d}-digest.html")
        if os.path.exists(today_file):
            print(f"[main] Digest for {il_now:%Y-%m-%d} already sent — skipping duplicate run.")
            return

    # 1. Fetch all articles
    run_started = time.time()
    articles = feedly_client.fetch_all(
        opml_path=config.OPML_PATH,
        categories_filter=config.CATEGORIES_FILTER,
        lookback_hours=_lookback_hours(docs_dir),
    )
    if not articles:
        print("[main] No articles found. Exiting.")
        return

    # 2. Cluster ALL articles at once (the model classifies each by promotion)
    print(f"\n[main] Clustering {len(articles)} articles...")
    all_clusters = clusterer.group_by_story(articles=articles)

    # Keep only the configured promotions, before the history filter and the
    # summaries, so dropped promotions never reach an LLM call.
    all_clusters = [
        c for c in all_clusters if c[0].get("promotion", "Other") in config.PROMOTIONS
    ]
    print(f"[main] Keeping {config.PROMOTIONS} — {len(all_clusters)} clusters")
    if not all_clusters:
        print("[main] No stories for the selected promotions. Nothing to send.")
        return

    # 3. Drop stories we already sent in the last few days. Wrestling sites rehash the
    # same story daily, so without this the digest repeats itself every morning.
    # Fails open — on any error every cluster survives.
    history_entries = history.load(docs_dir)
    all_clusters = clusterer.filter_against_history(
        clusters=all_clusters,
        history_block=history.as_prompt_block(history_entries),
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
    digest = summarizer.summarize_all(clusters=all_clusters)

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
    _save_last_run(docs_dir, run_started)

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
