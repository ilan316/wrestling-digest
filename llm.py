"""Single LLM entry point — Google Gemini (free tier).

Everything that talks to a model goes through `generate()`. Two reasons this is
one module rather than a call in each caller:

1. The free tier is rate-limited per *project*, not per call site. The summarizer
   fans out over a thread pool, so the limiter has to be module-level shared
   state or the pool blows straight through the quota.
2. The retry/backoff logic used to be duplicated in clusterer.py and
   summarizer.py with subtly different behaviour. Now there is one copy.
"""
from __future__ import annotations

import re
import threading
import time

from google import genai
from google.genai import types

import config

_client = genai.Client(api_key=config.GEMINI_API_KEY)

# Free tier is ~10 requests/minute. Simple leaky bucket: every call waits until
# at least `_MIN_INTERVAL` has passed since the previous one started. Coarser
# than a token bucket (no burst allowance) but that is the point — a burst is
# exactly what earns a 429 here.
_MIN_INTERVAL = 60.0 / max(config.GEMINI_RPM, 1)
_rate_lock = threading.Lock()
_last_call = 0.0

# The strong model's ceiling is 20 requests per *day*, and the free tier resets at
# midnight Pacific — i.e. ~07:00 UTC, *after* the 04:43/05:43 UTC scheduled run.
# So a manual test in the evening spends budget the next morning's digest needs.
# On 2026-08-22 the scheduled run opened on an already-exhausted quota and only got
# through on a retry. Flipping this off makes a manual run physically unable to
# touch that budget.
_heavy_enabled = True

# 503 UNAVAILABLE ("high demand") is Google-side transient load, unrelated to our
# own PerMinute/PerDay quotas. On 2026-09-02 a sustained wave of these cost one
# summary its LLM pass (fell back to raw excerpt) after exhausting 4 attempts
# (~140s of backoff). Widened to 6 attempts (~10min of backoff) to outlast a
# longer outage window.
_MAX_ATTEMPTS = 6


def disable_heavy_model(reason: str) -> None:
    global _heavy_enabled
    _heavy_enabled = False
    print(f"[llm] Strong model ({config.GEMINI_MODEL_HEAVY}) disabled — {reason}")


def _throttle() -> None:
    global _last_call
    with _rate_lock:
        wait = _last_call + _MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def _retry_after(err: Exception) -> float | None:
    """Gemini puts a `retry_delay { seconds: N }` block in quota errors. Honour it
    when present — it is the server telling us exactly when the window reopens."""
    m = re.search(r"retry_delay[^}]*?seconds:\s*(\d+)", str(err))
    return float(m.group(1)) if m else None


def _quota_hint(err: Exception) -> str:
    """A one-line reason for the log. Quota 429s carry a `quotaId` naming which
    ceiling was hit — PerMinute is survivable, PerDay means the run is done."""
    text = str(err)
    ids = re.findall(r"'quotaId': '([^']+)'", text)
    if ids:
        vals = re.findall(r"'quotaValue': '([^']+)'", text)
        return ", ".join(f"{i}={v}" for i, v in zip(ids, vals or ["?"] * len(ids)))
    return text.split("\n")[0][:160]


def _is_transient(err: Exception) -> bool:
    text = str(err)
    return any(s in text for s in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "500", "INTERNAL"))


def _thinking_config(model: str) -> types.ThinkingConfig:
    """Keep thinking to a minimum — it is billed against `max_output_tokens`, and
    left on it returns a 200 with empty text.

    The knob changed names between model generations: 2.5 takes a numeric
    `thinking_budget` (0 = off), 3.x replaced it with a `thinking_level` enum and
    rejects `thinking_budget` outright with a bare 400 INVALID_ARGUMENT. 3.x has no
    "off" level, so LOW is the floor.
    """
    if model.startswith("gemini-2"):
        return types.ThinkingConfig(thinking_budget=0)
    return types.ThinkingConfig(thinking_level="LOW")


def generate(prompt: str, max_tokens: int, tag: str, heavy: bool = False) -> str | None:
    """One Gemini call. Returns None on failure — every caller is expected to
    degrade gracefully rather than crash the run.

    `heavy=True` routes to the stronger model. Reserve it for the handful of
    structural calls per run: it has a 20/day free-tier ceiling, so anything
    called once per story must leave it alone. See config.py for the numbers.
    A `disable_heavy_model()` call downgrades those requests to the lite model —
    the run still produces a digest, just with a weaker reasoner on the two
    structural steps.
    """
    model = config.GEMINI_MODEL_HEAVY if (heavy and _heavy_enabled) else config.GEMINI_MODEL
    for attempt in range(_MAX_ATTEMPTS):
        _throttle()
        try:
            response = _client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    thinking_config=_thinking_config(model),
                ),
            )
            text = (response.text or "").strip()
            if text:
                return text
            candidates = getattr(response, "candidates", None) or []
            reason = getattr(candidates[0], "finish_reason", "?") if candidates else "no-candidates"
            print(f"[{tag}] Gemini returned empty text (finish_reason={reason})")
            return None
        except Exception as e:
            if not _is_transient(e) or attempt == _MAX_ATTEMPTS - 1:
                print(f"[{tag}] Gemini API error: {e}")
                return None
            wait = _retry_after(e) or 20 * (2 ** attempt)
            # Print *why*. Without the quota id here, a daily-cap exhaustion and an
            # ordinary per-minute 429 look identical in the Actions log — which is
            # exactly how the 20/day ceiling on the strong model stayed hidden for a
            # full production run.
            print(
                f"[{tag}] Gemini unavailable on {model} (attempt {attempt+1}/{_MAX_ATTEMPTS}), "
                f"retrying in {wait:.0f}s — {_quota_hint(e)}"
            )
            time.sleep(wait)
    return None
