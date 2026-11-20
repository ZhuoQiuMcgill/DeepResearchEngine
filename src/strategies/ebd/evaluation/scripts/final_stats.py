"""The result of the final test by the rules fixed beforehand (design section 29.6). No model call:
reads the run records and the judge's results.

Measures: (1) blind pairs in both orders on the real queries, a question counting for an arm only when
both orders name it; (2) the planted points; (3) cost, time, researchers and strategy calls from the
records; (4) the platform's citation check; (5) checklist items covered, with the items that only ask
what a term is counted apart.

What counts: the approach is kept unless the baseline wins 10 or more of the questions decided, or the
approach says fewer planted points than the baseline, or it costs over 15% more. It is shown to be
better only if it wins 10 or more of the questions decided.

Usage: python local/ebd-heldout/final_stats.py
Trial on the saved runs of 2026-11-18 with the judge's saved results of that day:
       python local/ebd-heldout/final_stats.py --folders sealed-new-,sealed-baseline- --new ebd-new --questions questions.json:sealed --results judge-results.json
"""
import glob
import json
import math
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
R = "local/ebd-heldout"


def flag(name, default):
    return sys.argv[sys.argv.index("--" + name) + 1] if "--" + name in sys.argv else default


NEW = flag("new", "ebd-one")
BASE = flag("base", "baseline")
FOLDERS = flag("folders", "final-sealed-,final-planted-").split(",")
QUESTION_FILES = flag("questions", "final-sealed-questions.json,final-planted-questions.json").split(",")
RESULTS = os.path.join(R, flag("results", "judge-final-results.json"))
STOP = {"of", "in", "the", "a", "an", "to", "for", "on", "by", "its", "their", "is", "are"}


def is_definition(item, question):
    """The rule of oneplan_items.py (design section 28.8): the item only asks what a term of the question is."""
    m = re.match(r"^(what|who)\s+(is|are|was|were)\s+(.*)$", item.strip(), re.I)
    if not m:
        return False
    head = re.split(r"\s+and\s+|\?", m.group(3))[0]
    head = re.sub(r"^(the definition of|the meaning of)\s+", "", head, flags=re.I)
    words = [w for w in re.findall(r"[a-z]+", head.lower()) if w not in STOP]
    qwords = re.findall(r"[a-z]+", question.lower())
    return 1 <= len(words) <= 5 and all(any(q.startswith(w[:4]) or w.startswith(q[:4]) for q in qwords if len(q) > 2) for w in words)


