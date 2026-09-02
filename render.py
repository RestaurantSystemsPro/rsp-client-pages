"""Build the standalone client page from facts, flags and carried state.

Self contained: no external CSS, JS, fonts or images, because the page is
served from GitHub Pages and must not depend on anything else.
"""
import datetime as dt
import html as H

WD = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SEV_LABEL = {"critical": "Critical", "high": "High", "medium": "Medium", "good": "Cleared"}


def m(v):
    return "$%s" % format(v, ",.2f") if isinstance(v, (int, float)) else "-"


def e(s):
    return H.escape(str(s)) if s is not None else ""


CSS = """
:root{--bg:#f4f6f8;--card:#fff;--ink:#16212b;--muted:#5d6b7a;--line:#dfe5ea;
--red:#b3261e;--redbg:#fdecea;--amber:#8a5a00;--amberbg:#fff5e0;
--green:#1f6b3a;--greenbg:#e9f6ed;--blue:#1c5b8c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,
BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:15px;
line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:20px 16px 64px}
header.top{background:#12303f;color:#fff;padding:22px 16px;margin:0 0 20px}
header.top .inner{max-width:1120px;margin:0 auto;padding:0 16px}
header.top h1{margin:0;font-size:22px}
header.top .sub{opacity:.85;font-size:13px;margin-top:4px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-bottom:18px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.tile .lbl{font-size:11px;text-transform:uppercase;letter-spacing:.7px;color:var(--muted);font-weight:600}
.tile .big{font-size:26px;font-weight:700;margin:6px 0 2px}
.tile .note{font-size:12.5px;color:var(--muted)}
.tile.red .big{color:var(--red)}.tile.green .big{color:var(--green)}.tile.amber .big{color:var(--amber)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;margin-bottom:16px;overflow:hidden}
.card>h2{margin:0;padding:12px 16px;font-size:14px;letter-spacing:.4px;text-transform:uppercase;
background:#eef2f5;border-bottom:1px solid var(--line);color:#2b3a47}
.card .body{padding:14px 16px}
.flag{border-left:4px solid var(--line);padding:10px 12px;margin-bottom:10px;border-radius:0 6px 6px 0;background:#fbfcfd}
.flag:last-child{margin-bottom:0}
.flag.high,.flag.critical{border-left-color:var(--red);background:var(--redbg)}
.flag.medium{border-left-color:var(--amber);background:var(--amberbg)}
.flag.good{border-left-color:var(--green);background:var(--greenbg)}
.flag .sev{font-size:10.5px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;
display:inline-block;padding:1px 7px;border-radius:9px;margin-right:8px;color:#fff}
.flag.high .sev,.flag.critical .sev{background:var(--red)}
.flag.medium .sev{background:var(--amber)}
.flag.good .sev{background:var(--green)}
.flag .t{font-weight:650}
.flag p{margin:6px 0 0;font-size:13.5px;color:#33424f}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{background:#f7f9fb;font-size:11.5px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.pill{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:9px}
.pill.ok{background:var(--greenbg);color:var(--green)}
.pill.flag{background:var(--redbg);color:var(--red)}
.pill.miss{background:var(--amberbg);color:var(--amber)}
.pill.na{background:#eef1f4;color:var(--muted)}
.scroll{overflow-x:auto}
.lead{background:#12303f;color:#fff;border-radius:10px;padding:16px 18px;margin-bottom:16px}
.lead .k{font-size:11px;text-transform:uppercase;letter-spacing:1px;opacity:.75;font-weight:700}
.lead h3{margin:5px 0 6px;font-size:18px}
.lead p{margin:0;font-size:13.5px;opacity:.92}
.meter{height:8px;background:#e9edf1;border-radius:5px;overflow:hidden;margin-top:5px}
.meter i{display:block;height:100%;background:var(--blue)}
.meter i.warn{background:var(--amber)}.meter i.bad{background:var(--red)}
.cad{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}
.cad .c{font-size:13px}.cad .c b{display:block}.cad .c span{color:var(--muted);font-size:12px}
footer{color:var(--muted);font-size:12px;text-align:center;padding-top:8px}
"""


def _flag_html(f):
    sev = f["sev"]
    cls = "good" if sev == "good" else sev
    return ('<div class="flag %s"><span class="sev">%s</span>'
            '<span class="t">%s</span><p>%s</p></div>'
            % (cls, SEV_LABEL.get(sev, sev), e(f["title"]), e(f["detail"])))


