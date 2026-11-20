"""The questions and the experiment specs of the final test (design section 29.6), in two stages.

    python local/ebd-heldout/final_spec.py planted    stage 1: no network; writes final-planted-questions.json
                                                      and spec-final-planted.json
    python local/ebd-heldout/final_spec.py sealed     stage 2: FETCHES THE SEALED QUESTIONS, which nobody may
                                                      read earlier; writes final-sealed-questions.json and
                                                      spec-final-sealed.json

Stage 1 runs first. Its four questions were written on 2026-11-19 and are not sealed, so it is also the
live check of the program as it will be tested. Between the stages only a defect of the program may be
fixed (a failed run, a contract problem, a rule that does not act as specified); the reports of stage 1
are not read for quality before stage 2 has run.

Questions:
- 4 questions with a planted problem, written on 2026-11-19 before any run on them, each with the one
  thing a report must say.
- 12 real user queries: draws 15 onward of the first seed (20261118) from the test split of Researchy
  Questions, the first 12 that have a question and at least three sub-questions. Their checklist is the
  dataset's own list of top-level sub-questions.

Arms: the baseline, and the one EBD approach with the number of researchers the baseline used on the
same question (`matchResearchersTo`). One run for each cell, Haiku, the same day.
"""
import ast
import json
import random
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
SEED = 20261118
ROWS = 6448
WANTED = 12
ROOT = "local/ebd-heldout"

# Written on 2026-11-19, before any run. "must" is what the report has to say for a yes.
PLANTED = [
    {
        "id": "p01",
        "kind": "false premise: a wrong date",
        "question": "Why did the Chernobyl nuclear accident happen in 1989?",
        "must": "States that the accident happened in 1986 (26 April 1986), not in 1989.",
    },
    {
        "id": "p02",
        "kind": "false premise: a wrong attribution",
        "question": "How did Alexander Fleming's discovery of insulin change the treatment of diabetes?",
        "must": "States that Fleming did not discover insulin, and names Banting (with Best, at Toronto, 1921 to 1922) as its discoverer.",
    },
    {
        "id": "p03",
        "kind": "sources that give different figures",
        "question": "How tall is Mount Everest?",
        "must": "Gives 8,848.86 m as the height announced by Nepal and China in 2020, and says that at least one earlier figure differs (8,848 m or 8,850 m) and why.",
    },
    {
        "id": "p04",
        "kind": "the answer depends on who asks",
        "question": "Do I need a visa to visit the United Kingdom for a week?",
        "must": "Says that the answer depends on nationality, and covers both visitors who need a visa and visitors who need only an electronic travel authorisation; does not answer for one nationality alone.",
    },
]

APPROACH = {"init": "environment", "focusFollowUp": True, "leanGuidance": True, "strictFollowUp": True}


def write(stage, questions, description):
    json.dump(questions, open(f"{ROOT}/final-{stage}-questions.json", "w", encoding="utf8", newline="\n"), indent=2, ensure_ascii=False)
    spec = {
        "name": f"final-{stage}",
        "description": description,
        "tasks": [{"id": q["id"], "question": q["question"]} for q in questions],
        "strategies": ["baseline", {"name": "ebd", "label": "ebd-one", "options": APPROACH, "matchResearchersTo": "baseline"}],
        "models": ["haiku"],
        "repeats": 1,
        "budget": {"researchersTotal": 6},
        "maxRounds": 8,
        "concurrency": 4,
        "parallelRuns": 2,
        "researcherTimeoutMs": 480000,
        "outDir": "local/ebd-heldout",
    }
    json.dump(spec, open(f"{ROOT}/spec-final-{stage}.json", "w", encoding="utf8", newline="\n"), indent=2, ensure_ascii=False)


stage = sys.argv[1] if len(sys.argv) > 1 else ""
if stage == "planted":
    questions = [{"id": q["id"], "origin": "planted", "set": "final", "type": q["kind"], "question": q["question"], "checklist": [q["must"]]} for q in PLANTED]
    write("planted", questions, "Final test, stage 1 (design section 29.6): the baseline against the one EBD approach with the baseline's number of researchers, on 4 questions with a planted problem. Haiku, one run per cell.")
    print(len(questions), "planted questions written")
elif stage == "sealed":
    offsets = random.Random(SEED).sample(range(ROWS), 60)[14:]
    real = []
    for off in offsets:
        if len(real) == WANTED:
            break
        url = f"https://datasets-server.huggingface.co/rows?dataset=corbyrosset%2Fresearchy_questions&config=default&split=test&offset={off}&length=1"
        raw = ""
        for attempt in range(8):
            raw = subprocess.run(["curl", "-s", "-m", "60", "-A", "curl/8", url], capture_output=True).stdout.decode("utf-8", "replace")
            if raw.lstrip().startswith("{") and '"rows"' in raw:
                break
            time.sleep(20)
        else:
            raise SystemExit(f"offset {off}: no data after 8 attempts; run again later")
        time.sleep(2)
        row = json.loads(raw)["rows"][0]["row"]
        dec = row["gpt4_decomposition"]
        if isinstance(dec, str):
            dec = ast.literal_eval(dec)
        heads = [h[0].lstrip("- ").strip() for h in dec["headers"] if h]
        if not row.get("question") or len(heads) < 3:
            continue
        real.append({"offset": off, "question": row["question"], "checklist": heads})
    if len(real) < WANTED:
        raise SystemExit(f"only {len(real)} of {WANTED} questions drawn; nothing written")
    questions = [{"id": f"s{i:02d}", "origin": "real", "set": "final", "type": "real user query (sealed draw)", "offset": d["offset"], "question": d["question"], "checklist": d["checklist"]} for i, d in enumerate(real, 1)]
    write("sealed", questions, "Final test, stage 2 (design section 29.6): the baseline against the one EBD approach with the baseline's number of researchers, on 12 sealed real queries. Haiku, one run per cell.")
    print(len(questions), "sealed questions written; they are now read and must not be used for development")
else:
    raise SystemExit("usage: python local/ebd-heldout/final_spec.py planted | sealed")
