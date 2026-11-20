"""What the two switches of the EBD strategy changed, on recorded runs and with no model call (design
section 39). Until 2026-11-20 `conflicts: false` turned the conflict checker off and `newGoals: false`
kept only the goals of the first plan.

The 28 runs of the strategy in the final test and in the planted-problem test were replayed by
golden.ts three times: with both switches on, with new goals off, with the conflict checker off. A
replay feeds a run's recorded replies and its recorded researcher results back in, so it says what the
strategy would have done as long as the same researchers are sent. This script checks that for every
run and then compares what the writer is given. It also adds up the time and cost of the strategy's
own model calls from the run records (Haiku 5.5: $0.10 a million tokens in, $0.50 out).

The replays with a switch off can only be made on commit a4e5cb2 or earlier: the code after it rejects
the two settings.

  tsx local/ebd-heldout/golden.ts '{}' local/ebd-heldout/switch-default.json <the four test folders>
  tsx local/ebd-heldout/golden.ts '{"newGoals":false}' local/ebd-heldout/switch-nonewgoals.json <the same>
  tsx local/ebd-heldout/golden.ts '{"conflicts":false}' local/ebd-heldout/switch-noconflicts-<name>.json <folder or run>
  python local/ebd-heldout/switch_check.py
"""
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
R = "local/ebd-heldout"
FOLDERS = ["final-planted-20261120-022344", "final-sealed-20261120-023629", "planted2-a-20261120-062842", "planted2-b-20261120-064014"]
IN, OUT = 0.10 / 1e6, 0.50 / 1e6

default = json.load(open(f"{R}/switch-default.json", encoding="utf8"))
nonew = json.load(open(f"{R}/switch-nonewgoals.json", encoding="utf8"))
noconf = {}
by_dir = {k.split(" ")[1]: k for k in default}
for f in glob.glob(f"{R}/switch-noconflicts*.json"):
    for k, v in json.load(open(f, encoding="utf8")).items():
        # A run replayed by itself is keyed "check <run folder>"; the run folder identifies it.
        noconf[by_dir.get(k.split(" ")[1], k)] = v

# The record: researchers left before each step, the briefs the platform accepted, and the calls.
record, baseline = {}, []
for folder in FOLDERS:
    for s in json.load(open(f"{R}/{folder}/summaries.json", encoding="utf8")):
        if s["status"] != "ok":
            continue
        if s["strategy"]["name"] != "ebd":
            baseline.append(s)
            continue
        decisions = [e["data"] for e in (json.loads(l) for l in open(os.path.join(s["dir"], "events.jsonl"), encoding="utf8") if l.strip()) if e["type"] == "decision"]
        key = f"{s['tags'].get('task', '')} {os.path.basename(s['dir'].replace(chr(92), '/'))}"
        record[key] = {"summary": s, "decisions": decisions}
assert set(record) == set(default) == set(nonew), "the replays do not cover the recorded runs"

task = lambda k: k.split(" ")[0]
last = lambda x: x["steps"][-1]["state"]
blocks = lambda x: (x["synthesis"]["guidance"] or "").split("\n\n")
head = lambda b: b.split("\n")[0]
CRITICAL = "The answer depends on these points"
APART = "Evidence to keep apart"
CLAIM = "The question takes for granted"
ENDS = {"complete": "complete", "budget": "researchers ran out"}


def sent(key, replay):
    """The briefs of each step that get a researcher: what the strategy asks for, cut to the researchers left."""
    return [json.dumps(st["briefs"][: d["budgetBefore"]], sort_keys=True) for st, d in zip(replay[key]["steps"], record[key]["decisions"])]


def unsent(key, replay):
    """Steps in which the strategy asks for more researchers than are left."""
    return sum(1 for st, d in zip(replay[key]["steps"], record[key]["decisions"]) if len(st["briefs"]) > d["budgetBefore"])


