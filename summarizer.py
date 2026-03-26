"""Summarize story clusters using Claude."""
from __future__ import annotations

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
) -> str:
    """Generate a unified Hebrew summary for a cluster of related articles."""
    cluster_text = _build_cluster_text(cluster)

    prompt = f"""You are an experienced wrestling news editor. Below are {'multiple articles' if len(cluster) > 1 else 'an article'} covering the story: "{story_title}".

{cluster_text}

Write your response in exactly this format:
TL;DR: <one sentence summary of the key fact>

<full article — complete, well-structured, multiple paragraphs>

Rules for the full article:
- Preserve ALL information, details, quotes, and context
- Remove only pure duplicate sentences
- Do not start with "Summary:" or "Title:" — just write the article directly
- Do not mention website/source names in the body
- If the excerpt is incomplete, summarize what is available — do not ask for more content"""

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def summarize_all(
    clusters: list[list[dict[str, Any]]],
    api_key: str,
    model: str,
    min_cluster_size: int,
) -> list[dict[str, Any]]:
    """
    For each cluster produce:
      {story_title, summary, sources: [{title, url, source_name}], count}
    """
    results = []
    for cluster in clusters:
        story_title: str = cluster[0].get("_story_title", cluster[0]["title"])
        seen_sources: set[str] = set()
        sources = []
        for a in cluster:
            name = a.get("source_name", "")
            if name not in seen_sources:
                seen_sources.add(name)
                sources.append({"title": a["title"], "url": a["url"], "source_name": name})

        print(f"[summarizer] Summarizing: {story_title!r} ({len(cluster)} articles)")
        try:
            raw = summarize_cluster(cluster, story_title, api_key, model)
        except Exception as e:
            print(f"[summarizer] Error: {e}")
            raw = cluster[0].get("summary", "") or "(סיכום לא זמין)"

        # Parse TL;DR line
        tldr = ""
        summary = raw
        if raw.startswith("TL;DR:"):
            parts = raw.split("\n", 2)
            tldr = parts[0].replace("TL;DR:", "").strip()
            summary = parts[2].strip() if len(parts) > 2 else ""

        results.append({
            "story_title": story_title,
            "tldr": tldr,
            "summary": summary,
            "sources": sources,
            "count": len(cluster),
        })

    return results


def summarize_executive(digest: list[dict[str, Any]], api_key: str, model: str) -> str:
    """Generate a 3-4 sentence executive summary covering all stories in the digest."""
    if not digest:
        return ""
    titles = "\n".join(f"- {s['story_title']}" for s in digest)
    prompt = f"""You are a wrestling news editor. Here are today's top stories:
{titles}

Write a 3-4 sentence executive summary covering the highlights of today's wrestling news. Be concise and informative. Do not use bullet points."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"[summarizer] executive summary error: {e}")
        return ""
