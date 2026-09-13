"""
Renders a math expression (matplotlib "mathtext" — a LaTeX-like subset
covering \\frac, \\sqrt, \\sec, \\cot, \\operatorname, super/subscripts,
Greek letters, etc.) to a transparent PNG. This is what lets equations
show up as properly typeset math instead of garbled OCR text or plain
font rendering (which can't do fractions/roots/etc. at all).

No LaTeX installation is required — matplotlib's mathtext renders this
subset natively.
"""

import io
import matplotlib
matplotlib.use("Agg")  # headless, no display needed
import matplotlib.pyplot as plt


def render_math_to_png_bytes(mathtext: str, color: str = "1B1B1B", fontsize: int = 28) -> bytes:
    """
    mathtext: a mathtext expression. Accepts it with or without the
    surrounding $...$ — added automatically if missing.
    color: hex string like "FFE234" (no '#').
    Returns PNG bytes with a transparent background.
    """
    expr = mathtext.strip()
    if not (expr.startswith("$") and expr.endswith("$")):
        expr = f"${expr}$"

    rgb = tuple(int(color[i:i+2], 16) / 255 for i in (0, 2, 4))

    fig = plt.figure(figsize=(10, 2), dpi=200)
    fig.patch.set_alpha(0.0)
    plt.axis("off")
    try:
        plt.text(0.5, 0.5, expr, ha="center", va="center", fontsize=fontsize, color=rgb)
        buf = io.BytesIO()
        plt.savefig(buf, format="png", transparent=True, bbox_inches="tight", pad_inches=0.08)
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception:
        plt.close(fig)
        raise
