"""
Shared Gemini call helper with model-name fallback + rate-limit retry.

Google periodically retires model names (e.g. gemini-2.0-flash was
retired in favor of gemini-3.6-flash). Rather than hardcoding one name
everywhere and breaking the whole app again next time this happens,
every caller goes through here and tries a short list of candidates in
order, falling through to the next one on a "model not found"-style
error.

Separately: the free tier has a real per-minute rate limit. A 429
("Too Many Requests") means the model is fine — we're just sending
requests too fast — so that case gets a short wait-and-retry instead
of being treated like a dead model and immediately abandoned for the
next candidate.
"""

import time

MODEL_CANDIDATES = [
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]

RATE_LIMIT_BACKOFFS = [5, 15, 30]  # seconds, escalating


def _is_rate_limit_error(exc) -> bool:
    msg = str(exc)
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg or "Too Many Requests" in msg


def generate_content(client, **kwargs):
    """
    Same call shape as client.models.generate_content(...), but tries
    each candidate model name in MODEL_CANDIDATES until one works,
    retrying with backoff on rate-limit errors before giving up on a
    model entirely. Raises the last error if everything fails.
    """
    last_exc = None
    for model_name in MODEL_CANDIDATES:
        for attempt, backoff in enumerate([0] + RATE_LIMIT_BACKOFFS):
            if backoff:
                time.sleep(backoff)
            try:
                return client.models.generate_content(model=model_name, **kwargs)
            except Exception as exc:
                last_exc = exc
                if _is_rate_limit_error(exc):
                    continue  # worth retrying the same model after a wait
                break  # a non-rate-limit error (e.g. 404) means try the next model instead
    raise last_exc
