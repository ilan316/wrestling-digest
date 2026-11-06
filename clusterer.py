"""Group articles by news story using an LLM."""
from __future__ import annotations

import json
import re
from typing import Any

import llm


def _parse_json(raw: str, tag: str) -> Any | None:
    """Parse a JSON response, stripping the ```json fences the model often adds."""
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


def _keyword_promotion(text: str) -> str | None:
    """"AEW"/"WWE" when the text names exactly one of them, else None."""
    text = text.lower()
    aew = "aew" in text or "all elite wrestling" in text
    wwe = "wwe" in text or "nxt" in text or "wrestlemania" in text
    if aew != wwe:
        return "AEW" if aew else "WWE"
    return None


def _guess_promotion(article: dict[str, Any]) -> str:
    """Keyword fallback for when the model's grouping is unusable. Titles almost
    always name the promotion outright (AEW/WWE/NXT), so this is a cheap and
    fairly reliable stand-in for the LLM classification — better than silently
    defaulting everything to "Other".

    The title decides first: a WWE story's snippet often mentions a wrestler's
    AEW past ("former AEW star Ricky Saints"), which used to win because AEW was
    checked first over title+summary together (2026-10-01)."""
    by_title = _keyword_promotion(article.get("title", ""))
    if by_title:
        return by_title
    text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
    if "aew" in text or "all elite wrestling" in text:
        return "AEW"
    if "wwe" in text or "nxt" in text or "wrestlemania" in text:
        return "WWE"
    return "Other"


def _title_override(cluster: list[dict[str, Any]]) -> str | None:
    """The promotion the cluster's headlines unanimously name, if any. Overrides
    the model, which tends to classify by the wrestlers' past employers — the
    lite fallback put a "WWE stars to reform tag team" piece under AEW because
    all three teams had ex-AEW members (2026-10-01)."""
    named = {p for a in cluster if (p := _keyword_promotion(a.get("title", "")))}
    return named.pop() if len(named) == 1 else None


class ClusteringDeferred(Exception):
    """The model could not group today's articles and a later run can still try."""


# Words that say nothing about *which* story a headline is: function words,
# promotion/show names, and wrestling-news boilerplate ("cuts promo", "update").
_GROUP_STOP = set("""
a an the and or of to in on at for with from by as is are was were be been it its his her their he she
they them this that these after before over into out up off about vs new more set says said say
reveals reveal reportedly report reports update updates news why how what who when will would could
should can has have had not no just finally ever all one two first last next
aew wwe nxt tna njpw roh aaa cmll wrestling wrestler wrestlers pro star stars match matches show
tonight week night company dynamite collision rampage raw smackdown former current
promo cuts backstage segment comments talks discusses reacts responds shares opens addresses
""".split())


def _headline_stems(title: str) -> list[str]:
    """Distinctive words in headline order, cut to 5 chars as crude stemming
    ("declines"/"declining" -> "decli")."""
    t = title.lower().replace("’", "'").replace("'s", "")
    return [w[:5] for w in re.findall(r"[a-z0-9]+", t) if len(w) >= 3 and w not in _GROUP_STOP]


def _headline_gender(title: str) -> str | None:
    t = title.lower().replace("’", "'")
    if re.search(r"\bwomen\b", t):
        return "w"
    if re.search(r"\bmen\b", t):
        return "m"
    return None


def _headline_overlap(a: list[str], b: list[str]) -> int:
    """Shared stems, with a pair adjacent in both headlines counted once —
    "Darby Allin" or "Blood & Guts" is one shared fact, not two. Otherwise every
    pair of stories about the same wrestler merges."""
    shared = set(a) & set(b)
    joint = {p for p in set(zip(a, a[1:])) & set(zip(b, b[1:])) if p[0] in shared and p[1] in shared}
    return len(shared) - len(joint)


