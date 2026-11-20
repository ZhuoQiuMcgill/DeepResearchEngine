"""A second seeded random draw of real user queries, for plan-level checks only (2026-11-19).

Same source and method as sample.py (Researchy Questions, test split), with another seed. The rows
that the first seed gives in its first 60 draws are left out without being fetched: draws 1 to 14 of
that seed are used, and draws 15 onward are the sealed set of the next end-to-end test, which nobody
may read before that test. The checklist of a query is the dataset's own list of top-level
sub-questions. Writes fresh-sample.json and fresh-questions.json.
Usage: python local/ebd-heldout/sample2.py
"""
import ast
import json
import random
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
FIRST_SEED = 20261118
SEED = 20261120
ROWS = 6448
WANTED = 12
reserved = set(random.Random(FIRST_SEED).sample(range(ROWS), 60))
offsets = [o for o in random.Random(SEED).sample(range(ROWS), 40) if o not in reserved]
skipped = 40 - len(offsets)

out = []
for off in offsets:
    if len(out) == WANTED:
        break
    url = f"https://datasets-server.huggingface.co/rows?dataset=corbyrosset%2Fresearchy_questions&config=default&split=test&offset={off}&length=1"
    # The server limits the rate of requests: a reply that is not JSON is asked for again after a pause,
    # so that the draw depends on the seed alone and not on which requests happened to get through.
    raw = ""
    for attempt in range(8):
        raw = subprocess.run(["curl", "-s", "-m", "60", "-A", "curl/8", url], capture_output=True).stdout.decode("utf-8", "replace")
        if raw.lstrip().startswith("{") and '"rows"' in raw:
            break
        time.sleep(20)
    else:
        raise SystemExit(f"offset {off}: no data after 8 attempts; run again later")
    time.sleep(2)
    try:
        row = json.loads(raw)["rows"][0]["row"]
        dec = row["gpt4_decomposition"]
        if isinstance(dec, str):
            dec = ast.literal_eval(dec)
        heads = [h[0].lstrip("- ").strip() for h in dec["headers"] if h]
        if not row.get("question") or len(heads) < 3:
            print("skipped offset", off, "(no question or fewer than 3 sub-questions)")
            continue
        out.append({"offset": off, "question": row["question"], "id": row.get("id"), "checklist": heads})
    except Exception as e:  # noqa: BLE001
        print("failed offset", off, str(e)[:160], raw[:120])

json.dump({"seed": SEED, "split": "test", "rows": ROWS, "left_out_for_the_first_seed": skipped, "draws": out}, open("local/ebd-heldout/fresh-sample.json", "w", encoding="utf8"), indent=2, ensure_ascii=False)
questions = [{"id": f"f{i:02d}", "origin": "real", "set": "fresh", "type": "real user query (second random draw)", "question": d["question"], "checklist": d["checklist"]} for i, d in enumerate(out, 1)]
json.dump(questions, open("local/ebd-heldout/fresh-questions.json", "w", encoding="utf8", newline="\n"), indent=2, ensure_ascii=False)
for q in questions:
    print(f"{q['id']} {len(q['checklist'])} items  {q['question']}")
print(len(questions), "questions;", sum(len(q["checklist"]) for q in questions), "checklist items; offsets left out for the first seed:", skipped)
