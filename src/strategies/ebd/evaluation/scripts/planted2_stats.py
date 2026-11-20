"""The planted-problem test (design section 35): the judge's score of each report on its one planted
point, read by the rule fixed in planted_spec.py. No model call.

Usage: python local/ebd-heldout/planted2_stats.py [--quotes]
"""
import glob
import json
import os
import statistics as st
import sys
from math import comb

sys.stdout.reconfigure(encoding="utf-8")
R = "local/ebd-heldout"
Q = {q["id"]: q for q in json.load(open(f"{R}/planted2-questions.json", encoding="utf8"))}
J = json.load(open(f"{R}/judge-planted2.json", encoding="utf8"))
S = []
for prefix in ("planted2-a-", "planted2-b-"):
    folders = sorted(d for d in glob.glob(f"{R}/{prefix}*") if os.path.exists(os.path.join(d, "summaries.json")))
    if folders:
        S += json.load(open(os.path.join(folders[-1], "summaries.json"), encoding="utf8"))
run = {(s["tags"]["task"], s["strategy"]["label"]): s for s in S}
score = {(r["task"], r["arm"]): r["items"][0] for r in J["results"] if r["kind"] == "coverage" and not r.get("error")}
ARMS = ["baseline", "ebd"]
KINDS = ["false fact", "sources that give different figures", "the answer depends on who asks"]
kind_of = lambda q: next(k for k in KINDS if q["type"].startswith(k))


def sign_p(a, b):
    n, k = a + b, max(a, b)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k, n + 1)) / 2**n) if n else 1.0


done = [t for t in Q if all((t, a) in score for a in ARMS)]
print(f"Judge {J['judge']} (effort {J['effort']}); questions scored on both sides: {len(done)} of {len(Q)}; tokens in {J['usage']['input']}, out {J['usage']['output']}; ${(J['usage']['input'] * 4 + J['usage']['output'] * 20) / 1e6:.2f}")
print("\nThe planted point: 1 stated with a source, 0.5 stated without a source or in part, 0 missing")
print(f"   {'':5s} {'baseline':>8s} {'EBD':>5s}   question")
for t in sorted(done):
    b, e = float(score[(t, "baseline")]["score"]), float(score[(t, "ebd")]["score"])
    mark = "EBD" if e == 1 and b < 1 else "base" if b == 1 and e < 1 else ""
    print(f"   {t}  {b:8.1f} {e:5.1f}   {mark:5s} [{kind_of(Q[t])[:22]:22s}] {Q[t]['question'][:70]}")

full = {a: sum(1 for t in done if float(score[(t, a)]["score"]) == 1) for a in ARMS}
mean = {a: st.mean(float(score[(t, a)]["score"]) for t in done) for a in ARMS}
only_e = sum(1 for t in done if float(score[(t, "ebd")]["score"]) == 1 and float(score[(t, "baseline")]["score"]) < 1)
only_b = sum(1 for t in done if float(score[(t, "baseline")]["score"]) == 1 and float(score[(t, "ebd")]["score"]) < 1)
missing = {a: sum(1 for t in done if float(score[(t, a)]["score"]) == 0) for a in ARMS}
print(f"\nStated in full: baseline {full['baseline']} of {len(done)}, EBD {full['ebd']} of {len(done)}; mean score {mean['baseline']:.2f} and {mean['ebd']:.2f}; missing altogether {missing['baseline']} and {missing['ebd']}")
p = sign_p(only_e, only_b)
verdict = "shown" if p < 0.05 and only_e > only_b else "points the same way" if only_e > only_b else "no difference"
print(f"In full on one side only: EBD {only_e}, baseline {only_b}; two-sided sign test p = {p:.3f}. By the rule fixed beforehand: {verdict.upper()}")
print("\nBy kind (in full: baseline, EBD)")
for k in KINDS:
    ts = [t for t in done if kind_of(Q[t]) == k]
    print(f"   {k:36s} {sum(1 for t in ts if float(score[(t, 'baseline')]['score']) == 1)} and {sum(1 for t in ts if float(score[(t, 'ebd')]['score']) == 1)} of {len(ts)}")
wrong = [(t, a) for t in done for a in ARMS if score[(t, a)].get("wrong")]
print(f"\nMarked by the judge as looking wrong on the planted point: {wrong or 'none'}")

print("\nThe runs (mean of the questions scored)")
for a in ARMS:
    rows = [run[(t, a)] for t in done if (t, a) in run]
    if rows:
        words = st.mean(len(open(os.path.join(s["dir"], "report.md"), encoding="utf8").read().split()) for s in rows)
        print(f"   {a:9s} researchers {st.mean(s['researchersUsed'] for s in rows):.2f}; rounds {st.mean(s['rounds'] for s in rows):.2f}; cost ${sum(s['costUsdEstimate'] for s in rows):.2f} (${st.mean(s['costUsdEstimate'] for s in rows):.3f} a run); {st.mean(s['durationMs'] for s in rows) / 1000:.0f} s a run; report {words:.0f} words; strategy calls {st.mean(s['usageByRole'].get('strategy', {}).get('calls', 0) for s in rows):.2f}")

# What the approach's own steps did with the planted problem.
print("\nWhat the approach's plan and checks recorded")
for t in sorted(done):
    s = run.get((t, "ebd"))
    if not s:
        continue
    events = [json.loads(l) for l in open(os.path.join(s["dir"], "events.jsonl"), encoding="utf8") if l.strip()]
    state = [e["data"] for e in events if e["type"] == "decision"][-1]["strategyState"]
    given = {g["id"] for g in (state.get("premises") or {}).get("given", [])}
    verdicts = {}
    for g in state["goals"]:
        verdicts.update(g.get("verdicts") or {})
    claims = "; ".join(f"{'given' if a['id'] in given else 'check'} -> {verdicts.get(a['id'], '-')}: {a['claim'][:60]}" for a in state["analysis"]["assumptions"]) or "no claim"
    crit = sum(1 for c in state["conflicts"] if c.get("critical"))
    not_stated = len((state.get("plan") or {}).get("notStated", []))
    print(f"   {t} claims [{claims}] | conflicts {len(state['conflicts'])} (critical {crit}) | not stated by the client: {not_stated}")

if "--quotes" in sys.argv:
    print()
    for t in sorted(done):
        print(f"{t} {Q[t]['question']}\n   must: {Q[t]['checklist'][0]}")
        for a in ARMS:
            print(f"   {a:9s} {score[(t, a)]['score']}: {score[(t, a)].get('quote', '')[:260]}")
