import copy, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import parse, rules, render, verify

state = json.load(open(os.path.join(ROOT, "data/state.json")))
ly = json.load(open(os.path.join(ROOT, "data/ly_sales.json")))
s = copy.deepcopy(state)
s["streaks"]["early_dispatch_days"] = [x for x in s["streaks"]["early_dispatch_days"] if x < "2026-09-01"]
s["streaks"]["invoice_log_empty_run"] = [x for x in s["streaks"]["invoice_log_empty_run"] if x < "2026-09-01"]
s["streaks"]["blank_manager_log"]["confirmed_days"] = [x for x in s["streaks"]["blank_manager_log"]["confirmed_days"] if x < "2026-08-31"]
s["streaks"]["blank_manager_log"]["pending"] = "2026-08-31"
s["cash"]["counted_deposits"] = [c for c in s["cash"]["counted_deposits"] if c["date"] < "2026-09-01"]
s["open_flags"]["price_increases"] = [p for p in s["open_flags"]["price_increases"] if p["date"] < "2026-09-01"]
s["actuals_gross"].pop("2026-09-01", None)

p = parse.parse(open(os.path.join(HERE, "fixture_2026-09-01.html")).read())
flags, facts, s2 = rules.evaluate(p, s, ly, today="2026-09-02")
cleared = [
 {"sev":"good","title":"The manager log was answered in full.","detail":"All 9 questions answered by Joseph Raven."},
 {"sev":"good","title":"The closer counted the deposit and entered it: $734.00.","detail":"Counted by Joseph Raven and entered in the log the same night."}]
page = render.build(facts, flags, s2, cleared=cleared)
probs = verify.check(page)
open(os.path.join(HERE, "out.html"), "w").write(page)
print("page bytes:", len(page))
print("verify problems:", probs or "none")
import re
print("high cards:", len(re.findall(r'class="flag high"', page)),
      "| medium cards:", len(re.findall(r'class="flag medium"', page)),
      "| cleared cards:", len(re.findall(r'class="flag good"', page)))
print("lead:", re.search(r'<h3>(.*?)</h3>', page).group(1)[:110])
print("forward rows:", len(re.findall(r'Cut first, expires soonest|Cut next, biggest|Under, leave it|Marginal, leave it', page)))
sys.exit(0 if not probs else 1)