def only_in(a, b):
    """Goals of the last state of a that b does not have, matched by their text (their IDs shift)."""
    texts = {g["text"] for g in last(b)["goals"]}
    return [g for g in last(a)["goals"] if g["text"] not in texts]


def compare(title, other):
    keys = [k for k in default if k in other]
    n = len(keys)
    print(f"\n{title}: {n} runs")
    print(f"   researchers sent to the same goals in every round: {sum(sent(k, default) == sent(k, other) for k in keys)} of {n}")
    for name, part in (("notes", "material"), ("outline", "outline"), ("guidance", "guidance")):
        print(f"   the writer gets the same {name}: {sum(default[k]['synthesis'][part] == other[k]['synthesis'][part] for k in keys)} of {n}")
    words = lambda rep: sum(len((rep[k]["synthesis"]["guidance"] or "").split()) for k in keys) / n
    print(f"   words of guidance a run: {words(default):.0f} with both on, {words(other):.0f} with the switch off")
    ends = lambda rep: {ENDS.get(e, e): sum(1 for k in keys if (last(rep[k])["stop"] or {}).get("kind") == e) for e in sorted({(last(rep[k])["stop"] or {}).get("kind") for k in keys}, key=str)}
    print(f"   how the run's end is recorded: both on {ends(default)}; switch off {ends(other)}")
    print(f"   runs in which the strategy asks for a researcher when none is left: both on {sum(unsent(k, default) > 0 for k in keys)}, switch off {sum(unsent(k, other) > 0 for k in keys)}")
    return keys


print("WHAT THE TWO SWITCHES CHANGED: recorded runs of the strategy replayed with no model call")
print(f"{len(record)} runs (final test 16, planted-problem test 12), replayed on commit a4e5cb2, the last with the switches")
second = [k for k in record if any(d["accepted"] for d in record[k]["decisions"][1:])]
print(f"recorded runs in which a researcher was sent after the first round: {len(second)} of {len(record)} ({', '.join(task(k) for k in second)})")
print("in all the others the notes come from the first round, which neither switch touches")

# (1) New goals.
keys = compare("(1) New goals off, against both switches on", nonew)
extra = [(task(k), g) for k in keys for g in only_in(default[k], nonew[k])]
runs_of = lambda rows: len({t for t, _ in rows})
necessary = [(t, g) for t, g in extra if g["need"] == "necessary"]
print(f"   goals that exist only with new goals on: {len(extra)} in {runs_of(extra)} runs; marked necessary: {len(necessary)} in {runs_of(necessary)} runs ({', '.join(sorted({t for t, _ in necessary}))})")
print(f"   of these, goals that had a researcher: {sum(1 for _, g in extra if g['attempts'] > 0)}")

# (2) The conflict checker.
keys = compare("(2) Conflict checker off, against both switches on", noconf)
missing = [task(k) for k in default if k not in noconf]
print(f"   not replayed: {', '.join(missing)} (see 3)")
lost, gained = {}, {}
for k in keys:
    d, o = blocks(default[k]), blocks(noconf[k])
    for b in d:
        if b not in o:
            lost.setdefault(head(b)[:34], []).append((task(k), b))
    for b in o:
        if b not in d:
            gained.setdefault(head(b)[:34], []).append((task(k), b))
print("   parts of the guidance only with the checker on:")
for h, rows in lost.items():
    lines = sum(b.count("\n- ") for _, b in rows)
    print(f"      \"{h}...\": {len(rows)} runs, {lines} lines, {min(b.count(chr(10) + '- ') for _, b in rows)} to {max(b.count(chr(10) + '- ') for _, b in rows)} a run ({', '.join(t for t, _ in rows)})")
