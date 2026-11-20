"""The numbers of the planning-step probe (weaker-probe.ts; design sections 36 and 37). No model call.

For each model setting and side: how the plan treats the one specific fact of the question, as read by a
small model that does not know the side: corrects it itself, asks a researcher to check it, or takes it
for granted. Usage: python local/ebd-heldout/weaker_probe_stats.py [--show model qid ...]
"""
import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
P = "local/ebd-heldout/weaker"
KNOWN = ["pp01", "pp02", "pp03", "pp04", "p01", "p02"]
UNKNOWN = ["u01", "u02", "u03", "u04", "u05", "u06"]
NAMES = {
    "h55": "Claude Haiku 5.5, effort medium (as tested)",
    "h55low": "Claude Haiku 5.5, effort low",
    "h45": "Claude Haiku 4.5 (previous Haiku)",
    "luna": "OpenAI GPT-6 Luna, effort medium",
    "nano": "OpenAI GPT-5 nano, effort medium",
}
PRICE = {"h55": (0.1, 0.5), "h55low": (0.1, 0.5), "h45": (1, 5), "nano": (0.05, 0.4), "luna": (0.1, 0.5)}
CARRIER = {"pp01": r"1908", "pp02": r"invent", "pp03": r"Etna", "pp04": r"re-?entry", "p01": r"1989", "p02": r"Fleming|insulin", "u01": r"2019|librar", "u02": r"2017|ferry|Havtor", "u03": r"2016|study|Teixeira", "u04": r"2021|fail", "u05": r"outage|2024", "u06": r"2023|cancel|SkyNorth"}


def load(m):
    plans = []
    for f in sorted(glob.glob(f"{P}/{m}/*.json")):
        if f.endswith(".read.json"):
            continue
        p = json.load(open(f, encoding="utf8"))
        r = f.replace(".json", ".read.json")
        p["treatment"] = json.load(open(r, encoding="utf8"))["treatment"] if os.path.exists(r) else ("failed" if not p["ok"] else "unread")
        plans.append(p)
    return plans


models = [m for m in NAMES if os.path.isdir(f"{P}/{m}")]
for title, ids in [("A FALSE FACT THAT IS WELL KNOWN (6 questions)", KNOWN), ("A SPECIFIC FACT NO MODEL CAN KNOW (6 questions)", UNKNOWN)]:
    print(title)
    print(f"   {'':44s} {'baseline: corrects/checks/granted':36s} {'EBD: corrects/checks/granted':32s} EBD plan: calls a plan, last-resort plans, failed, marks the claim check")
    for m in models:
        plans = [p for p in load(m) if p["qid"] in ids]
        cells = []
        for arm in ("baseline", "ebd"):
            t = [p["treatment"] for p in plans if p["arm"] == arm]
            cells.append(f"{t.count('corrects'):2d} / {t.count('checks'):2d} / {t.count('granted'):2d}  of {len(t)}" + (f" ({t.count('failed')} failed)" if t.count("failed") else ""))
        e = [p for p in plans if p["arm"] == "ebd"]
        ok = [p for p in e if p["ok"]]
        marked = sum(1 for p in ok if any(c["verdict"] == "check" and re.search(CARRIER[p["qid"]], c["claim"], re.I) for c in p["claims"]))
        print(f"   {NAMES[m]:44s} {cells[0]:36s} {cells[1]:32s} {sum(p['attempts'] for p in e) / max(1, len(e)):.2f}, {sum(1 for p in e if p.get('fallback'))}, {len(e) - len(ok)}, {marked} of {len(ok)}")
    print()

print("Plans that take the fact for granted, both sets together (baseline, EBD)")
for m in models:
    plans = load(m)
    b = [p for p in plans if p["arm"] == "baseline"]
    e = [p for p in plans if p["arm"] == "ebd"]
    cost = sum((p["usage"]["input"] * PRICE[m][0] + p["usage"]["output"] * PRICE[m][1]) / 1e6 for p in plans)
    print(f"   {NAMES[m]:44s} {sum(1 for p in b if p['treatment'] == 'granted')} of {len(b)}    {sum(1 for p in e if p['treatment'] == 'granted')} of {len(e)}    planning cost ${cost:.3f}; baseline assignments a plan {sum(p['text'].count('Assignment ') for p in b) / max(1, len(b)):.2f}")

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if "--show" in sys.argv and len(args) >= 2:
    m, ids = args[0], args[1:]
    for p in load(m):
        if p["qid"] in ids:
            print(f"\n--- {NAMES[m]} | {p['qid']} {p['arm']} [{p['treatment']}]\n{p['text'][:1500]}")
