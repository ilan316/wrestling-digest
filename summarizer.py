"""Summarize story clusters using Claude."""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import anthropic


def _build_cluster_text(cluster: list[dict[str, Any]]) -> str:
    parts = []
    for a in cluster:
        parts.append(f"- Title: {a['title']}")
        parts.append(f"  Source: {a.get('source_name', 'Unknown')}")
        if a.get("summary"):
            parts.append(f"  Excerpt: {a['summary'][:4000]}")
        parts.append("")
    return "\n".join(parts)


def summarize_cluster(
    cluster: list[dict[str, Any]],
    story_title: str,
    api_key: str,
    model: str,
    prev_tldr: str = "",
) -> str:
    """Generate a unified Hebrew summary for a cluster of related articles.

    When `prev_tldr` is set the reader already received this story in an earlier
    digest, so the summary must cover only what has changed since then.
    """
    cluster_text = _build_cluster_text(cluster)

    if prev_tldr:
        continuation_block = f"""
IMPORTANT — the reader ALREADY received this story in a previous digest:
"{prev_tldr}"

Write only what is NEW since then. Open with at most one short sentence of context, then go
straight to the new development. Do not re-tell background the reader already has. If most of
the material below repeats what they already know, keep the whole piece short.
"""
        length_rule = "- Cover the new developments fully, but skip anything already covered above"
    else:
        continuation_block = ""
        length_rule = "- Preserve ALL information, details, quotes, and context"

    prompt = f"""You are an experienced wrestling news editor. Below are {'multiple articles' if len(cluster) > 1 else 'an article'} covering the story: "{story_title}".
{continuation_block}
{cluster_text}

Write your response in exactly this format (no markdown, no bold, no asterisks):
TL;DR: <3-4 sentence summary with enough context to understand the full story>

<full article — complete, well-structured, multiple paragraphs>

Rules for the full article:
{length_rule}
- Remove only pure duplicate sentences
- Do not start with "Summary:" or "Title:" — just write the article directly
- Do not mention website/source names in the body
- If the excerpt is incomplete, summarize what is available — do not ask for more content
- Do not use markdown formatting (no **, no --, no ##)"""

    client = anthropic.Anthropic(api_key=api_key)
    for attempt in range(4):
        try:
            message = client.messages.create(
                model=model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except anthropic.APIStatusError as e:
            if e.status_code != 529 or attempt == 3:
                raise
            wait = 30 * (2 ** attempt)
            print(f"[summarizer] Claude overloaded (attempt {attempt+1}/4), retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError("unreachable")  # loop either returns or raises


def summarize_all(
    clusters: list[list[dict[str, Any]]],
    api_key: str,
    model: str,
) -> list[dict[str, Any]]:
    """
    For each cluster produce:
      {story_title, summary, sources: [{title, url, source_name}], count}
    """
    def _summarize_one(cluster: list[dict[str, Any]]) -> str:
        story_title: str = cluster[0].get("_story_title", cluster[0]["title"])
        prev_tldr: str = cluster[0].get("_prev_tldr", "")
        cont = " [continuation]" if prev_tldr else ""
        print(f"[summarizer] Summarizing: {story_title!r} ({len(cluster)} articles){cont}")
        try:
            return summarize_cluster(cluster, story_title, api_key, model, prev_tldr=prev_tldr)
        except Exception as e:
            print(f"[summarizer] Error: {e}")
            return cluster[0].get("summary", "") or "(סיכום לא זמין)"

    # Each cluster is an independent Claude call — run them in parallel instead of
    # serially. ThreadPoolExecutor.map preserves input order, so results still align.
    with ThreadPoolExecutor(max_workers=6) as executor:
        raws = list(executor.map(_summarize_one, clusters))

    results = []
    for cluster, raw in zip(clusters, raws):
        story_title = cluster[0].get("_story_title", cluster[0]["title"])
        seen_sources: set[str] = set()
        sources = []
        for a in cluster:
            name = a.get("source_name", "")
            if name not in seen_sources:
                seen_sources.add(name)
                sources.append({"title": a["title"], "url": a["url"], "source_name": name})

        # Parse TL;DR block — handle plain "TL;DR:" or markdown "**TL;DR:**"
        tldr = ""
        summary = raw
        m = re.match(r'^\*{0,2}TL;DR:\*{0,2}\s*(.*?)(?:\n\n|\n---|\Z)(.*)', raw, re.DOTALL)
        if m:
            tldr = m.group(1).strip()
            summary = m.group(2).strip()

        results.append({
            "story_title": story_title,
            "tldr": tldr,
            "summary": summary,
            "sources": sources,
            "count": len(cluster),
            "promotion": cluster[0].get("promotion", "Other"),
            "is_update": bool(cluster[0].get("_is_update")),
        })

    return results


