"""
Shared Gemini call helper with model-name fallback.

Google periodically retires model names (e.g. gemini-2.0-flash was
retired in favor of gemini-3.6-flash). Rather than hardcoding one name
everywhere and breaking the whole app again next time this happens,
every caller goes through here and tries a short list of candidates in
order, falling through to the next one on a "model not found"-style
error.
"""

MODEL_CANDIDATES = [
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]


def generate_content(client, **kwargs):
    """
    Same call shape as client.models.generate_content(...), but tries
    each candidate model name in MODEL_CANDIDATES until one works.
    Raises the last error if all candidates fail.
    """
    last_exc = None
    for model_name in MODEL_CANDIDATES:
        try:
            return client.models.generate_content(model=model_name, **kwargs)
        except Exception as exc:
            last_exc = exc
            continue
    raise last_exc