print(f"   parts of the guidance only with the checker off: {sum(len(v) for v in gained.values()) or 'none'}")
with_claim = lambda rep: sorted(task(k) for k in keys if any(b.startswith(CLAIM) for b in blocks(rep[k])))
print(f"   runs in which the writer is told to correct a claim of the question: checker on {len(with_claim(default))}, off {len(with_claim(noconf))}; the same runs and the same text: {[b for k in keys for b in blocks(default[k]) if b.startswith(CLAIM)] == [b for k in keys for b in blocks(noconf[k]) if b.startswith(CLAIM)]}")
count = lambda rep, f: sum(1 for k in keys for c in last(rep[k])["conflicts"] if f(c))
print(f"   disagreements recorded: checker on {count(default, lambda c: True)} ({count(default, lambda c: c['critical'])} critical), off {count(noconf, lambda c: True)}")
on_only = [(task(k), g) for k in keys for g in only_in(default[k], noconf[k])]
off_only = [(task(k), g) for k in keys for g in only_in(noconf[k], default[k])]
print(f"   goals only with the checker on: {len(on_only)} in {runs_of(on_only)} runs, all made to settle a disagreement: {all(g.get('settles') for _, g in on_only)}; with a researcher: {sum(1 for _, g in on_only if g['attempts'] > 0)}")
print(f"   goals only with the checker off: {len(off_only)} in {runs_of(off_only)} runs ({', '.join(f'{t} {g['need']}' for t, g in off_only)}); with a researcher: {sum(1 for _, g in off_only if g['attempts'] > 0)}")

# (3) The run with a second round.
print("\n(3) The run with a second round")
for k in second:
    ds = record[k]["decisions"]
    print(f"   {task(k)} \"{ds[0]['strategyState']['question']}\": researchers {record[k]['summary']['researchersUsed']} of {record[k]['summary']['researchersBudget']}")
    for d in ds[1:]:
        for b in d["accepted"]:
            for g in last(default[k])["goals"]:
                if g["id"] in b["tag"].split(","):
                    c = next((c for c in last(default[k])["conflicts"] if c["id"] == g.get("settles")), None)
                    print(f"   round {d['round']}: a researcher to {g['id']} ({g['kind']}, made from {(g.get('origin') or {}).get('type')}); afterwards {g['status']}, claim verdicts {g.get('verdicts')}")
                    if c:
                        print(f"      the disagreement it was to settle ({c['type']}): {c['statement']}")
    print(f"   replayed with new goals off: the same researcher is asked for: {sent(k, default) == sent(k, nonew)}")
    print(f"   replayed with the conflict checker off: {'done' if k in noconf else 'not possible: the researcher of the second round was sent to a goal that only the conflict checker makes, so the record does not hold what the run would have done without it'}")

# (4) Time and cost of the strategy's own calls.
print("\n(4) Time and cost of the strategy's own model calls in the 28 recorded runs")
mean = lambda xs: sum(xs) / len(xs)
runs = [r["summary"] for r in record.values()]
print(f"   a run of the strategy: {mean([s['durationMs'] for s in runs]) / 1000:.0f} s and ${mean([s['costUsdEstimate'] for s in runs]):.3f}; of the baseline ({len(baseline)} runs): {mean([s['durationMs'] for s in baseline]) / 1000:.0f} s and ${mean([s['costUsdEstimate'] for s in baseline]):.3f}")
total_ms, total_usd = sum(s["durationMs"] for s in runs), sum(s["costUsdEstimate"] for s in runs)
for role, name in (("environment_analyst", "the plan"), ("conflict_checker", "the conflict checker"), ("round_analyst", "the round analyst")):
    calls = [c for r in record.values() for d in r["decisions"] for c in d["strategyState"]["step"]["calls"] if c["role"] == role]
    ms, usd = sum(c["ms"] for c in calls), sum(c["inputTokens"] * IN + c["outputTokens"] * OUT for c in calls)
    print(f"   {name:20} {len(calls):2} calls, {sum(1 for c in calls if not c['accepted'])} of them rejected and asked again; a run: {ms / len(runs) / 1000:4.1f} s ({100 * ms / total_ms:.0f}% of its time) and ${usd / len(runs):.4f} ({100 * usd / total_usd:.1f}% of its cost)")
