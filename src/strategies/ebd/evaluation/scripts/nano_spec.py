"""The questions and specs of the side run on a weaker model (design section 37).

    python local/ebd-heldout/nano_spec.py      writes nano-questions.json, spec-nano-a.json (one question,
                                               to see that the program runs on this model and what a run
                                               costs) and spec-nano-b.json (the other five)

The six questions of the two earlier tests whose planted fact is false and well known, each with the
one thing a report must say. With Claude Haiku 5.5 both sides stated all six (sections 31 and 35). Both
sides get at most three researchers, so that the whole run stays within the 5 dollars of the key.

How it is read, fixed before the runs: the planted point is scored 1, 0.5 or 0 with the judge's
coverage instruction; six questions cannot show a difference by a test (that needs six to none), so the
counts are an indication, read together with what the run records show (plans, checks, failures).
"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = "local/ebd-heldout"
src = {q["id"]: q for f in ("planted2-questions.json", "final-planted-questions.json") for q in json.load(open(f"{ROOT}/{f}", encoding="utf8"))}
IDS = ["pp01", "pp02", "pp03", "pp04", "p01", "p02"]
questions = [{**src[i], "set": "nano"} for i in IDS]
json.dump(questions, open(f"{ROOT}/nano-questions.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)


def spec(name, ids, note):
    return {
        "name": name,
        "description": f"Side run on a weaker model (design section 37), {note}: the baseline against the EBD strategy with the baseline's number of researchers, on questions with a well-known false fact. GPT-5 nano, one run per cell, at most three researchers.",
        "tasks": [{"id": q["id"], "question": q["question"]} for q in questions if q["id"] in ids],
        "strategies": ["baseline", {"name": "ebd", "label": "ebd", "options": {}, "matchResearchersTo": "baseline"}],
        "models": ["nano"],
        "repeats": 1,
        "budget": {"researchersTotal": 3},
        "maxRounds": 8,
        "concurrency": 3,
        "parallelRuns": 2,
        "researcherTimeoutMs": 480000,
        "outDir": "local/ebd-heldout",
    }


json.dump(spec("nano-a", ["pp01"], "stage a"), open(f"{ROOT}/spec-nano-a.json", "w", encoding="utf8"), ensure_ascii=False, indent=2)
json.dump(spec("nano-b", [i for i in IDS if i != "pp01"], "stage b"), open(f"{ROOT}/spec-nano-b.json", "w", encoding="utf8"), ensure_ascii=False, indent=2)
for q in questions:
    print(f"  {q['id']} {q['question']}\n       must: {q['checklist'][0]}")
