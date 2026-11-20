"""The side run on a weaker model (design section 37): what the run records and the scores show.
No model call. Cost is counted at OpenAI's list prices for GPT-5 nano ($0.05 and $0.40 a million tokens)
and $0.01 for every web search call, searches and page opens alike, which is the upper bound.

Usage: python local/ebd-heldout/nano_stats.py [--plans]
"""
import glob
import json
import os
import re
import statistics as st
import sys

sys.stdout.reconfigure(encoding="utf-8")
R = "local/ebd-heldout"
Q = {q["id"]: q for q in json.load(open(f"{R}/nano-questions.json", encoding="utf8"))}
S = []
for prefix in ("nano-a-", "nano-b-"):
    folders = sorted(d for d in glob.glob(f"{R}/{prefix}*") if os.path.exists(os.path.join(d, "summaries.json")))
    if folders:
        S += json.load(open(os.path.join(folders[-1], "summaries.json"), encoding="utf8"))
scores = {}
if os.path.exists(f"{R}/nano-scores.json"):
    scores = {(r["task"], r["arm"]): r for r in json.load(open(f"{R}/nano-scores.json", encoding="utf8"))["rows"]}
ARMS = ["baseline", "ebd"]


def cost(s):
    total = 0.0
    calls = 0
    for u in s["usageByRole"].values():
        total += (u["inputTokens"] * 0.05 + u["outputTokens"] * 0.4) / 1e6
        calls += u.get("searches", 0) + u.get("pageReads", 0)
    return total + 0.01 * calls, total, calls


def events(s):
    return [json.loads(l) for l in open(os.path.join(s["dir"], "events.jsonl"), encoding="utf8") if l.strip()]


print(f"{len(S)} runs")
print(f"   {'':5s} {'side':9s} status  researchers  searches  pages  tokens in/out        cost    seconds  report words  planted point")
tot = {a: 0.0 for a in ARMS}
for s in sorted(S, key=lambda s: (s["tags"]["task"], s["strategy"]["label"])):
    a = s["strategy"]["label"]
    c, tok, calls = cost(s)
    tot[a] += c
    path = os.path.join(s["dir"], "report.md")
    words = len(open(path, encoding="utf8").read().split()) if os.path.exists(path) else 0
    tin = sum(u["inputTokens"] for u in s["usageByRole"].values())
    tout = sum(u["outputTokens"] for u in s["usageByRole"].values())
    sc = scores.get((s["tags"]["task"], a))
    print(f"   {s['tags']['task']:5s} {a:9s} {s['status']:6s}  {s['researchersUsed']}/{s['researchersBudget']}          {s['searches']:3d}      {s['pageReads']:3d}    {tin:8d}/{tout:6d}   ${c:.3f}   {s['durationMs'] / 1000:5.0f}    {words:5d}         {sc['score'] if sc else '-'}")
print(f"   cost: baseline ${tot['baseline']:.2f}, EBD ${tot['ebd']:.2f}, together ${sum(tot.values()):.2f}")

if scores:
    done = [t for t in Q if all((t, a) in scores and scores[(t, a)]["score"] is not None for a in ARMS)]
    full = {a: sum(1 for t in done if scores[(t, a)]["score"] == 1) for a in ARMS}
    part = {a: sum(1 for t in done if scores[(t, a)]["score"] == 0.5) for a in ARMS}
    print(f"\nPlanted point on the {len(done)} questions scored on both sides: in full baseline {full['baseline']}, EBD {full['ebd']}; in part {part['baseline']} and {part['ebd']}; missing {len(done) - full['baseline'] - part['baseline']} and {len(done) - full['ebd'] - part['ebd']}")
    for t in Q:
        for a in ARMS:
            r = scores.get((t, a))
            if r:
                print(f"   {t} {a:9s} {r['score']}: {r['quote'][:170]}")

print("\nWhat each side's own steps recorded")
for s in sorted(S, key=lambda s: (s["tags"]["task"], s["strategy"]["label"])):
    a = s["strategy"]["label"]
    ev = events(s)
    dec = [e["data"] for e in ev if e["type"] == "decision"]
    if not dec:
        print(f"   {s['tags']['task']} {a}: no decision recorded; {s.get('stopReason')}")
        continue
    st0 = dec[0]["strategyState"]
    if a == "baseline":
        note = ((st0.get("interpretation") or "") + " " + (dec[0].get("rationale") or ""))[:260]
        print(f"   {s['tags']['task']} baseline: briefs {[len(d['accepted']) for d in dec]}; planner's notes: {note}")
    else:
        last = dec[-1]["strategyState"]
        given = {g["id"] for g in (last.get("premises") or {}).get("given", [])}
        verdicts = {}
        for g in last["goals"]:
            verdicts.update(g.get("verdicts") or {})
        claims = "; ".join(f"{'given' if x['id'] in given else 'check'} -> {verdicts.get(x['id'], '-')}: {x['claim'][:70]}" for x in last["analysis"]["assumptions"]) or "no claim"
        calls = [c for d in dec for c in d["strategyState"]["step"]["calls"]]
        rejected = sum(1 for c in calls if not c.get("accepted", True))
        print(f"   {s['tags']['task']} EBD: briefs {[len(d['accepted']) for d in dec]}; plan fallback {last['init'].get('fallback')}; strategy calls {len(calls)} (rejected {rejected}); problems {len(last['problems'])}; conflicts {len(last['conflicts'])}; stop {(last.get('stop') or {}).get('kind')}; claims [{claims}]")
        for p in last["problems"][:3]:
            print(f"        problem: {p[:200]}")
    for d in s["diagnostics"][:4]:
        print(f"        diagnostic: {d[:200]}")

if "--plans" in sys.argv:
    for s in sorted(S, key=lambda s: (s["tags"]["task"], s["strategy"]["label"])):
        dec = [e["data"] for e in events(s) if e["type"] == "decision"]
        print(f"\n===== {s['tags']['task']} {s['strategy']['label']}")
        for d in dec:
            for b in d["accepted"]:
                print(f"  {b['id']}: {b['objective'][:200]}")
                for k in b["keyQuestions"]:
                    print(f"       - {k[:170]}")
