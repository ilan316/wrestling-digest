"""Summarize story clusters using an LLM."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import llm


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
    prev_tldr: str = "",
) -> str | None:
    """Generate a unified summary for a cluster of related articles.

    Returns None if the model call failed — the caller falls back to the raw excerpt.

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

    return llm.generate(prompt, max_tokens=4096, tag="summarizer")


def summarize_all(clusters: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
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
            text = summarize_cluster(cluster, story_title, prev_tldr=prev_tldr)
        except Exception as e:
            print(f"[summarizer] Error: {e}")
            text = None
        if text:
            return text
        # A single failed story must not take the digest down — fall back to the
        # raw feed excerpt so the reader still gets the item.
        print(f"[summarizer] Falling back to raw excerpt for {story_title!r}")
        return cluster[0].get("summary", "") or "(summary unavailable)"

    # Each cluster is an independent model call — run them in parallel instead of
    # serially. The rate limiter in llm.py, not the pool size, sets the actual pace.
    # ThreadPoolExecutor.map preserves input order, so results still align.
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


