"""The only place the model is used, and it is deliberately fenced in.

It may do two things:
  1. read the free-text manager answers and say whether any of them carry a
     health, safety, security, asset or money risk a human would want raised;
  2. tighten the wording of flags the rules already decided.

It may NOT compute, alter or introduce a number, decide a severity, or add
a flag. Every figure on the board comes from rules.py. If the API is down,
missing or slow, the run still publishes using the deterministic text: the
board is never blocked on the model.
"""
import json
import os
import re

MODEL = os.environ.get("VIVIOS_MODEL", "claude-sonnet-4-5")
MAXTOK = 1600

SYSTEM = """You help audit a restaurant's daily manager log for its owner.

Rules you must follow exactly:
- Never invent, change, or restate a number. Numbers are computed elsewhere.
- Never use an em dash or an en dash. Use commas or periods.
- Never mention yourself, any AI, any model, or any vendor. The reader is the
  restaurant owner and must only ever see plain operational writing.
- Plain, direct, warm but unsentimental. No exclamation marks. No praise padding.
- If nothing in the answers carries risk, say so and return an empty list.
Return JSON only."""

CONTENT_PROMPT = """Here are last night's free text answers from the manager log.

{answers}

Return JSON:
{{"content_flags": [{{"severity": "high"|"medium", "title": str, "detail": str,
                      "manager": str}}],
  "read": str}}

Raise a content flag only for a real operational risk: health, safety, security,
an asset at risk, repeated negligence, an unresolved complaint, an unresolved 86,
a repair need, a callout pattern, or anything with money attached. Quote briefly
and name the manager who wrote it. "read" is one sentence describing the shift as
the answers describe it."""


def _strip(s):
    if not isinstance(s, str):
        return s
    s = s.replace("—", ", ").replace("–", ", ")
    for bad in ("claude", "anthropic", "openai", "chatgpt", "gpt", "as an ai"):
        s = re.sub(bad, "", s, flags=re.I)
    return " ".join(s.split())


def content_scan(questions):
    """Return (content_flags, one_line_read). Never raises."""
    free = [q for q in questions
            if q["a"].strip() and q["a"].strip().lower() not in
            ("no", "none", "nothing", "n/a", "na", "no one answered.")]
    if not free:
        return [], ""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return [], ""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        answers = "\n".join("Q: %s\nA: %s (%s)" % (q["q"], q["a"], q["by"] or "unsigned")
                            for q in questions if q["a"].strip())
        msg = client.messages.create(
            model=MODEL, max_tokens=MAXTOK, system=SYSTEM,
            messages=[{"role": "user",
                       "content": CONTENT_PROMPT.format(answers=answers)}])
        txt = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        m = re.search(r"\{.*\}", txt, re.S)
        if not m:
            return [], ""
        data = json.loads(m.group(0))
        out = []
        for f in data.get("content_flags", [])[:6]:
            sev = f.get("severity")
            if sev not in ("high", "medium"):
                sev = "medium"
            out.append({"sev": sev, "code": "CONTENT",
                        "title": _strip(f.get("title", ""))[:200],
                        "detail": _strip(f.get("detail", ""))[:900]})
        return out, _strip(data.get("read", ""))[:300]
    except Exception as e:                       # never block the board
        print("narrate: content scan skipped (%s: %s)" % (type(e).__name__, e))
        return [], ""
