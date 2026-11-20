"""The texts approved on 2026-11-20 applied (design section 34): what changed on the recorded runs,
with no model call.

1. golden-after.json (the code before) against golden-texts.json (the code after), both made by
   golden.ts on the 16 runs of the final test and the live-check run: every decision, brief, goal,
   conflict, map, log line, call check and the writer's material must be equal; the writer's outline
   and guidance are what changed.
2. The writer's outline and guidance of the code after, against the input the judged reports of
   section 33.9 were written from (rewrite-final-defs/): equal except for the sentence that was
   left out and the label of a claim.

Usage: python local/ebd-heldout/texts_check.py [--show task ...]
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
R = "local/ebd-heldout"
before = json.load(open(f"{R}/golden-after.json", encoding="utf8"))
after = json.load(open(f"{R}/golden-texts.json", encoding="utf8"))
assert list(before) == list(after), "the two replays cover different runs"

same_steps = same_material = 0
changed_guidance = with_outline = 0
for key in before:
    b, a = before[key], after[key]
    same_steps += json.dumps(b["steps"], sort_keys=True) == json.dumps(a["steps"], sort_keys=True)
    same_material += b["synthesis"]["material"] == a["synthesis"]["material"]
    changed_guidance += b["synthesis"]["guidance"] != a["synthesis"]["guidance"]
    with_outline += bool(a["synthesis"]["outline"])
n = len(before)
print(f"1. {n} runs replayed before and after")
print(f"   every step (briefs, stop, rationale, goals, conflicts, map, log lines, call checks) equal: {same_steps} of {n}")
print(f"   the writer's material equal: {same_material} of {n}")
print(f"   the writer's guidance changed: {changed_guidance} of {n}; runs that now get an outline: {with_outline} of {n} (before: {sum(bool(before[k]['synthesis']['outline']) for k in before)})")

GONE = ["The question was read as:", "say so plainly early in the report", "do not present it as established", "The client did not state these", "assumption A"]
NEW = ["The question takes for granted:", "Early in the report, say what the question's main terms mean", "Build first on the strongest sources in the notes"]
print("   lines in the guidance, runs before -> after:")
for text in GONE + NEW:
    print(f"      {text[:62]:62s} {sum(text in (before[k]['synthesis']['guidance'] or '') for k in before):2d} -> {sum(text in (after[k]['synthesis']['guidance'] or '') for k in after):2d}")
words = lambda t: len((t or "").split())
print(f"   words of guidance a run: {sum(words(before[k]['synthesis']['guidance']) for k in before) / n:.0f} -> {sum(words(after[k]['synthesis']['guidance']) for k in after) / n:.0f}")

print("\n2. Against the writer input of the judged reports (12 real queries)")
LEFT_OUT = "Cover each part of the outline. In each part, build first on the strongest sources in the notes:"
KEPT = "Build first on the strongest sources in the notes:"
equal_outline = equal_guidance = judged = 0
for key in after:
    task = key.split(" ")[0]
    path = f"{R}/rewrite-final-defs/{task}.synthesis.json"
    if not os.path.exists(path):
        continue
    judged += 1
    j = json.load(open(path, encoding="utf8"))
    a = after[key]["synthesis"]
    equal_outline += (a["outline"] or []) == j["outline"]
    expected = j["guidance"].replace(LEFT_OUT, KEPT)
    expected = re.sub(r"\bassumption A\d+\b", "the question's claim", expected)
    ok = expected == a["guidance"]
    equal_guidance += ok
    if not ok:
        print(f"   {task}: differs")
        ea, aa = expected.split("\n\n"), a["guidance"].split("\n\n")
        for x in ea:
            if x not in aa:
                print("      only in the judged input:", x[:200].replace("\n", " / "))
        for x in aa:
            if x not in ea:
                print("      only in the code's input: ", x[:200].replace("\n", " / "))
print(f"   outline equal: {equal_outline} of {judged}; guidance equal, but for the sentence left out and the claim's label: {equal_guidance} of {judged}")

for task in [x for x in sys.argv[1:] if not x.startswith("--")]:
    for key in after:
        if key.startswith(task + " "):
            print(f"\n===== {key}\nOUTLINE: {after[key]['synthesis']['outline']}\nGUIDANCE BEFORE:\n{before[key]['synthesis']['guidance']}\n\nGUIDANCE AFTER:\n{after[key]['synthesis']['guidance']}")
