"""Acceptance test: the engine must reproduce the 2026-09-02 manual audit.

Rolls state back to how it stood before the 09-01 dispatch was read, runs
the engine against the real dispatch, and asserts the conclusions.
"""
import copy, json, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import parse, paths, rules

state = json.load(open(paths.find_file("state.json")))
ly = json.load(open(paths.find_file("ly_sales.json")))

# --- rewind to the pre-09-01 position -------------------------------------
s = copy.deepcopy(state)
s["streaks"]["early_dispatch_days"] = [x for x in s["streaks"]["early_dispatch_days"] if x < "2026-09-01"]
s["streaks"]["invoice_log_empty_run"] = [x for x in s["streaks"]["invoice_log_empty_run"] if x < "2026-09-01"]
s["streaks"]["blank_manager_log"]["confirmed_days"] = [
    x for x in s["streaks"]["blank_manager_log"]["confirmed_days"] if x < "2026-08-31"]
s["streaks"]["blank_manager_log"]["pending"] = "2026-08-31"
s["streaks"]["blank_manager_log"].pop("broken_on", None)
s["cash"]["counted_deposits"] = [c for c in s["cash"]["counted_deposits"] if c["date"] < "2026-09-01"]
s["open_flags"]["price_increases"] = [p for p in s["open_flags"]["price_increases"] if p["date"] < "2026-09-01"]
s["actuals_gross"].pop("2026-09-01", None)

p = parse.parse(open(paths.find_file("fixture_2026-09-01.html", extra=(HERE,))).read())
flags, facts, s2 = rules.evaluate(p, s, ly, today="2026-09-02")

codes = [f["code"] for f in flags]
fwd = {f["weekday"]: f for f in facts["forward"]}
ok = True


def check(label, got, want, tol=0.011):
    """One cent tolerance. Rounding order across trailing means differs
    a hair between machines, and half-cent drift is not a real failure."""
    global ok
    if isinstance(want, float):
        good = got is not None and abs(got - want) <= tol
    else:
        good = got == want
    ok = ok and good
    print(("  PASS " if good else "  FAIL ") + label + ": got %r, want %r" % (got, want))


print("Manager log and cash")
check("all nine answered", facts["questions_answered"], 9)
check("answered on site", facts["answered_by"], ["Joseph Raven"])
check("A2 does not fire for 09-01 itself", facts["log_blank"], False)
check("08-31 converted to confirmed miss",
      "2026-08-31" in s2["streaks"]["blank_manager_log"]["confirmed_days"], True)
check("blank streak now 7", len(s2["streaks"]["blank_manager_log"]["confirmed_days"]), 7)
check("V1 does not fire", "V1" in codes, False)
check("deposit parsed", facts["deposit"], 734.0)
check("counted by", facts["deposit_by"], "Joseph Raven")
check("V2 fires", "V2" in codes, True)
check("B4 fires on the date in the receipt field", "B4" in codes, True)

print("Dispatch state")
check("early dispatch detected", facts["early_dispatch"], True)
check("ninth early dispatch", len(s2["streaks"]["early_dispatch_days"]), 9)
check("no fake over/short reported", "B1" in codes, False)
check("C2 fires", "C2" in codes, True)
check("invoice empty run of 5", len(s2["streaks"]["invoice_log_empty_run"]), 5)
check("no new C1", "C1" in codes, False)
check("PO back-confirmation fires", "C3b" in codes, True)
check("eleven products still unassigned", s2["open_flags"]["new_products_no_location"], 11)

print("Forward labor, the lead item")
check("Wednesday over", fwd["Wednesday"]["delta"], 183.82)
check("Wednesday cut hours", fwd["Wednesday"]["cut_hours"], 15.1)
check("Wednesday trailing-4", round(fwd["Wednesday"]["trailing4"], 2), 3113.24)
check("Thursday under", fwd["Thursday"]["delta"], -94.85)
check("Thursday forecast ratio", fwd["Thursday"]["ratio"], 2.15)
check("Friday under", fwd["Friday"]["delta"], -137.72)
check("Saturday over", fwd["Saturday"]["delta"], 118.14)
check("Sunday over", fwd["Sunday"]["delta"], 251.61)
check("Sunday trailing-4 includes 08-30", round(fwd["Sunday"]["trailing4"], 2), 3118.79)
check("Wed-Sun scheduled", facts["forward_totals"]["scheduled"], 4419.86)
check("Wed-Sun over target", facts["forward_totals"]["over"], 321.00)
check("reads under against forecast", facts["forward_totals"]["reads_under_by"], 418.33)
fwd_flag = [f for f in flags if f["code"] == "FWD"][0]
check("cut list leads with Wednesday", fwd_flag["detail"].startswith("Cut Wednesday first"), True)

print("Sales")
check("Tuesday LY", rules.ly_same_day(rules.d("2026-09-01"), ly), 2877.29)
check("no sales miss fired while pending", "SALES" in codes, False)

print("Config gaps")
check("Daily Duties absent", "CFG1" in codes, True)
check("Tuesday zero rows on due day", "CFG2" in codes, True)
check("walkthrough cadence closes", any(f["code"] == "CAD" for f in flags), True)

print("\nFlags: %d high, %d medium" % (facts["flag_counts"]["high"], facts["flag_counts"]["medium"]))
print("Codes:", codes)
print("\n" + ("ACCEPTANCE PASSED" if ok else "ACCEPTANCE FAILED"))
sys.exit(0 if ok else 1)
