"""Entry point for the daily workflow.

Fetch yesterday's dispatch, evaluate the rules, build the page, save state.
Exits non-zero only on a real failure, so a quiet day is still a green run.
"""
import datetime as dt
import json
import os
import sys
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch_mail, narrate, parse, paths, render, rules, verify   # noqa: E402

STATE = paths.find_file("state.json")
LY = paths.find_file("ly_sales.json")


def summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)


def output(k, v):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s=%s\n" % (k, v))


def main():
    state = json.load(open(STATE))
    ly = json.load(open(LY))
    tz = zoneinfo.ZoneInfo(state["config"]["timezone"])
    now = dt.datetime.now(tz)
    forced = (os.environ.get("FORCE_RUN", "").lower() == "true"
              or bool(os.environ.get("LOG_DATE")))
    if not forced and now.hour != 7:
        summary("Local time in Warren is %s, not 7 AM. This is the other daylight "
                "saving cron entry; the run that matters fires an hour from now."
                % now.strftime("%H:%M"))
        return 0

    log_date = os.environ.get("LOG_DATE") or (now.date() - dt.timedelta(days=1)).isoformat()
    ROOT = paths.repo_root(state["config"]["slug"])
    out_path = os.path.join(ROOT, state["config"]["slug"], "index.html")
    output("log_date", log_date)
    summary("## Vivio's board, log date %s (run %s local)" % (log_date, now.strftime("%Y-%m-%d %H:%M")))

    addr = (os.environ.get("GMAIL_ADDRESS")
            or state["config"].get("mail_user") or "").strip()
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    if not pw:
        summary("FAILED: GMAIL_APP_PASSWORD is not set. Add it under Settings, "
                "Secrets and variables, Actions, as a repository SECRET.")
        return 2
    if not addr:
        summary("FAILED: no mailbox address. Any one of these works, in order of "
                "preference:\n"
                "  - a repository secret or variable named GMAIL_ADDRESS\n"
                "  - a repository secret or variable named MAIL_USER\n"
                "  - a \"mail_user\" value in tools/vivios/data/state.json, which is "
                "committed to a PUBLIC repo, so only use that if you are content "
                "for the address to be visible")
        return 2

    html, meta = fetch_mail.fetch(addr, pw, log_date)
    if html is None:
        summary("No dispatch found for %s (%s). Rule A1 would be critical; leaving the "
                "published page untouched rather than replacing it with an empty one."
                % (log_date, meta.get("error")))
        return 0
    summary("Dispatch: %s, %s, %d bytes" % (meta["subject"], meta["date"], meta["size"]))

    p = parse.parse(html)
    if p["log_date"] != log_date:
        summary("FAILED: dispatch title says %s, expected %s." % (p["log_date"], log_date))
        return 2

    # Backfill. The dispatch reliably beats the Toast EOD, so yesterday
    # usually posts zeros. Every run looks back over the recent days that
    # still have no verified gross and re-reads them: by now a re-dispatch
    # has normally landed and the figure is there. The board self heals
    # instead of leaving a permanent hole.
    filled = []
    for back in range(2, 8):
        d0 = (dt.date.fromisoformat(log_date) - dt.timedelta(days=back - 1)).isoformat()
        if d0 in state["actuals_gross"] or d0 < state["seeded"]:
            continue
        h2, m2 = fetch_mail.fetch(addr, pw, d0, days_back=back + 3)
        if h2 is None:
            continue
        p2 = parse.parse(h2)
        g2 = (p2.get("eod") or {}).get("gross")
        if g2:
            state["actuals_gross"][d0] = g2
            filled.append("%s %s" % (d0, render.m(g2)))
    if filled:
        summary("Backfilled sales that posted after their dispatch: " + ", ".join(filled))

    flags, facts, state = rules.evaluate(p, state, ly, today=now.date().isoformat())

    content, read_line = narrate.content_scan(p["questions"])
    flags.extend(content)
    summary("Content scan: %d flag(s)%s" % (len(content), (". " + read_line) if read_line else ""))

    cleared = []
    if facts.get("questions_answered", 0) >= facts.get("questions_total", 9):
        who = ", ".join(facts.get("answered_by") or []) or "the closing manager"
        cleared.append({"sev": "good",
                        "title": "The manager log was answered in full.",
                        "detail": "All %d questions answered by %s.%s"
                                  % (facts["questions_total"], who,
                                     (" " + read_line) if read_line else "")})
    if facts.get("deposit") and facts.get("deposit_by"):
        cleared.append({"sev": "good",
                        "title": "The closer counted the deposit and entered it: %s."
                                 % render.m(facts["deposit"]),
                        "detail": "Counted by %s and entered in the log the same night, "
                                  "rather than reaching the system second hand. That is the "
                                  "control the log was built to produce."
                                  % facts["deposit_by"]})

    page = render.build(facts, flags, state, cleared=cleared, read_line=read_line)
    problems = verify.check(page)
    if problems:
        summary("FAILED verification, page not written:")
        for x in problems:
            summary("  - " + x)
        return 2

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)
    state["flag_count_history"].append(
        {"date": now.date().isoformat(), "high": facts["flag_counts"]["high"],
         "medium": facts["flag_counts"]["medium"]})
    state["flag_count_history"] = state["flag_count_history"][-30:]
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=False)

    summary("Wrote %s (%d bytes). Flags from this dispatch: %d high, %d medium."
            % (os.path.relpath(out_path, ROOT), len(page),
               facts["flag_counts"]["high"], facts["flag_counts"]["medium"]))
    for f in flags:
        if f["sev"] in ("critical", "high"):
            summary("- %s %s" % (f["sev"].upper(), f["title"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
