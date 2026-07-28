"""Group articles by news story using Claude."""
from __future__ import annotations

import json
import time
from typing import Any

import anthropic


def _ask_claude(prompt: str, api_key: str, model: str, max_tokens: int, tag: str) -> str | None:
    """Single Claude call with the 529-overload backoff. Returns None on failure —
    callers are expected to fall back to a safe no-op rather than crash the run."""
    client = anthropic.Anthropic(api_key=api_key)
    for attempt in range(4):
        try:
            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except anthropic.APIStatusError as e:
            if e.status_code != 529:
                print(f"[{tag}] Claude API error {e.status_code}: {e}")
                return None
            wait = 30 * (2 ** attempt)
            print(f"[{tag}] Claude overloaded (attempt {attempt+1}/4), retrying in {wait}s...")
            time.sleep(wait)
        except Exception as e:
            print(f"[{tag}] Claude API error: {e}")
            return None
    print(f"[{tag}] Claude still overloaded after retries")
    return None


def _parse_json(raw: str, tag: str) -> Any | None:
    """Parse a JSON response, stripping the ```json fences Claude sometimes adds."""
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[{tag}] JSON parse error: {e}\nRaw response:\n{raw[:500]}")
        return None


def group_by_story(
    articles: list[dict[str, Any]],
    api_key: str,
    model: str,
) -> list[list[dict[str, Any]]]:
    """
    Use Claude to group articles by the story they cover.
    Returns a list of clusters, each cluster is a list of article dicts.
    Articles that don't share a story with anyone else get their own cluster.
    """
    if not articles:
        return []

    # Build numbered list for the prompt
    lines = []
    for i, a in enumerate(articles):
        summary_snippet = a.get("summary", "")[:120]
        lines.append(f"{i}: {a['title']} [{a.get('source_name', '')}]")
        if summary_snippet:
            lines.append(f"   {summary_snippet}")
    article_list = "\n".join(lines)

    prompt = f"""You are a wrestling news editor. Below is a numbered list of articles (title + snippet).
Do two things:
1. Group articles by the news story they cover.
2. For each group, identify the wrestling promotion: "AEW", "WWE", or "Other" (NJPW, AAA, MLW, etc.).
   Use the full context — even if "AEW" or "WWE" is not in the title, infer from wrestlers, shows, and events mentioned.

Each article index must appear in exactly one group.

Return ONLY valid JSON (no markdown, no explanation):
[
  {{"story_title": "Short descriptive title", "promotion": "AEW", "indices": [0, 3, 7]}},
  {{"story_title": "Another story", "promotion": "WWE", "indices": [1, 2]}}
]

Articles:
{article_list}"""

    raw = _ask_claude(prompt, api_key, model, max_tokens=8192, tag="clusterer")
    if raw is None:
        print("[clusterer] Falling back to solo clusters")
        return [[a] for a in articles]

    groups = _parse_json(raw, "clusterer")
    if not isinstance(groups, list):
        # Fallback: one article per cluster
        return [[a] for a in articles]

    clusters: list[list[dict[str, Any]]] = []
    assigned: set[int] = set()
    for group in groups:
        story_title: str = group.get("story_title", "")
        promotion: str = group.get("promotion", "Other")
        indices: list[int] = group.get("indices", [])
        cluster_articles = []
        for idx in indices:
            if 0 <= idx < len(articles) and idx not in assigned:
                article = dict(articles[idx])
                article["_story_title"] = story_title
                article["promotion"] = promotion  # Claude's classification
                cluster_articles.append(article)
                assigned.add(idx)
        if cluster_articles:
            clusters.append(cluster_articles)

    # Add any articles Claude didn't assign to any group
    for i, article in enumerate(articles):
        if i not in assigned:
            a = dict(article)
            a["_story_title"] = article["title"]
            clusters.append([a])

    # Sort clusters: largest first
    clusters.sort(key=len, reverse=True)

    total = sum(len(c) for c in clusters)
    dropped = len(articles) - len(assigned)
    if dropped:
        print(f"[clusterer] WARNING: {dropped} articles were not assigned by Claude — added as solo clusters")
    print(f"[clusterer] {len(articles)} articles -> {len(clusters)} story clusters (total mapped: {total})")
    return clusters


def _norm_headline(s: str) -> str:
    """Key for matching a cited headline back to history. Claude retypes headlines
    rather than copying them byte-for-byte, so case and smart quotes must not count."""
    s = s.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'}))
    return " ".join(s.split()).casefold()


def _cluster_digest_line(idx: int, cluster: list[dict[str, Any]]) -> str:
    """One prompt line per cluster: story title + article titles + a content taste."""
    story_title = cluster[0].get("_story_title", cluster[0]["title"])
    titles = " | ".join(a["title"] for a in cluster[:4])
    snippet = (cluster[0].get("summary") or "")[:300]
    line = f"{idx}: {story_title}\n    Headlines: {titles}"
    if snippet:
        line += f"\n    Content: {snippet}"
    return line


