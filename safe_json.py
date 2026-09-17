r"""
Robust JSON parsing for AI responses that may contain LaTeX/mathtext.

Problem: when Gemini's response includes a math expression like
$\sqrt{\frac{a}{b}}$ inside a JSON string value, the raw backslashes
(\s, \f, \{, etc.) are NOT valid JSON escape sequences — only
\" \\ \/ \b \f \n \r \t \uXXXX are. This makes json.loads() fail with
"Invalid \escape", even though the JSON is otherwise well-formed.

Fix: before parsing, double any backslash that isn't already part of
a valid JSON escape sequence, so \sqrt becomes \\sqrt (a literal
backslash followed by 's', 'q', etc. — valid JSON, and decodes back to
exactly the original \sqrt string).
"""

import json
import re

_VALID_ESCAPES = set('"\\/bfnrtu')


def _fix_invalid_escapes(text: str) -> str:
    def replace(match):
        char_after_backslash = match.group(1)
        if char_after_backslash in _VALID_ESCAPES:
            return match.group(0)  # already valid, leave as-is
        return "\\\\" + char_after_backslash  # double the backslash

    return re.sub(r'\\(.)', replace, text)


def loads(text: str):
    """Same as json.loads, but repairs invalid-escape LaTeX content first."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(_fix_invalid_escapes(text))