def _local_group(articles: list[dict[str, Any]], min_shared: int = 2) -> list[list[int]]:
    """Model-free grouping by shared headline words — the last resort when Gemini
    is down. On the 2026-11-05 headlines it took 45 solo stories to 31 with no
    false merges (Taya Valkyrie x5, RVD x3, Borden x3, men's and women's Blood &
    Guts kept apart). Coarser than the model, far better than nothing."""
    stems = [_headline_stems(a.get("title", "")) for a in articles]
    df: dict[str, int] = {}
    for s in stems:
        for w in set(s):
            df[w] = df.get(w, 0) + 1
    # A word in a fifth of all headlines that day ("blood", "guts" during a PPV)
    # is the day's theme, not a story key.
    limit = max(3, len(articles) // 5)
    stems = [[w for w in s if df[w] <= limit] for s in stems]

    clusters: list[dict[str, Any]] = []
    for i, s in enumerate(stems):
        g = _headline_gender(articles[i].get("title", ""))
        best, best_n = None, 0
        for c in clusters:
            if g and c["gender"] and g != c["gender"]:
                continue  # men's vs women's match: different stories
            n = max(_headline_overlap(s, stems[j]) for j in c["members"])
            if n > best_n:
                best, best_n = c, n
        if best is not None and best_n >= min_shared:
            best["members"].append(i)
            best["gender"] = best["gender"] or g
        else:
            clusters.append({"members": [i], "gender": g})
    return [c["members"] for c in clusters]


def group_by_story(
    articles: list[dict[str, Any]], can_defer: bool = False
) -> list[list[dict[str, Any]]]:
    """
    Use the LLM to group articles by the story they cover.
    Returns a list of clusters, each cluster is a list of article dicts.
    Articles that don't share a story with anyone else get their own cluster.

    If the model is unavailable: raises ClusteringDeferred when `can_defer`
    (a later run today will retry), otherwise groups locally by headline words.
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
   Classify by the promotion the story is ABOUT, not where the wrestlers previously worked.

Each article index must appear in exactly one group.

Critical rule: group articles ONLY when they report the SAME SPECIFIC news item — the same
announcement, match, injury, quote, or event outcome. Sharing a promotion, a show, or a
wrestler is NOT enough: "Dynamite ticket sales" and "Tony Khan comments on All Out PPV buys"
are DIFFERENT stories. When in doubt, keep an article in its own group.

Return ONLY valid JSON (no markdown, no explanation):
[
  {{"story_title": "Short descriptive title", "promotion": "AEW", "indices": [0, 3, 7]}},
  {{"story_title": "Another story", "promotion": "WWE", "indices": [1, 2]}}
]

Articles:
{article_list}"""

    # Up to two calls per run — a malformed-JSON response (not a quota/network
    # error, so llm.generate()'s own retries don't cover it — see 2026-09-01,
    # everything landed in "Other") is worth one retry before giving up on the
    # strong model. Still well inside its 20/day.
    groups = None
    for attempt in range(2):
        raw = llm.generate(prompt, max_tokens=8192, tag="clusterer", heavy=True)
        if raw is None:
            break
        groups = _parse_json(raw, "clusterer")
        if isinstance(groups, list):
            break
        groups = None
        if attempt == 0:
            print("[clusterer] Retrying once after malformed JSON")

    if groups is None:
        # On 2026-11-05 both models 503'd for ~10 minutes and the old fallback —
        # one article per cluster — sent a 45-story digest with Taya Valkyrie's
        # departure seven times. A run that can still be retried later today
        # defers instead; the last chance groups by shared headline words.
        if can_defer:
            raise ClusteringDeferred("model grouping unavailable")
        print("[clusterer] Falling back to local headline grouping (no model)")
        clusters = []
        for members in _local_group(articles):
            cluster = []
            for idx in members:
                article = dict(articles[idx])
                article["_story_title"] = articles[members[0]]["title"]
                cluster.append(article)
            promo = _title_override(cluster) or _guess_promotion(cluster[0])
            for a in cluster:
                a["promotion"] = promo
            clusters.append(cluster)
        clusters.sort(key=len, reverse=True)
        print(f"[clusterer] {len(articles)} articles -> {len(clusters)} story clusters (local)")
        return clusters

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
                article["promotion"] = promotion  # model's classification
                cluster_articles.append(article)
                assigned.add(idx)
        if cluster_articles:
            override = _title_override(cluster_articles)
            # AEW<->WWE swaps only: an "Other" story (TNA, NJPW) often names a
            # wrestler's former promotion in its headline.
            if override and promotion in ("AEW", "WWE") and override != promotion:
                print(f"[clusterer] Promotion override: {story_title!r} model={promotion} -> {override} (title)")
                for a in cluster_articles:
                    a["promotion"] = override
            clusters.append(cluster_articles)

    # Add any articles the model didn't assign to any group
    for i, article in enumerate(articles):
        if i not in assigned:
            a = dict(article)
            a["_story_title"] = article["title"]
            a["promotion"] = _guess_promotion(a)
            clusters.append([a])

    # Sort clusters: largest first
    clusters.sort(key=len, reverse=True)

    total = sum(len(c) for c in clusters)
    dropped = len(articles) - len(assigned)
    if dropped:
        print(f"[clusterer] WARNING: {dropped} articles were not assigned by the model — added as solo clusters")
    print(f"[clusterer] {len(articles)} articles -> {len(clusters)} story clusters (total mapped: {total})")
    return clusters


def _norm_headline(s: str) -> str:
    """Key for matching a cited headline back to history. The model retypes headlines
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

    raw = llm.generate(prompt, max_tokens=8192, tag="history-filter", heavy=True)
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
    dropped, updates, merged = 0, 0, 0
    # Two clusters continuing the same previous story (e.g. PAC tributes and The
    # Rock's PAC statement, 2026-09-30) would otherwise render as two separate
    # "continuation" cards — fold the later ones into the first.
    update_by_prev: dict[str, list[dict[str, Any]]] = {}
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

        if status == "UPDATE" and prev_key and prev_key in update_by_prev:
            first = update_by_prev[prev_key]
            first.extend(cluster)
            merged += 1
            print(f"[history-filter] MERGED into {first[0].get('_story_title', first[0]['title'])!r}: "
                  f"{story_title!r} ~ {prev_headline!r}")
            continue

        if status == "UPDATE":
            if prev_key:
                update_by_prev[prev_key] = cluster
            updates += 1
            cluster[0]["_is_update"] = True
            cluster[0]["_prev_tldr"] = prev_tldr_by_headline.get(prev_key, prev_headline)
            print(f"[history-filter] UPDATE: {story_title!r} ~ {prev_headline!r}")

        kept.append(cluster)

    new_count = len(kept) - updates
    print(f"[history-filter] NEW={new_count}  UPDATE={updates}  MERGED={merged}  DUPLICATE(dropped)={dropped}")
    return kept