def carried_flags(state):
    """Flags that live in state rather than in any single dispatch."""
    out = []
    of = state["open_flags"]
    pis = of.get("price_increases", [])
    if pis:
        parts = []
        for p in pis:
            if p.get("old") and p.get("new"):
                parts.append("%s via %s, $%.2f to $%.2f, plus %.2f%%, dated %s"
                             % (p["product"], p["vendor"], p["old"], p["new"],
                                p["pct"], p["date"]))
            else:
                parts.append("%s via %s, plus %.2f%%, dated %s"
                             % (p["product"], p["vendor"], p["pct"], p["date"]))
        out.append({"sev": "high", "code": "C1open",
                    "title": "%d price increases are still open and unconfirmed." % len(pis),
                    "detail": "; ".join(parts) + "."})
    q = of.get("inventory_data_quality")
    if q:
        out.append({"sev": "medium", "code": "INV",
                    "title": "Inventory data quality, three separate patterns.",
                    "detail": "%d lines counted higher at week end than beginning plus "
                              "purchases could allow, %s, caused by invoice timing. "
                              "%d lines purchased but never counted, %s, which are the "
                              "products with no inventory location. %d lines identical "
                              "both weeks and about %d where the count unit does not match "
                              "the system unit. The first two nearly cancel, so a large "
                              "share of the week's usage dollars is offsetting bookkeeping "
                              "noise. The counting effort is not the problem; the number is "
                              "not yet trustworthy in either direction."
                              % (q["negative_usage_lines"], m(q["negative_usage_value"]),
                                 q["never_counted_lines"], m(q["never_counted_value"]),
                                 q["identical_count_lines"], q["unit_mismatch_lines"])})
    if of.get("chicken_93lb_unreconciled"):
        out.append({"sev": "medium", "code": "CHK",
                    "title": "The chicken breast 93 lb note does not reconcile.",
                    "detail": "The note says 8.35 cases on hand, 3 purchased, 1.3 ending. "
                              "The usage report for the same week shows 3.775 beginning, "
                              "3.000 purchased and 1.475 ending, about 53 lbs. Beginning "
                              "and ending counts both disagree. Settle which count is right "
                              "before the number travels further."})
    for u in state["cash"].get("unexplained_over_short", []):
        out.append({"sev": "medium", "code": "OSopen",
                    "title": "Over and short of %s on %s has never been explained."
                             % (m(u["amount"]), u["date"]),
                    "detail": "Every other gap in the series traced to an un-entered "
                              "deposit. This one has not been closed out."})
    if state["streaks"].get("bvr_waste_zero_weeks", 0) >= 2:
        out.append({"sev": "medium", "code": "WASTE",
                    "title": "Waste values printed $0.00 on every line for %d weeks running."
                             % state["streaks"]["bvr_waste_zero_weeks"],
                    "detail": "With no waste recorded and no ideal cost set, ordinary trim, "
                              "spoilage and comps have nowhere to land and get pushed into "
                              "the usage number instead."})
    ce = state["cash"].get("recurring_cash_entertainment")
    if ce:
        wk = sum(v for k, v in ce.items() if isinstance(v, (int, float)))
        out.append({"sev": "medium", "code": "CASHENT",
                    "title": "About %s a week leaves in cash for entertainment with no "
                             "receipt numbers." % m(wk),
                    "detail": "Roughly %s a year paid in cash where the payee field is a "
                              "single letter and the receipt field usually holds a date. "
                              "Not evidence of anything wrong. It is the largest recurring "
                              "cash outflow in the building with the weakest paper trail."
                              % m(wk * 52)})
    g = state.get("config_gaps", {})
    if g.get("availabilities_not_in_cadence_group"):
        out.append({"sev": "medium", "code": "CFG3",
                    "title": "Employee availabilities are still not in the cadence group.",
                    "detail": "A configuration item on the RSP side. Managers are never "
                              "flagged for it."})
    if g.get("drive_august_forecast_sheet_stale"):
        out.append({"sev": "medium", "code": "CFG4",
                    "title": "The stored August forecast sheet disagrees with what is running.",
                    "detail": "The sheet holds last year flat while the live forecast has "
                              "run last year minus 20%% since %s. The figures on this page "
                              "are the ones actually in use."
                              % state["config"]["forecast_basis_since"]})
    return out


