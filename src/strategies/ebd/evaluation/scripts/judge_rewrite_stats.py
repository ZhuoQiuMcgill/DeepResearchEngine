"""Step 2 of design section 33.7: the judge's verdicts on the rewritten reports, beside its verdicts on
the recorded reports of the same 12 questions (no model call).

A question counts for a side only when both orders name it. Usage:
    python local/ebd-heldout/judge_rewrite_stats.py [name, default defs] [--reasons]
"""
import json
import sys
from math import comb

sys.stdout.reconfigure(encoding="utf-8")
R = "local/ebd-heldout"
args = [a for a in sys.argv[1:] if not a.startswith("--")]
name = args[0] if args else "defs"
NEW = json.load(open(f"{R}/judge-rewrite-{name}.json", encoding="utf8"))
OLD = json.load(open(f"{R}/judge-final-results.json", encoding="utf8"))
Q = {q["id"]: q for q in json.load(open(f"{R}/final-sealed-questions.json", encoding="utf8"))}
CRIT = ["overall", "coverage", "support", "conflicts", "usefulness"]
cand = NEW["arms"]["new"]


def decided(results, task, crit, approach):
    two = [r["verdict"][crit] for r in results if r["kind"] == "pair" and r["task"] == task and "verdict" in r]
    assert len(two) == 2, (task, len(two))
    if two[0] == two[1] == approach:
        return "approach"
    if two[0] == two[1] == "baseline":
        return "baseline"
    return "-"


def sign_p(a, b):
    n, k = a + b, max(a, b)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k, n + 1)) / 2**n) if n else 1.0


old = {t: {c: decided(OLD["results"], t, c, "ebd-one") for c in CRIT} for t in Q}
new = {t: {c: decided(NEW["results"], t, c, cand) for c in CRIT} for t in Q}

print(f"Judge {NEW['judge']} (effort {NEW['effort']}); {len(NEW['results'])} pair judgments; tokens in {NEW['usage']['input']}, out {NEW['usage']['output']}; ${(NEW['usage']['input'] * 4 + NEW['usage']['output'] * 20) / 1e6:.2f}")
print("\nQuestions decided (both orders agree): approach, baseline, not decided")
print(f"{'':12s} {'recorded reports':>22s}   {'rewritten reports':>22s}")
for c in CRIT:
    o = [old[t][c] for t in Q]
    n = [new[t][c] for t in Q]
    print(f"{c:12s} {o.count('approach'):6d} {o.count('baseline'):6d} {o.count('-'):6d}     {n.count('approach'):6d} {n.count('baseline'):6d} {n.count('-'):6d}" + (f"     sign test p = {sign_p(n.count('approach'), n.count('baseline')):.2f}" if c == "overall" else ""))

print("\nBy question (overall; then coverage, support, conflicts, usefulness of the rewritten report: A approach, B baseline, - not decided)")
short = {"approach": "A", "baseline": "B", "-": "-"}
for t in sorted(Q):
    marks = " ".join(short[new[t][c]] for c in CRIT[1:])
    print(f"   {t}  recorded {old[t]['overall']:9s} rewritten {new[t]['overall']:9s} [{marks}]  {Q[t]['question'][:62]}")

# single judgments, not only the pairs that agree
flat_new = [r["verdict"]["overall"] for r in NEW["results"] if "verdict" in r]
flat_old = [r["verdict"]["overall"] for r in OLD["results"] if r["kind"] == "pair" and r["task"] in Q]
print(f"\nSingle judgments (24 each): recorded approach {flat_old.count('ebd-one')}, baseline {flat_old.count('baseline')}, tie {flat_old.count('tie')}; rewritten approach {flat_new.count(cand)}, baseline {flat_new.count('baseline')}, tie {flat_new.count('tie')}")
flips = sum(1 for t in Q if len({r["verdict"]["overall"] for r in NEW["results"] if r["task"] == t}) > 1)
print(f"Questions on which the two orders disagree: {flips} of {len(Q)}")
# position: how often the report shown as A is preferred
as_a = sum(1 for r in NEW["results"] if "verdict" in r and r["verdict"]["overall"] == r["order"].replace(" as A", ""))
print(f"The report shown first is preferred in {as_a} of {len(flat_new)} judgments")

if "--reasons" in sys.argv:
    print()
    for t in sorted(Q):
        print(f"{t} {Q[t]['question']}")
        for r in [x for x in NEW["results"] if x["task"] == t]:
            v = r["verdict"]
            who = lambda x: {"baseline": "base", "tie": "tie"}.get(x, "EBD")
            print(f"   [{r['order']}] overall {who(v['overall'])} | cov {who(v['coverage'])} sup {who(v['support'])} con {who(v['conflicts'])} use {who(v['usefulness'])}\n      {r['reason']}")
