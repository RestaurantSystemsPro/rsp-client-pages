"""Deterministic exception rules for the Vivio's Warren owner board.

Every money figure on the board is computed here, in plain Python, so the
same inputs always produce the same numbers. The model is never asked to
do arithmetic; see narrate.py for the only thing it is allowed to do.
"""
import datetime as dt
import re

WEEKDAY = ["Monday", "Tuesday", "Wednesday", "Thursday",
           "Friday", "Saturday", "Sunday"]
NO_ANSWER = {"", "no one answered.", "no one answered", "n/a", "na", "none given"}
RECEIPT_IS_DATE = re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$")


def d(s):
    return dt.date.fromisoformat(s)


def flag(sev, code, title, detail):
    return {"sev": sev, "code": code, "title": title, "detail": detail}


def _answered(q):
    return q["a"].strip().lower() not in NO_ANSWER


def _rl(p, row, day):
    v = p["reverse_labor"].get(row, {}).get(day)
    return v


def trailing_same_weekday(target, ly_sales, actuals, window=4):
    """Mean of the last `window` same weekday actuals strictly before target.

    Reads this year's own history first, falling back to the frozen sheet,
    which also carries this year's days through 2026-08-18.
    """
    vals, cur = [], target - dt.timedelta(days=7)
    while len(vals) < window and cur > target - dt.timedelta(days=90):
        k = cur.isoformat()
        v = actuals.get(k, ly_sales.get(k))
        if v is not None and v >= 1000:
            vals.append(v)
        cur -= dt.timedelta(days=7)
    return (sum(vals) / len(vals)) if len(vals) == window else None


def ly_same_day(target, ly_sales):
    v = ly_sales.get((target - dt.timedelta(days=364)).isoformat())
    return v if (v is not None and v >= 1000) else None


