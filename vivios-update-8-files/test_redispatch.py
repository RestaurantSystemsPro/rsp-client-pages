"""Second acceptance test: the 09-02 re-dispatch with a full EOD.

Also proves re-running the same day twice leaves state unchanged, because
re-dispatch followed by a fresh run is now the normal daily pattern.
"""
import copy, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import parse, paths, rules

state = json.load(open(paths.find_file("state.json")))
ly = json.load(open(paths.find_file("ly_sales.json")))
fx = paths.find_file("fixture_2026-09-02_redispatch.html", extra=(HERE,))
p = parse.parse(open(fx).read())
ok = True
def check(label, got, want, tol=0.011):
    global ok
    good = (abs(got - want) <= tol) if isinstance(want, float) else (got == want)
    ok = ok and good
    print(("  PASS " if good else "  FAIL ") + label + ": got %r, want %r" % (got, want))

s1 = copy.deepcopy(state)
flags, facts, s1 = rules.evaluate(p, s1, ly, today="2026-09-03")
codes = [f["code"] for f in flags]

print("Cash, the point of the re-dispatch")
check("gross posted", facts["gross"], 4946.63)
check("not an early dispatch", facts["early_dispatch"], False)
check("expected deposit = total cash - proof", facts["expected_deposit"], 850.66)
check("over/short read correctly", facts["over_short"], -850.66)
check("B1 fires", "B1" in codes, True)
check("B1 names the un-entered deposit", any("no count and no entry" in f["title"] for f in flags), True)
check("V1 fires", "V1" in codes, True)
check("A2 fires, log blank", "A2" in codes, True)
check("tenders sum to proof", round(sum(facts["tenders"].values()), 2), 5238.54)
check("un-entered series now 6 long", len(s1["cash"]["unentered_deposit_series"]), 6)

print("Sales")
sl = facts["sales"]
check("forecast", sl["forecast"], 2520.79)
check("LY same day 09-03-2025", sl["ly"], 3150.99)
check("beat forecast by 96%", round(sl["fc_var_pct"], 1), 96.2)
check("beat LY by 57%", round(sl["ly_var_pct"], 1), 57.0)
check("no sales miss", "SALES" in codes, False)

print("Labor")
ly_ = facts["labor_yesterday"]
check("hours over schedule", ly_["hours_vs_schedule"], 6.7)
check("LC%", ly_["lc_pct"], 23.16)
check("D4 does not fire (0.23 pts)", "D4" in codes, False)
check("forward days are Thu-Sun", [f["weekday"] for f in facts["forward"]], ["Thursday","Friday","Saturday","Sunday"])
check("Sunday schedule moved to 907.42", [f["pay"] for f in facts["forward"] if f["weekday"]=="Sunday"][0], 907.42)

print("Invoices, prices, products, orders")
check("C2 clears, invoices present", "C2" in codes, False)
check("invoice run reset", s1["streaks"]["invoice_log_empty_run"], [])
c1 = [f for f in flags if f["code"] == "C1"]
check("two C1 increases", sorted(f["title"] for f in c1),
      sorted(["Price increase over 5%: Onions, Green, Fresh.", "Price increase over 5%: Salad Blend, Romaine & Iceberg, 55/45 Tiny Chop, Fresh Cut."]))
check("steep decreases grouped into one note", sum(1 for f in flags if f["code"] == "C1d"), 1)
check("B2 suppressed when B1 explains the gap", "B2" in codes, False)
check("new products: 11 baseline + 11 seen = 22", s1["open_flags"]["new_products_no_location"], 22)
check("PO back-confirmation fires", "C3b" in codes, True)

print("Idempotency: run the same dispatch again on the resulting state")
s2 = copy.deepcopy(s1)
flags2, facts2, s2 = rules.evaluate(p, s2, ly, today="2026-09-03")
check("new products unchanged", s2["open_flags"]["new_products_no_location"], 22)
check("un-entered series unchanged", len(s2["cash"]["unentered_deposit_series"]), 6)
check("price increases not duplicated", len(s2["open_flags"]["price_increases"]), len(s1["open_flags"]["price_increases"]))
check("early dispatch days unchanged", s2["streaks"]["early_dispatch_days"], s1["streaks"]["early_dispatch_days"])
check("same codes minus the two C1s, which are now carried in state",
      [f["code"] for f in flags2], [c for c in codes if c != "C1"])

print("\nCodes:", codes)
print("ACCEPTANCE PASSED" if ok else "ACCEPTANCE FAILED")
sys.exit(0 if ok else 1)
