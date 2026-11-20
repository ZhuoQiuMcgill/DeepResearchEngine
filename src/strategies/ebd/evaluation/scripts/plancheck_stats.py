"""The numbers of the plan-level check of the reworded planner rules (plancheck.ts; no model call).

base = the baseline's briefs recorded in the final test; now = the accepted planner wording;
next = the proposed wording. All three with three researchers.

Usage: python local/ebd-heldout/plancheck_stats.py [--show s07 ...]
"""
import glob
import json
import os
import re
import statistics as st
import sys

sys.stdout.reconfigure(encoding="utf-8")
R = "local/ebd-heldout"
P = R + "/plancheck"
METHODS = ["base", "now", "next"]
NAMES = {"base": "baseline (recorded)", "now": "EBD, present wording", "next": "EBD, proposed wording"}
src = open(R + "/final_stats.py", encoding="utf8").read()
ns = {}
exec("import re\nSTOP = " + re.search(r"STOP = (\{.*?\})", src).group(1) + "\n" + re.search(r"(def is_definition.*?)\n\n\ndef sign_test", src, re.S).group(1), ns)
is_def = ns["is_definition"]
FINAL = {q["id"]: q for q in json.load(open(R + "/final-sealed-questions.json", encoding="utf8"))}


def load(kind, method):
    return [json.load(open(f, encoding="utf8")) for f in sorted(glob.glob(f"{P}/{kind}/{method}/*.json" if kind else f"{P}/{method}/*.json"))]


plans = {m: load("", m) for m in METHODS}
labels = {m: load("labels", m) for m in METHODS}
scores = {m: load("scores", m) for m in METHODS}

print("1. WHAT THE KEY QUESTIONS ASK FOR (12 questions of the final test, three researchers)")
print(f"{'':26s} plans  key questions  direct  check  definition  around  | briefs mostly direct (of 3)  | plans with a definition question")
for m in METHODS:
    rows = labels[m]
    if not rows:
        continue
    n = [len(r["keys"]) for r in rows]
    share = lambda lab: sum(sum(1 for k in r["keys"] if k["label"] == lab) for r in rows) / sum(n)
    mostly = []
    for r in rows:
        by = {}
        for k in r["keys"]:
            by.setdefault(k["id"].split(".")[0], []).append(k["label"])
        mostly.append(sum(1 for v in by.values() if sum(1 for x in v if x == "direct") * 2 >= len(v)))
    withdef = sum(1 for r in rows if any(k["label"] == "definition" for k in r["keys"]))
    print(f"{NAMES[m]:26s} {len(rows):4d}  {st.mean(n):11.1f}  {share('direct'):6.0%} {share('check'):6.0%} {share('definition'):9.0%} {share('around'):8.0%}  | {st.mean(mostly):10.2f}                   | {withdef} of {len(rows)}")

print("\n   by question: share of key questions labelled direct (base | now | next), and the test's result")
J = json.load(open(R + "/judge-final-results.json", encoding="utf8"))
res = {}
for t in FINAL:
    two = [r["verdict"]["overall"] for r in J["results"] if r["kind"] == "pair" and r["task"] == t]
    res[t] = {"ebd-one": "EBD won", "baseline": "baseline won"}.get(two[0], "undecided") if two[0] == two[1] else "undecided"
for t in sorted(FINAL):
    cells = []
    for m in METHODS:
        rows = [r for r in labels[m] if r["qid"] == t]
        tot = sum(len(r["keys"]) for r in rows)
        cells.append(f"{sum(sum(1 for k in r['keys'] if k['label'] == 'direct') for r in rows) / tot:4.0%}" if tot else "  - ")
    print(f"   {t}  {' | '.join(cells)}   {res[t]:13s} {FINAL[t]['question'][:62]}")

print("\n2. CHECKLIST ITEMS THE PLAN ASKS A RESEARCHER ABOUT (12 questions)")
for m in METHODS:
    rows = [r for r in scores[m] if r["judged"]]
    if not rows:
        continue
    alls, defs, others = [], [], []
    for r in rows:
        q = FINAL[r["qid"]]
        for i, item in enumerate(q["checklist"]):
            hit = (i + 1) in r["asked"]
            alls.append(hit)
            (defs if is_def(item, q["question"]) else others).append(hit)
    print(f"   {NAMES[m]:26s} all items {st.mean(alls):4.0%}   definition items {st.mean(defs):4.0%} ({len(defs)})   other items {st.mean(others):4.0%} ({len(others)})")