def evaluate(p, state, ly_sales, today=None):
    """Return (flags, facts, state) for one parsed dispatch."""
    cfg = state["config"]
    tgt = cfg["labor_target_pct"] / 100.0
    actuals = dict(state["actuals_gross"])
    flags, facts = [], {}

    if p is None or not p.get("log_date"):
        return ([flag("critical", "A1", "No manager log for yesterday.",
                      "No dispatch carrying yesterday's date was found in the mailbox.")],
                facts, state)

    day = d(p["log_date"])
    ref = d(today) if isinstance(today, str) else (today or day + dt.timedelta(days=1))
    facts["log_date"] = p["log_date"]
    facts["as_of"] = ref.isoformat()
    facts["weekday"] = WEEKDAY[day.weekday()]
    week_mon = day - dt.timedelta(days=day.weekday())
    facts["week_start"] = week_mon.isoformat()

    # ---- early dispatch signature -------------------------------------
    eod = p.get("eod") or {}
    gross = eod.get("gross")
    rl_actual = _rl(p, "actual daily sales / lc %", facts["weekday"])
    rl_actual_v = rl_actual[0] if isinstance(rl_actual, tuple) else rl_actual
    early = (gross in (None, 0.0)) and (rl_actual_v in (None, 0.0))
    facts["early_dispatch"] = early
    if early:
        if p["log_date"] not in state["streaks"]["early_dispatch_days"]:
            state["streaks"]["early_dispatch_days"].append(p["log_date"])
        flags.append(flag(
            "medium", "A3",
            "Early dispatch number %d: the EOD had not posted." % len(state["streaks"]["early_dispatch_days"]),
            "Gross, net and reverse labor actual sales all read 0.00 for %s, and no "
            "re-dispatch of the %s log exists yet. Any printed over or short is an "
            "artifact of paid outs sitting against $0.00 posted gross, not a real "
            "discrepancy. Re-dispatching the log is what fixes this; re-running the "
            "audit against the same log does not."
            % (facts["weekday"], p["log_date"])))
    elif gross:
        actuals[p["log_date"]] = gross
        facts["gross"] = gross
        facts["net"] = eod.get("net")

    if not p.get("reverse_labor"):
        flags.append(flag("high", "A4", "Reverse Labor Report missing from the dispatch.",
                          "The labor section did not render, so no labor rule can be evaluated."))

    # ---- A2 manager log ------------------------------------------------
    qs = [q for q in p["questions"] if "notes from rsp" not in q["q"].lower()]
    answered = [q for q in qs if _answered(q)]
    rsp_side = [q for q in answered if q["by"] and "britney" in q["by"].lower()]
    facts["questions_total"] = len(qs)
    facts["questions_answered"] = len(answered)
    facts["answered_by"] = sorted({q["by"] for q in answered if q["by"]})
    blank = state["streaks"]["blank_manager_log"]

    if len(answered) == 0 or len(rsp_side) == len(qs):
        why = ("closed out by an RSP staff account rather than by anyone in the building, "
               "which is worse than blank because it removes the gap that made the miss "
               "visible" if rsp_side else "left blank")
        facts["log_blank"] = True
        flags.append(flag("high", "A2",
                          "Manager log not answered on site for %s." % p["log_date"],
                          "All %d questions were %s. Held as MISSING until the next "
                          "dispatch, which either carries an after midnight closer's "
                          "answers or converts this to a confirmed miss." % (len(qs), why)))
    elif len(answered) < len(qs) / 2:
        facts["log_blank"] = True
        flags.append(flag("high", "A2", "Over half the manager log went unanswered.",
                          "%d of %d questions answered." % (len(answered), len(qs))))
    else:
        facts["log_blank"] = False
        if blank.get("pending") and blank["pending"] != p["log_date"]:
            # the pending day's rollover window has now closed
            pend = blank.pop("pending")
            if pend not in blank["confirmed_days"]:
                blank["confirmed_days"].append(pend)
                flags.append(flag("high", "A2",
                                  "%s is now a confirmed manager log miss." % pend,
                                  "Its rollover window closed when this dispatch arrived "
                                  "carrying its own day's answers and nothing for %s." % pend))
        blank["broken_on"] = p["log_date"]

    if facts.get("log_blank") and p["log_date"] not in blank["confirmed_days"]:
        blank["pending"] = p["log_date"]

    # ---- cash ----------------------------------------------------------
    def qa(needle):
        for q in qs:
            if needle in q["q"].lower():
                return q
        return None

    dep_q = qa("actual cash deposit amount")
    bank_q = qa("taken to the bank")
    dep_amt, dep_by = None, None
    if dep_q and _answered(dep_q):
        m = re.search(r"[\d,]+(?:\.\d+)?", dep_q["a"])
        if m:
            dep_amt = float(m.group(0).replace(",", ""))
            dep_by = dep_q["by"]
    facts["deposit"] = dep_amt
    facts["deposit_by"] = dep_by

    if dep_amt is None:
        flags.append(flag("high", "V1", "No counted cash deposit for the day.",
                          "The deposit question was unanswered or non numeric on an open "
                          "day. An EOD that reconciles with no counted number is circular, "
                          "not proof."))
    else:
        cds = [c for c in state["cash"]["counted_deposits"] if c["date"] != p["log_date"]]
        cds.append({"date": p["log_date"], "amount": dep_amt,
                    "counted_by": dep_by, "reached_system": "log",
                    "proved": "pending EOD" if early else None})
        state["cash"]["counted_deposits"] = cds

    if bank_q and _answered(bank_q) and bank_q["a"].strip().lower().startswith("no"):
        flags.append(flag("medium", "V2", "The deposit was not banked that day.",
                          "Answered No to the same day banking question. Counting it is "
                          "the hard part and that is being done; banking it same day and "
                          "by itself is the remaining half of the control."))

    cash = p.get("cash") or {}
    tc, proof = cash.get("total_cash"), cash.get("proof")
    if not early and tc is not None and proof is not None:
        expected = round(tc - proof, 2)
        facts["expected_deposit"] = expected
        os_ = round(proof - tc, 2)
        facts["over_short"] = os_
        facts["tenders"] = p.get("tenders") or {}
        facts["mix"] = (p.get("eod") or {}).get("mix") or {}
        if abs(os_) > cfg["over_short_tolerance"]:
            if dep_amt is None and abs(abs(os_) - expected) < 0.01:
                # no deposit entered at all: the printed gap IS the deposit
                ser = state["cash"].setdefault("unentered_deposit_series", [])
                dated = state["cash"].setdefault("unentered_deposit_dates", [])
                if p["log_date"] not in dated:
                    ser.append(expected)
                    dated.append(p["log_date"])
                flags.append(flag("high", "B1",
                                  "$%.2f in cash with no count and no entry." % expected,
                                  "Total Cash $%.2f less Proof $%.2f leaves $%.2f that should "
                                  "have been the deposit. Nothing was entered, so the EOD "
                                  "prints it as a $%.2f short. Every prior gap in this series "
                                  "turned out to be an un-entered deposit rather than missing "
                                  "cash, but this is the largest yet and it carries no paper "
                                  "trail at all: no count, no name, no banking answer. "
                                  "Entry %d in the series." % (tc, proof, expected, os_, len(ser))))
            else:
                flags.append(flag("high", "B1", "Over and short of $%.2f." % os_,
                                  "Total Cash $%.2f against Proof $%.2f. Expected deposit for a "
                                  "clean zero is $%.2f." % (tc, proof, expected)))
        if (abs(tc - proof) > cfg["over_short_tolerance"] and dep_amt is None
                and not any(f["code"] == "B1" for f in flags)):
            flags.append(flag("high", "B2", "Total Cash and Proof differ by more than $20.",
                              "$%.2f against $%.2f." % (tc, proof)))
        if dep_amt is not None:
            facts["deposit_variance"] = round(dep_amt - expected, 2)

    # ---- B4 paid outs --------------------------------------------------
    for po in p["paid_outs"]:
        if RECEIPT_IS_DATE.match((po["receipt"] or "").strip()):
            desc = ", ".join(c["description"] for c in po["categories"] if c["description"])
            flags.append(flag("medium", "B4",
                              "The paid out receipt field holds a date, not a receipt number.",
                              'Reads "%s" against $%.2f%s. Payee reads only "%s".'
                              % (po["receipt"], po["amount"],
                                 " for " + desc if desc else "", po["store"])))
    if p["paid_outs_empty"]:
        run = state["streaks"]["paid_out_empty_run"]
        if p["log_date"] not in run:
            run.append(p["log_date"])
        if facts["weekday"] in ("Friday", "Saturday") and dep_amt is None:
            flags.append(flag("high" if len(run) >= 3 else "medium", "PO",
                              "Empty paid out log on a %s with no counted deposit."
                              % facts["weekday"],
                              "This is the combination that hides cash. %d consecutive "
                              "days with no paid out recorded." % len(run)))
    else:
        state["streaks"]["paid_out_empty_run"] = []

    # ---- C2 invoices ----------------------------------------------------
    run = state["streaks"]["invoice_log_empty_run"]
    if p["invoices_empty"]:
        if p["log_date"] not in run:
            run.append(p["log_date"])
        if len(run) >= 2:
            flags.append(flag("medium", "C2",
                              "The invoice log has been empty %d days running." % len(run),
                              "%s through %s. This is the direct mechanical cause of the "
                              "negative usage lines: stock is on the shelf and counted "
                              "correctly, but the invoice recording its arrival is not in "
                              "the system yet." % (run[0], run[-1])))
    else:
        state["streaks"]["invoice_log_empty_run"] = []

    # ---- C1 price history ------------------------------------------------
    # The table always carries the prior day's rows, so accept yesterday and
    # the day before, and dedup against what state already holds.
    def _iso(sv):
        for fmt in ("%Y-%m-%d", "%m-%d-%Y"):
            try:
                return dt.datetime.strptime(sv.strip(), fmt).date().isoformat()
            except (ValueError, AttributeError):
                pass
        return None
    ok_dates = {(day - dt.timedelta(days=k)).isoformat() for k in (0, 1)}
    seen = {(f.get("date"), f.get("product")) for f in state["open_flags"]["price_increases"]}
    steep = []
    for row in p["price_history"]:
        iso = _iso(row["date"])
        if iso not in ok_dates or row["pct"] is None:
            continue
        if (iso, row["product"]) in seen:
            continue
        if row["pct"] > cfg["price_increase_pct"]:
            state["open_flags"]["price_increases"].append(
                {"date": iso, "vendor": row["vendor"], "product": row["product"],
                 "old": row["old"], "new": row["new"], "pct": round(row["pct"], 2)})
            flags.append(flag("high", "C1", "Price increase over 5%%: %s." % row["product"],
                              "%s, $%.2f to $%.2f, plus %.2f%%."
                              % (row["vendor"], row["old"], row["new"], row["pct"])))
        elif row["pct"] < cfg["price_decrease_note_pct"]:
            steep.append("%s %s $%.2f to $%.2f (%.1f%%)"
                         % (row["vendor"], row["product"][:40], row["old"], row["new"], row["pct"]))
    if steep:
        flags.append(flag("medium", "C1d",
                          "%d steep price decreases, data check only." % len(steep),
                          "Drops past 10%% are usually a unit change or a mis-key rather "
                          "than a real price move, and a wrong unit poisons the usage "
                          "report. Confirm the pack size on each: %s." % "; ".join(steep)))

    # ---- C3 orders --------------------------------------------------------
    back = [o for o in p["orders"] if o["placed_date"] and o["delivery_date"]
            and dt.datetime.strptime(o["placed_date"], "%m-%d-%Y")
            > dt.datetime.strptime(o["delivery_date"], "%m-%d-%Y")]
    if back:
        state["open_flags"]["po_back_confirmation"] = True
        flags.append(flag("high", "C3b",
                          "Purchase orders are still being created after the goods arrive.",
                          "%d orders carry a vendor Placed Date later than their delivery "
                          "date: %s. The approve before placing control cannot function "
                          "when the PO is built to match an invoice already received."
                          % (len(back), ", ".join(o["name"] for o in back))))
    for o in p["orders"]:
        if not o["placed_date"]:
            flags.append(flag("medium", "C3", "Order placed with no vendor confirmation.",
                              "%s carries no Placed Date." % o["name"]))

    # ---- new products ------------------------------------------------------
    of = state["open_flags"]
    if "new_products_seen" not in of:          # migrate from the old integer
        of["new_products_baseline"] = of.get("new_products_no_location", 0)
        of["new_products_seen"] = []
    seen_np = {(x["vendor"], x["product"]) for x in of["new_products_seen"]}
    for np_ in p["new_products"]:
        key = (np_["vendor"], np_["product"])
        if key not in seen_np:
            of["new_products_seen"].append(
                {"vendor": np_["vendor"], "product": np_["product"],
                 "date": np_["date"], "price": np_["price"]})
            seen_np.add(key)
    n = of["new_products_baseline"] + len(of["new_products_seen"])
    of["new_products_no_location"] = n
    added_today = [x for x in p["new_products"] if x["date"] in
                   ((day).isoformat(), (day - dt.timedelta(days=1)).isoformat())]
    if n:
        days_to_count = (6 - day.weekday()) % 7 or 7
        urgent = days_to_count <= 2
        recent = ""
        if added_today:
            recent = " %d arrived on this dispatch: %s." % (
                len(added_today), "; ".join("%s (%s)" % (x["product"][:48], x["vendor"])
                                            for x in added_today[:6]))
            if len(added_today) > 6:
                recent = recent[:-1] + " and %d more." % (len(added_today) - 6)
        flags.append(flag("high", "NP",
                          "%d products are still purchased with no inventory location." % n,
                          "They land in cost and are never counted back out, so the "
                          "purchase reads as consumed.%s Next end of week count is in %d "
                          "days.%s" % (recent, days_to_count,
                                       " Assign the locations before then." if urgent else "")))

    # ---- labor -------------------------------------------------------------
    sched = p["reverse_labor"].get("orginal schedule hours", {})
    hrs_pay = p["reverse_labor"].get("total hrs / total pay", {})
    fcast = p["reverse_labor"].get("forecasted sales / lc %", {})
    forward, worked = [], []
    for i, wd in enumerate(WEEKDAY):
        dd = week_mon + dt.timedelta(days=i)
        hp, sh = hrs_pay.get(wd), sched.get(wd)
        fc = fcast.get(wd)
        fc_v = fc[0] if isinstance(fc, tuple) else fc
        if not hp or sh is None:
            continue
        h, pay = hp
        scheduled_only = (h == sh)
        act = actuals.get(dd.isoformat())
        rec = {"date": dd.isoformat(), "weekday": wd, "hours": h, "pay": pay,
               "sched_hours": sh, "forecast": fc_v,
               "trailing4": trailing_same_weekday(dd, ly_sales, actuals),
               "ly": ly_same_day(dd, ly_sales), "actual": act,
               "scheduled_only": scheduled_only}
        if rec["trailing4"]:
            rec["target_pay"] = round(rec["trailing4"] * tgt, 2)
            rec["delta"] = round(pay - rec["target_pay"], 2)
            rec["rate"] = round(pay / h, 2) if h else None
            rec["cut_hours"] = round(rec["delta"] / rec["rate"], 1) if rec.get("rate") else None
            rec["ratio"] = round(fc_v / rec["trailing4"], 3) if fc_v else None
        if dd > day and scheduled_only:
            forward.append(rec)
        elif dd <= day:
            worked.append(rec)
            if act and not scheduled_only:
                if pay == 0 or h == 0:
                    flags.append(flag("high", "D2", "Zero hours or pay on a completed day.",
                                      "%s shows %.2f hrs / $%.2f." % (wd, h, pay)))
        if fc_v == 0:
            flags.append(flag("high", "D3", "Forecast sales are 0.00 for %s." % wd,
                              "A zero forecast disables the labor allowance for that day."))

    facts["forward"] = forward
    facts["worked"] = worked
    yday = next((w for w in worked if w["date"] == day.isoformat()), None)
    if yday and not early and yday.get("actual"):
        act_lc = _rl(p, "actual daily sales / lc %", facts["weekday"])
        nec = _rl(p, "necessary daily sales / lc %", facts["weekday"])
        act_lc = act_lc[1] if isinstance(act_lc, tuple) else None
        nec_lc = nec[1] if isinstance(nec, tuple) else None
        over_hrs = round(yday["hours"] - yday["sched_hours"], 2)
        facts["labor_yesterday"] = {"hours": yday["hours"], "pay": yday["pay"],
                                    "sched_hours": yday["sched_hours"],
                                    "hours_vs_schedule": over_hrs,
                                    "lc_pct": act_lc, "necessary_lc_pct": nec_lc}
        if act_lc is not None and nec_lc is not None and act_lc - nec_lc > 5.0:
            driver = ("hours: %.2f worked against %.2f scheduled" % (yday["hours"], yday["sched_hours"])
                      if over_hrs > 0 else "sales, not hours: the schedule was held")
            flags.append(flag("medium", "D4",
                              "Labor ran %.2f points above necessary." % (act_lc - nec_lc),
                              "%.2f%% against %.2f%%. Driver was %s." % (act_lc, nec_lc, driver)))
    if forward:
        over = [f for f in forward if f.get("delta", 0) > 0]
        tot_over = round(sum(f["delta"] for f in over), 2)
        sched_pay = round(sum(f["pay"] for f in forward), 2)
        tgt_pay = round(sum(f.get("target_pay", 0) for f in forward), 2)
        fc_allow = round(sum((f["forecast"] or 0) for f in forward) * tgt, 2)
        facts["forward_totals"] = {"scheduled": sched_pay, "target": tgt_pay,
                                   "over": round(sched_pay - tgt_pay, 2),
                                   "forecast_allowance": fc_allow,
                                   "reads_under_by": round(fc_allow - sched_pay, 2)}
        if over:
            over.sort(key=lambda f: f["date"])          # soonest first: it expires first
            first = over[0]
            rest = sorted([f for f in over if f is not first],
                          key=lambda f: -f["delta"])
            detail = ("Cut %s first at $%.2f, about %.1f hours at the $%.2f rate, because "
                      "that window closes at open. " % (first["weekday"], first["delta"],
                                                        first["cut_hours"], first["rate"]))
            if rest:
                detail += "Then " + ", ".join(
                    "%s $%.2f (%.1f hrs)" % (f["weekday"], f["delta"], f["cut_hours"])
                    for f in rest) + ". "
            under = [f for f in forward if f.get("delta", 0) <= 0]
            if under:
                detail += "Leave " + " and ".join(
                    "%s ($%.2f under)" % (f["weekday"], -f["delta"]) for f in under) + " alone."
            flags.append(flag("high", "FWD",
                              "Forward labor, $%.2f above target across the days still to "
                              "be worked." % round(sched_pay - tgt_pay, 2), detail))

    # ---- yesterday's sales -------------------------------------------------
    if not early and facts.get("gross"):
        g = facts["gross"]
        fc = fcast.get(facts["weekday"])
        fc_v = fc[0] if isinstance(fc, tuple) else fc
        ly = ly_same_day(day, ly_sales)
        t4 = trailing_same_weekday(day, ly_sales, actuals)
        facts["sales"] = {"gross": g, "forecast": fc_v, "ly": ly, "trailing4": t4,
                          "fc_var_pct": round((g - fc_v) / fc_v * 100, 2) if fc_v else None,
                          "ly_var_pct": round((g - ly) / ly * 100, 2) if ly else None,
                          "t4_var_pct": round((g - t4) / t4 * 100, 2) if t4 else None}
        s = facts["sales"]
        if (s["fc_var_pct"] is not None and s["fc_var_pct"] < cfg["sales_miss_forecast_pct"]
                and s["ly_var_pct"] is not None and s["ly_var_pct"] < cfg["sales_miss_ly_pct"]):
            extra = ""
            if s["t4_var_pct"] is not None and s["t4_var_pct"] > 0:
                extra = (" Read it with the day mix caveat: against the last four real %ss "
                         "the day actually BEAT by %.1f%%." % (facts["weekday"], s["t4_var_pct"]))
            flags.append(flag("medium", "SALES", "Sales miss on the rule.",
                              "$%.2f against a $%.2f forecast (%.2f%%) and $%.2f last year "
                              "(%.2f%%).%s" % (g, s["forecast"], s["fc_var_pct"], s["ly"],
                                               s["ly_var_pct"], extra)))

    # ---- duty tables / config gaps -----------------------------------------
    if p["duty_tables"].get("Daily") is None:
        flags.append(flag("medium", "CFG1",
                          "The Daily Duties table is missing from the dispatch.",
                          "Ten daily controls including paid out receipts, purchase "
                          "allotment, the $500 approval, prep sheets and preshift have no "
                          "attestation to score. RSP configuration, never a crew failure."))
    due = p["duty_tables"].get(facts["weekday"])
    if due is not None and len(due) == 0:
        flags.append(flag("medium", "CFG2",
                          "The %s Duties table dispatched with zero rows on its due day."
                          % facts["weekday"],
                          "No row existed to answer. A re-dispatch has been shown to "
                          "populate these, so the automatic send is firing before the duty "
                          "data is written. Not scored against the crew."))
    if p["duty_tables"].get("CADENCE") is not None and len(p["duty_tables"]["CADENCE"]) == 0:
        for name, c in state["cadence"].items():
            if not c.get("scored", True):
                continue
            m = re.search(r"(\d+)d$", name)
            if not m:
                continue
            span = int(m.group(1))
            start = d(c["last_yes"] or c["cycle_start"])
            elapsed = (ref - start).days
            if elapsed >= span:
                flags.append(flag("medium", "CAD",
                                  "The %d day %s cycle has closed with no Yes recorded."
                                  % (span, name.rsplit("_", 1)[0].replace("_", " ")),
                                  "Day %d of %d. The cadence table dispatches with zero "
                                  "rows, so no manager could record it. Fires as a "
                                  "configuration artifact, not a real miss."
                                  % (elapsed, span)))

    if state["open_flags"].get("usage_report_no_ideal"):
        flags.append(flag("high", "USAGE", "The usage report still cannot measure over usage.",
                          "Ideal Usage and Waste both read 0.00 on every line, so the "
                          "Variance column is just actual usage restated as a negative. "
                          "Generating Ideal Cost in MPG is the highest value open item."))

    for pi in state["open_flags"]["price_increases"]:
        pass  # carried forward and rendered as a group; see render.py

    state["actuals_gross"] = actuals
    state["last_log_date_audited"] = p["log_date"]
    high = sum(1 for f in flags if f["sev"] == "high")
    med = sum(1 for f in flags if f["sev"] == "medium")
    facts["flag_counts"] = {"high": high, "medium": med,
                            "critical": sum(1 for f in flags if f["sev"] == "critical")}
    return flags, facts, state
