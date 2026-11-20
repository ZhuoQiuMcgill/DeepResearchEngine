"""Seeded random draw of real user queries for the held-out test of 2026-11-18.

Source: the public dataset "Researchy Questions" (Rosset et al. 2024; Hugging Face
corbyrosset/researchy_questions), test split: search-engine queries of real users that need more
than one fact to answer. The draw is fixed by the seed, so nobody chooses the questions.
Only the question text is kept. Usage: python local/ebd-heldout/sample.py
"""
import json
import random
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
SEED = 20261118
ROWS = 6448
DRAWS = 14
random.seed(SEED)
offsets = random.sample(range(ROWS), DRAWS)
out = []
for off in offsets:
    url = f"https://datasets-server.huggingface.co/rows?dataset=corbyrosset%2Fresearchy_questions&config=default&split=test&offset={off}&length=1"
    raw = subprocess.run(["curl", "-s", "-m", "60", "-A", "curl/8", url], capture_output=True).stdout.decode("utf-8", "replace")
    try:
        row = json.loads(raw)["rows"][0]["row"]
        out.append({"offset": off, "question": row.get("question"), "keys": sorted(row.keys())})
    except Exception as e:  # noqa: BLE001
        out.append({"offset": off, "question": None, "error": str(e)[:200], "raw": raw[:200]})
json.dump({"seed": SEED, "split": "test", "rows": ROWS, "draws": out}, open("local/ebd-heldout/researchy-sample.json", "w", encoding="utf8"), indent=2, ensure_ascii=False)
for i, d in enumerate(out, 1):
    print(i, d["offset"], repr(d["question"]), d.get("error", ""))
print("keys:", out[0].get("keys"))