def sign_test(wins, losses):
    """Two-sided exact sign test."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = max(wins, losses)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n)


questions = []
for entry in QUESTION_FILES:
    name, _, wanted = entry.partition(":")
    path = os.path.join(R, name)
    if os.path.exists(path):
        questions += [q for q in json.load(open(path, encoding="utf8")) if not wanted or q["set"] == wanted]
Q = {q["id"]: q for q in questions}
real = [q for q in questions if q["origin"] != "planted"]
planted = [q for q in questions if q["origin"] == "planted"]

summaries = []
for prefix in FOLDERS:
    dirs = sorted(d for d in glob.glob(os.path.join(R, prefix + "*")) if os.path.exists(os.path.join(d, "summaries.json")))
    if dirs:
        summaries += json.load(open(os.path.join(dirs[-1], "summaries.json"), encoding="utf8"))
runs = {(s["tags"]["task"], s["strategy"]["label"]): s for s in summaries}
if not questions or not summaries:
    raise SystemExit("no questions or no runs yet")
judged = json.load(open(RESULTS, encoding="utf8")) if os.path.exists(RESULTS) else {"results": []}
results = [r for r in judged["results"] if not r.get("error")]
# The pass of 2026-11-18 has no key; its records carry kind, task, arm and order.
coverage = {(r["task"], r["arm"]): r for r in results if r["kind"] == "coverage"}
pairs = {}
for r in results:
    if r["kind"] == "pair":
        pairs.setdefault(r["task"], []).append(r)

print(f"FINAL TEST: {BASE} against {NEW}; {len(real)} real queries, {len(planted)} planted questions; {len(summaries)} runs; judge results {len(results)}")
failed = [f"{s['tags']['task']}/{s['strategy']['label']}: {s['status']}" for s in summaries if s["status"] != "ok"]
print("runs that did not end ok:", ", ".join(failed) if failed else "none")

# ---------------------------------------------------------------- (1) pairs
print("\n(1) Blind pairs in both orders, real queries. A question counts for an arm only when both orders name it.")
CRITERIA = ["overall", "coverage", "support", "conflicts", "usefulness"]
tally = {c: {NEW: 0, BASE: 0, "not decided": 0} for c in CRITERIA}
flips = 0
for q in real:
    two = pairs.get(q["id"], [])
    if len(two) != 2:
        print(f"   {q['id']}: {len(two)} of 2 verdicts; not counted")
        continue
    line = []
    for c in CRITERIA:
        a, b = two[0]["verdict"][c], two[1]["verdict"][c]
        winner = a if a == b and a != "tie" else "not decided"
        tally[c][winner] += 1
        if c == "overall":
            flips += int(a != b and "tie" not in (a, b))
            line.append(f"{winner:11s} (as A: {two[0]['order'].split(' ')[0]} -> {a}; {two[1]['order'].split(' ')[0]} -> {b})")
    print(f"   {q['id']} {line[0]}  {q['question'][:64]}")
for c in CRITERIA:
    t = tally[c]
    print(f"   {c:10s} {NEW} {t[NEW]:2d}, {BASE} {t[BASE]:2d}, not decided {t['not decided']:2d}" + (f"; exact sign test on the decided p = {sign_test(t[NEW], t[BASE]):.3f}; the two orders named opposite reports on {flips}" if c == "overall" else ""))

# ---------------------------------------------------------------- (2) planted points
print("\n(2) The planted points (score 1: stated with a source; 0.5: stated without a source or in part; 0: absent)")
said = {NEW: 0.0, BASE: 0.0}
full = {NEW: 0, BASE: 0}
for q in planted:
    print(f"   {q['id']} {q['question']}")
    print(f"        must say: {q['checklist'][0]}")
    for arm in (BASE, NEW):
        r = coverage.get((q["id"], arm))
        if not r:
            print(f"        {arm:9s} no verdict")
            continue
        item = r["items"][0]
        said[arm] += float(item["score"])
        full[arm] += int(float(item["score"]) == 1)
        print(f"        {arm:9s} score {item['score']}{' WRONG-FLAG' if item.get('wrong') else ''}  \"{str(item.get('quote', ''))[:150]}\"")
if planted:
    print(f"   planted points said in full: {NEW} {full[NEW]} of {len(planted)}, {BASE} {full[BASE]} of {len(planted)}; sum of scores {NEW} {said[NEW]:g}, {BASE} {said[BASE]:g}")

# ---------------------------------------------------------------- (3) cost and time
print("\n(3) From the records, all questions")
tot = {}
for arm in (BASE, NEW):
    rs = [s for (t, a), s in runs.items() if a == arm and t in Q]
    tot[arm] = dict(
        n=len(rs),
        cost=sum(s["costUsdEstimate"] for s in rs),
        sec=sum(s["durationMs"] for s in rs) / 1000,
        res=sum(s["researchersUsed"] for s in rs),
        searches=sum(s["searches"] for s in rs),
        calls=sum(s["usageByRole"].get("strategy", {}).get("calls", 0) for s in rs),
        strategy=sum(s["usageByRole"].get("strategy", {}).get("costUsd", 0) for s in rs),
        rounds=sum(s["rounds"] for s in rs),
        words=sum(len(open(os.path.join(s["dir"], "report.md"), encoding="utf8").read().split()) for s in rs if os.path.exists(os.path.join(s["dir"], "report.md"))),
        unknown=sum(len(s["citationCheck"]["unknownUrls"]) for s in rs),
        urls=sum(s["citationCheck"]["reportUrls"] for s in rs),
        unbound=sum(s["citationCheck"].get("binding", {}).get("unbound", 0) for s in rs),
        checked=sum(s["citationCheck"].get("binding", {}).get("checked", 0) for s in rs),
    )
    t = tot[arm]
    if t["n"]:
        print(f"   {arm:9s} runs {t['n']:2d}: ${t['cost']:.2f} (${t['cost'] / t['n']:.3f} a run; strategy calls ${t['strategy']:.2f}), {t['sec'] / t['n']:.0f} s a run, researchers {t['res'] / t['n']:.2f} a run, rounds {t['rounds'] / t['n']:.2f}, searches {t['searches'] / t['n']:.1f}, strategy calls {t['calls'] / t['n']:.1f} a run, report {t['words'] / t['n']:.0f} words")
ratio = tot[NEW]["cost"] / tot[BASE]["cost"] if tot[BASE]["cost"] else float("nan")
print(f"   cost of {NEW} relative to {BASE}: {100 * (ratio - 1):+.0f}%")
matched = [(t, runs[(t, BASE)]["researchersUsed"], runs[(t, NEW)]["researchersBudget"], runs[(t, NEW)]["researchersUsed"]) for t in Q if (t, BASE) in runs and (t, NEW) in runs]
print("   researchers (question: baseline used / approach allowed / approach used): " + ", ".join(f"{t} {b}/{a}/{u}" for t, b, a, u in matched))

# ---------------------------------------------------------------- (4) citation check
print("\n(4) The platform's citation check")
for arm in (BASE, NEW):
    t = tot[arm]
    print(f"   {arm:9s} links in reports {t['urls']}, of them not among the researchers' sources {t['unknown']}; cited statements checked {t['checked']}, not bound to a source {t['unbound']}")

# ---------------------------------------------------------------- (5) checklist
print("\n(5) Checklist items covered, real queries (mean score; an item counts as covered at 0.5 or more)")
for arm in (BASE, NEW):
    by = {"definition": [], "other": []}
    wrong = 0
    for q in real:
        r = coverage.get((q["id"], arm))
        if not r:
            continue
        for item, text in zip(r["items"], q["checklist"]):
            by["definition" if is_definition(text, q["question"]) else "other"].append(float(item["score"]))
            wrong += int(bool(item.get("wrong")))
    every = by["definition"] + by["other"]
    if every:
        part = lambda xs: f"{sum(xs) / len(xs):.2f} mean, {sum(x >= 0.5 for x in xs)} of {len(xs)} covered" if xs else "none"
        print(f"   {arm:9s} all items {part(every)}; items that only ask what a term is: {part(by['definition'])}; other items: {part(by['other'])}; flagged wrong {wrong}")

# ---------------------------------------------------------------- the rules
print("\nBy the rules fixed before the test")
o = tally["overall"]
rule1 = o[BASE] < 10
rule2 = full[NEW] >= full[BASE]
rule3 = ratio <= 1.15
print(f"   the baseline wins fewer than 10 of the questions decided: {'yes' if rule1 else 'NO'} ({o[BASE]} of {o[NEW] + o[BASE]} decided)")
print(f"   the approach says at least as many planted points as the baseline: {'yes' if rule2 else 'NO'} ({full[NEW]} against {full[BASE]})")
print(f"   the approach costs no more than 15% above the baseline: {'yes' if rule3 else 'NO'} ({100 * (ratio - 1):+.0f}%)")
print(f"   => the approach is {'KEPT' if rule1 and rule2 and rule3 else 'NOT KEPT'}; shown to be better (10 or more wins): {'yes' if o[NEW] >= 10 else 'no'} ({o[NEW]} wins)")
