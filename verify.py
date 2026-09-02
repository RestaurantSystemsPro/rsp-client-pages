"""Guards that fail the build rather than letting a bad page reach the client.

The branding rule is not a thing a person should have to remember, so it is
enforced here: nothing model-branded and no dashes Fred does not use.
"""
import re
import sys

BANNED_STRINGS = ["claude", "anthropic", "openai", "gpt", "chatgpt", "llm",
                  "as an ai", "language model"]
BANNED_CHARS = ["—", "–"]          # em dash, en dash


def check(html):
    problems = []
    low = html.lower()
    for s in BANNED_STRINGS:
        if s in low:
            i = low.index(s)
            problems.append("banned string %r near: %s"
                            % (s, html[max(0, i - 60):i + 60].replace("\n", " ")))
    for c in BANNED_CHARS:
        if c in html:
            i = html.index(c)
            problems.append("banned character %r near: %s"
                            % (c, html[max(0, i - 60):i + 60].replace("\n", " ")))
    if "<!DOCTYPE html>" not in html[:200]:
        problems.append("missing doctype: the page must be a complete document")
    if not re.search(r"<title>.+</title>", html):
        problems.append("missing title")
    if len(html) < 5000:
        problems.append("page is suspiciously small (%d bytes)" % len(html))
    return problems


if __name__ == "__main__":
    path = sys.argv[1]
    probs = check(open(path, encoding="utf-8").read())
    if probs:
        print("VERIFY FAILED for %s" % path)
        for p in probs:
            print("  -", p)
        sys.exit(1)
    print("VERIFY PASSED for %s" % path)