print("\n3. THE CLAIMS OF THE 12 QUESTIONS: checked or taken as given")
for t in sorted(FINAL):
    print(f"   {t} {FINAL[t]['question'][:80]}")
    for m in ["now", "next"]:
        for p in [x for x in plans[m] if x["qid"] == t]:
            cl = p["reply"]["claims"]
            print(f"        {m:4s} #{p['k']}: " + (" ".join(f"[{c['verdict']}] {c['claim']}" for c in cl) or "(no claim)")[:230])
for m in ["now", "next"]:
    fin = [p for p in plans[m] if p["qid"] in FINAL]
    withcheck = sum(1 for p in fin if any(c["verdict"] == "check" for c in p["reply"]["claims"]))
    lead = sum(1 for p in fin if any(re.match(r"^\[Q\d+\] Is it true", k) for b in p["briefs"] for k in b["keyQuestions"]))
    print(f"   {NAMES[m]}: a claim is checked in {withcheck} of {len(fin)} plans; a brief carries the check question in {lead}")

print("\n4. QUESTIONS WRITTEN WITH A FALSE OR A TRUE SPECIFIC FACT, OR NONE (premise set and planted set)")
MARK = {"n01": r"soviet", "n02": r"edison", "n03": r"1991", "n04": r"visible", "n05": r"2021", "n06": r"10\s?%|ten per", "n07": r"hyperactiv", "n08": r"three", "tel": r"2018", "d04": r"relativity", "n15": r"1912|sank|sink", "n16": r"2008|crisis", "p01": r"1989", "p02": r"fleming"}
KIND = {"n01": "false", "n02": "false", "n03": "false", "n04": "false", "n05": "false", "n06": "false", "n07": "false", "n08": "false", "tel": "false", "d04": "false", "n09": "general", "n10": "general", "n11": "general", "n12": "general", "n13": "general", "n14": "general", "n15": "true", "n16": "true", "p01": "false", "p02": "false"}
for m in ["now", "next"]:
    tally = {}
    miss = []
    for p in plans[m]:
        kind = KIND.get(p["qid"])
        if not kind:
            continue
        cl = p["reply"]["claims"]
        if kind == "general":
            ok = all(c["verdict"] == "given" for c in cl)
        else:
            ok = any(c["verdict"] == "check" and re.search(MARK[p["qid"]], c["claim"], re.I) for c in cl)
        a = tally.setdefault(kind, [0, 0])
        a[0] += ok
        a[1] += 1
        if not ok:
            miss.append(f"{p['qid']}#{p['k']}: " + " ".join(f"[{c['verdict']}] {c['claim']}" for c in cl)[:200])
    print(f"   {NAMES[m]}: false specific fact checked in {tally['false'][0]} of {tally['false'][1]} plans; true specific fact checked in {tally['true'][0]} of {tally['true'][1]}; general question with nothing checked in {tally['general'][0]} of {tally['general'][1]}")
    for x in miss:
        print("        not as intended:", x)

print("\n5. SIZE OF THE PLANS (12 questions)")
for m in ["now", "next"]:
    fin = [p for p in plans[m] if p["qid"] in FINAL]
    parts = [len(p["reply"]["parts"]) for p in fin]
    nec = [sum(1 for x in p["reply"]["parts"] if x["need"] == "necessary") for p in fin]
    kq = [sum(len(b["keyQuestions"]) for b in p["briefs"]) for p in fin]
    cost = sum((p["usage"]["input"] * 0.1 + p["usage"]["output"] * 0.5) / 1e6 for p in fin) / len(fin)
    print(f"   {NAMES[m]}: parts {st.mean(parts):.2f} (necessary {st.mean(nec):.2f}); key questions sent with three researchers {st.mean(kq):.1f}; planning calls {st.mean(p['attempts'] for p in fin):.2f} a plan; fallback plans {sum(p['fallback'] for p in fin)}; ${cost:.4f} a plan")

for t in [a for a in sys.argv[1:] if not a.startswith("--")]:
    for m in METHODS:
        for p in [x for x in plans[m] if x["qid"] == t][:1]:
            lab = {k["id"]: k["label"] for r in labels[m] if r["qid"] == t and r["k"] == p["k"] for k in r["keys"]}
            print(f"\n===== {NAMES[m]} | {t} #{p['k']}: {p['question']}")
            for i, b in enumerate(p["briefs"]):
                print(f"  A{i + 1} {b['objective'][:200]}")
                for j, k in enumerate(b["keyQuestions"]):
                    print(f"       [{lab.get(f'A{i + 1}.{j + 1}', '?'):10s}] {k[:190]}")