def filter_against_history(
    clusters: list[list[dict[str, Any]]],
    history_block: str,
    api_key: str,
    model: str,
) -> list[list[dict[str, Any]]]:
    """Drop clusters that merely rehash a story we already sent, and mark the rest.

    Wrestling sites recycle the same story for days, so without this every run
    re-reports ongoing sagas as fresh news. Clusters judged to carry a real
    development are kept and tagged (`_is_update` / `_prev_tldr`) so the
    summarizer can focus on what changed.

    Fails open: on any API or parse error every cluster is returned untouched —
    a missed dedup is far cheaper than silently losing news.
    """
    if not clusters or not history_block.strip():
        return clusters

    cluster_list = "\n".join(_cluster_digest_line(i, c) for i, c in enumerate(clusters))

    prompt = f"""You are a wrestling news editor preparing today's digest for a reader who
already received a digest on each of the previous days. Your job is to avoid boring them
with stories they have already read.

PREVIOUSLY SENT STORIES (date, headline, summary):
{history_block}

TODAY'S CANDIDATE STORIES:
{cluster_list}

For each of today's stories, decide:
- "NEW"       — this story does not appear in the previously sent list at all.
- "UPDATE"    — the same ongoing story, but today's coverage contains at least one genuinely
                new fact, quote, result, date, or development beyond what was already sent.
- "DUPLICATE" — the same ongoing story with NO new information: only rewording, reaction
                pieces, or another site repeating what the reader already knows.

Critical rules:
- "UPDATE" and "DUPLICATE" require the SAME SPECIFIC SUBJECT — the same wrestler, event,
  match, lawsuit, or signing. Sharing a broad category is NOT a match. "LA Knight interview"
  and "WWE merchandise news" are both WWE corporate items but they are DIFFERENT stories, so
  the first is "NEW". If you cannot point to one specific previous story about this exact
  subject, the answer is "NEW".
- Mark "DUPLICATE" ONLY when you are confident there is no new information. When in doubt,
  choose "UPDATE". Never mark DUPLICATE based on a similar headline alone.
- A new quote from a different person, a scheduled match, an injury update, or a lawsuit
  filing all count as new information.
- For UPDATE and DUPLICATE, set "prev_headline" to the previously sent headline it matches,
  copied EXACTLY as written above.

Return ONLY valid JSON (no markdown, no explanation), one object per story index:
[
  {{"index": 0, "status": "NEW", "prev_headline": ""}},
  {{"index": 1, "status": "UPDATE", "prev_headline": "Bayley WWE Exit Speculation"}},
  {{"index": 2, "status": "DUPLICATE", "prev_headline": "Big Cass Return Vignettes"}}
]"""

    raw = _ask_claude(prompt, api_key, model, max_tokens=8192, tag="history-filter")
    if raw is None:
        print("[history-filter] Skipping dedup — keeping all stories")
        return clusters

    verdicts = _parse_json(raw, "history-filter")
    if not isinstance(verdicts, list):
        print("[history-filter] Skipping dedup — keeping all stories")
        return clusters

    # Map previous headline -> its TL;DR so the summarizer knows what the reader saw.
    # `known_headlines` also covers entries that had no TL;DR line.
    prev_tldr_by_headline: dict[str, str] = {}
    known_headlines: set[str] = set()
    current_headline = None
    for line in history_block.splitlines():
        if line.startswith("["):
            current_headline = _norm_headline(line.split("] ", 1)[-1])
            known_headlines.add(current_headline)
        elif current_headline and line.strip():
            prev_tldr_by_headline.setdefault(current_headline, line.strip())

    by_index: dict[int, dict[str, Any]] = {}
    for v in verdicts:
        if isinstance(v, dict) and isinstance(v.get("index"), int):
            by_index[v["index"]] = v

    kept: list[list[dict[str, Any]]] = []
    dropped, updates = 0, 0
    for i, cluster in enumerate(clusters):
        verdict = by_index.get(i, {})
        status = str(verdict.get("status", "NEW")).upper()
        story_title = cluster[0].get("_story_title", cluster[0]["title"])
        prev_headline = str(verdict.get("prev_headline", "") or "")
        prev_key = _norm_headline(prev_headline)

        # A drop must cite a headline we actually sent. Without this check a
        # hallucinated or paraphrased reference silently deletes real news.
        if status == "DUPLICATE" and prev_key not in known_headlines:
            print(f"[history-filter] Ignoring DUPLICATE for {story_title!r} — "
                  f"unrecognised reference {prev_headline!r}")
            status = "NEW"

        if status == "DUPLICATE":
            dropped += 1
            print(f"[history-filter] DROPPED (already sent): {story_title!r} ~ {prev_headline!r}")
            continue

        if status == "UPDATE":
            updates += 1
            cluster[0]["_is_update"] = True
            cluster[0]["_prev_tldr"] = prev_tldr_by_headline.get(prev_key, prev_headline)
            print(f"[history-filter] UPDATE: {story_title!r} ~ {prev_headline!r}")

        kept.append(cluster)

    new_count = len(kept) - updates
    print(f"[history-filter] NEW={new_count}  UPDATE={updates}  DUPLICATE(dropped)={dropped}")
    return kept
