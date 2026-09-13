"""
"Tuition mode" — rewrites OCR'd/pasted question text following Samiu's
Tuition's exact rules (as given by the user):

  1. Retype questions in new wording — never paste OCR text verbatim.
  2. Only questions, never answers.
  3. Lightly vary numbers/values, but never alter constants, atomic
     masses, or balanced chemical equations.
  4. No diagrams unless they can be drawn 100% accurately — prefer
     clean text-based slides.
  5. (handled by renderer.py) watermark "Samiu's Tuition" on every page.
  6. (handled by app.py) WhatsApp number on the title page.
  7. Keep board/university references (e.g. [DU 18-19]) intact.
  8. Keep any notes/formula/rule sections from the source if they help
     students solve the problem.

This requires a real AI call (semantic rewriting is not something a
rule-based engine can do). Needs GEMINI_API_KEY configured.
"""

import os
import json
import re

TUITION_SYSTEM_PROMPT = """You are rewriting exam/practice questions for a tutor named Samiu, for his tuition center "Samiu's Tuition". You will be given raw OCR'd or pasted text containing one or more questions (possibly with notes/formulas). Follow these rules exactly:

1. Retype every question in new wording — do not copy the original phrasing verbatim. This should read as a genuinely different sentence with the same meaning and difficulty. EXCEPTION: any text wrapped in single dollar signs like $\\frac{a}{b}$ is a math equation (matplotlib mathtext) — copy it through byte-for-byte, never reword, rewrite, or alter it in any way, even if it looks like it contains a "value" you'd normally vary.
2. Include ONLY the questions. Strip out any answers, solutions, or worked steps if present in the source.
3. Lightly vary numeric values in the PLAIN TEXT of the question (e.g. 25 degrees C becomes 22 degrees C, 100 mL becomes 110 mL) so it isn't identical to the original. NEVER alter universal constants, atomic masses, balanced chemical equations, or anything inside a $...$ math expression — those must stay exactly as given.
4. Do not invent or describe diagrams. If the source relies on a diagram you cannot reproduce with 100% accuracy, describe the setup in clear text instead.
5. If the source includes a notes/formula/rule section (not itself a question) that would help a student solve the problems, keep it, reworded, as its own slide (put it in the "question" field like the others).
6. If a question includes a board/university reference like [DU 18-19] or [BUET'22-23], put that reference in a separate "tag" field, not inside the question text. If there's no reference, use an empty string for "tag".

Return ONLY valid JSON, no other text, in this exact shape:
{"topic_label": "a short Bangla/English label for this topic, e.g. 'ম্যাট্রিক্স'", "slides": [{"question": "the reworded question text", "tag": "[DU 18-19]" or ""}]}

Each distinct question or notes-section becomes one slide."""


def rewrite_for_tuition(raw_text: str):
    """
    Returns (topic_label: str, slides: list of {"question": str, "tag": str}),
    rewritten per the tuition rules above, using Google's Gemini API
    (free-tier friendly). Raises RuntimeError if no API key is
    configured or the call fails, so the caller can show a clear
    message rather than silently falling back to unrewritten text
    (a silent fallback would violate rule 1/2 unnoticed).
    """
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError(
            "Tuition mode needs a GEMINI_API_KEY configured on the server "
            "to do the AI rewriting — ask whoever manages the deployment to "
            "add it under Environment variables. Get a free key at "
            "aistudio.google.com/apikey."
        )

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=raw_text,
        config=types.GenerateContentConfig(
            system_instruction=TUITION_SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )
    text = resp.text.strip()
    text = re.sub(r"^```json|```$", "", text).strip()
    data = json.loads(text)
    return data.get("topic_label", ""), data.get("slides", [])