def forecast_quality_flag(facts):
    fwd = [f for f in facts.get("forward", []) if f.get("ratio")]
    if len(fwd) < 3:
        return None
    hot = [f for f in fwd if f["ratio"] >= 1.25]
    cold = [f for f in fwd if f["ratio"] <= 0.9]
    if not hot and not cold:
        return None
    bits = []
    if hot:
        bits.append("unreachable on " + ", ".join("%s %.2fx" % (f["weekday"], f["ratio"]) for f in hot))
    if cold:
        bits.append("too soft on " + ", ".join("%s %.2fx" % (f["weekday"], f["ratio"]) for f in cold))
    return {"sev": "medium", "code": "FCQ",
            "title": "The forecast still carries last year's day mix, and the mix has moved.",
            "detail": "Against the last four real same weekdays it is " + "; ".join(bits)
                      + ". The errors cancel in the weekly total, which is why the aggregate "
                        "looks fine. Keep the period total, redistribute it on this year's "
                        "trailing day of week shares, then hand set the event days."}


def build(facts, flags, state, cleared=None, read_line=""):
    cleared = cleared or []
    all_flags = list(flags) + carried_flags(state)
    fq = forecast_quality_flag(facts)
    if fq:
        all_flags.append(fq)
    order = {"critical": 0, "high": 1, "medium": 2}
    lead = None
    fwd_flags = [f for f in all_flags if f["code"] == "FWD"]
    if fwd_flags:
        lead = fwd_flags[0]
    all_flags.sort(key=lambda f: (order.get(f["sev"], 3), f["code"] != "FWD"))
    high = sum(1 for f in all_flags if f["sev"] in ("high", "critical"))
    med = sum(1 for f in all_flags if f["sev"] == "medium")

    as_of = facts.get("as_of") or facts.get("log_date", "")
    day_name = facts.get("weekday", "")
    log_date = facts.get("log_date", "")

    p = []
    p.append("<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">")
    p.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    p.append("<title>Vivio's Warren Owner Status</title>")
    p.append("<style>%s</style>\n</head>\n<body>" % CSS)
    p.append('<header class="top"><div class="inner"><h1>Vivio\'s Warren, Owner Status</h1>'
             '<div class="sub">Updated through %s, %s. Prepared by Restaurant Systems Pro.'
             '</div></div></header><div class="wrap">' % (e(day_name), e(log_date)))

    if lead:
        p.append('<div class="lead"><div class="k">Most time sensitive, still fixable today'
                 '</div><h3>%s</h3><p>%s</p></div>' % (e(lead["title"]), e(lead["detail"])))

    # tiles
    s = facts.get("sales")
    if s:
        big, note = m(s["gross"]), ("Against a %s forecast (%.2f%%) and %s last year (%.2f%%)."
                                    % (m(s["forecast"]), s["fc_var_pct"] or 0,
                                       m(s["ly"]), s["ly_var_pct"] or 0))
        cls = "green" if (s["t4_var_pct"] or 0) > 0 else "amber"
    else:
        big, note, cls = "Pending", ("The EOD had not posted when the dispatch went out. "
                                     "No verified sales figure for %s yet." % e(day_name)), "amber"
    w = state.get("weekly", {})
    ft = facts.get("forward_totals", {})
    p.append('<div class="tiles">')
    p.append('<div class="tile %s"><div class="lbl">%s %s sales</div><div class="big">%s</div>'
             '<div class="note">%s</div></div>' % (cls, e(day_name), e(log_date), big, note))
    if w.get("prime_cost_pct"):
        p.append('<div class="tile green"><div class="lbl">Prime cost, week %s</div>'
                 '<div class="big">%.2f%%</div><div class="note">%s against a %.2f%% target, '
                 '%s over.</div></div>'
                 % (e(w.get("bvr_week", "")), w["prime_cost_pct"],
                    m(w.get("prime_cost_pct", 0) and w.get("bvr_gross", 0) * w["prime_cost_pct"] / 100),
                    w.get("prime_cost_target_pct", 0), m(w.get("prime_cost_variance", 0))))
    if ft:
        p.append('<div class="tile red"><div class="lbl">Payroll still cuttable this week</div>'
                 '<div class="big">%s</div><div class="note">Scheduled %s against %s at target '
                 'on realistic sales. Against the forecast the same days read %s under, which is '
                 'why it hides.</div></div>'
                 % (m(ft["over"]), m(ft["scheduled"]), m(ft["target"]), m(ft["reads_under_by"])))
    p.append('<div class="tile"><div class="lbl">Open flags</div><div class="big">%d</div>'
             '<div class="note">%d high, %d medium.</div></div>' % (high + med, high, med))
    p.append("</div>")

    if cleared:
        p.append('<div class="card"><h2>Cleared, worth saying out loud</h2><div class="body">')
        p.extend(_flag_html(c) for c in cleared)
        p.append("</div></div>")

    p.append('<div class="card"><h2>Open flags</h2><div class="body">')
    p.extend(_flag_html(f) for f in all_flags)
    p.append("</div></div>")

    fwd = facts.get("forward", [])
    if fwd:
        p.append('<div class="card"><h2>Forward labor, days not yet worked</h2><div class="body">'
                 '<div class="scroll"><table><thead><tr><th>Day</th><th class="num">Scheduled</th>'
                 '<th class="num">Hrs</th><th class="num">Rate</th><th class="num">Forecast</th>'
                 '<th class="num">Last 4 real</th><th class="num">Target</th>'
                 '<th class="num">Over / under</th><th>Call</th></tr></thead><tbody>')
        over_days = [f for f in fwd if f.get("delta", 0) > 0]
        first = min(over_days, key=lambda f: f["date"]) if over_days else None
        biggest = max(over_days, key=lambda f: f["delta"]) if over_days else None
        for f in fwd:
            dl = f.get("delta")
            call = "Under, leave it"
            if dl and dl > 0:
                if f is first:
                    call = "Cut first, expires soonest"
                elif f is biggest:
                    call = "Cut next, biggest"
                elif dl < 125:
                    call = "Marginal, leave it"
                else:
                    call = "Cut if the day softens"
            colour = "#b3261e" if (dl or 0) > 0 else "#1f6b3a"
            p.append('<tr><td>%s %s</td><td class="num">%s</td><td class="num">%.2f</td>'
                     '<td class="num">%s</td><td class="num">%s</td><td class="num">%s</td>'
                     '<td class="num">%s</td><td class="num" style="font-weight:700;color:%s">'
                     '%s%s</td><td>%s</td></tr>'
                     % (e(f["weekday"]), e(f["date"][5:]), m(f["pay"]), f["hours"],
                        m(f.get("rate")), m(f.get("forecast")), m(f.get("trailing4")),
                        m(f.get("target_pay")), colour, "+" if (dl or 0) > 0 else "",
                        m(dl), call))
        p.append("</tbody></table></div></div></div>")

    # cash trail
    cd = state["cash"].get("counted_deposits", [])[-6:]
    p.append('<div class="card"><h2>Cash trail</h2><div class="body"><div class="scroll">'
             '<table><thead><tr><th>Night</th><th class="num">Counted deposit</th>'
             '<th>Counted by</th><th>Reached the system</th><th>Proved out</th></tr></thead><tbody>')
    for c in cd:
        p.append("<tr><td>%s</td><td class='num'>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                 % (e(c["date"]), m(c.get("amount")), e(c.get("counted_by") or "unknown"),
                    e(c.get("reached_system") or ""), e(c.get("proved") or "pending")))
    p.append("</tbody></table></div><p style='font-size:13px;color:#5d6b7a;margin:12px 0 0'>"
             "Expected deposit on any day equals Total Cash minus Proof before a deposit is "
             "entered. Use it to check a counted figure the moment it is reported.</p>"
             "</div></div>")

    # cadence
    p.append('<div class="card"><h2>Cadence</h2><div class="body"><div class="cad">')
    ref = dt.date.fromisoformat(as_of) if as_of else dt.date.today()
    import re as _re
    for name, c in state["cadence"].items():
        mm = _re.search(r"(\d+)d$", name)
        span = int(mm.group(1)) if mm else (31 if "monthly" in name else None)
        if not span:
            continue
        start = dt.date.fromisoformat(c.get("last_yes") or c["cycle_start"])
        elapsed = (ref - start).days
        pct = min(100, round(elapsed / span * 100))
        cls2 = "bad" if pct >= 100 else ("warn" if pct >= 75 else "")
        p.append("<div class='c'><b>%s</b><span>%d day cycle, day %d of %d</span>"
                 "<div class='meter'><i class='%s' style='width:%d%%'></i></div></div>"
                 % (e(name.rsplit("_", 1)[0].replace("_", " ").title()), span,
                    elapsed, span, cls2, pct))
    p.append("</div></div></div>")

    p.append("<footer>Restaurant Systems Pro, owner exception reporting for Vivio's Warren. "
             "Figures computed from the daily dispatch and the trailing sales history.</footer>")
    p.append("</div>\n</body>\n</html>\n")
    return "\n".join(p)
