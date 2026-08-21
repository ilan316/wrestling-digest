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


def _is_transient(err: Exception) -> bool:
    text = str(err)
    return any(s in text for s in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "500", "INTERNAL"))


def generate(prompt: str, max_tokens: int, tag: str) -> str | None:
    """One Gemini call. Returns None on failure — every caller is expected to
    degrade gracefully rather than crash the run."""
    for attempt in range(4):
        _throttle()
        try:
            response = _client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    # 2.5-flash thinks by default and the thinking tokens come out of
                    # max_output_tokens — leaving it on returns a 200 with empty text.
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
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
            if not _is_transient(e) or attempt == 3:
                print(f"[{tag}] Gemini API error: {e}")
                return None
            wait = _retry_after(e) or 20 * (2 ** attempt)
            print(f"[{tag}] Gemini unavailable (attempt {attempt+1}/4), retrying in {wait:.0f}s...")
            time.sleep(wait)
    return None
