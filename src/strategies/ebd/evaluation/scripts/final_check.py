"""Did the program act as specified? The check between the two stages of the final test (design
section 29.6). No model call, and no report is read: only the run records of the approach's runs.

For every run: it ended ok. For every run of the approach:
- the plan was made in one call and accepted without the fallback;
- first round (section 30): as many briefs as the smaller of the researchers allowed, 4 and the number
  of main parts; every necessary part asked in it; a part asked as one question, or not asked, only
  when the round has fewer researchers than the plan has parts; the check of the claims rides in a brief;
- after the first round (section 29.2): a researcher goes only to a necessary goal or to a planned part
  not yet asked; no goal settles a conflict that decides no claim; no extra round of details;
- no problem recorded by the strategy.

Usage: python local/ebd-heldout/final_check.py <experiment folder | run folder> [more]
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
NEW = "ebd-one"


def runs_of(folder):
    if os.path.exists(os.path.join(folder, "summaries.json")):
        return json.load(open(os.path.join(folder, "summaries.json"), encoding="utf8"))
    s = json.load(open(os.path.join(folder, "summary.json"), encoding="utf8"))
    s.setdefault("dir", folder)
    s.setdefault("tags", {"task": os.path.basename(folder)[-4:]})
    return [s]


def check(s):
    """Returns (facts, faults) for one run of the approach."""
    d = s["dir"] if os.path.exists(s["dir"]) else s.get("_folder", s["dir"])
    events = [json.loads(l) for l in open(os.path.join(d, "events.jsonl"), encoding="utf8") if l.strip()]
    decisions = [e["data"] for e in events if e["type"] == "decision"]
    faults = []
    if not decisions or "goals" not in (decisions[-1].get("strategyState") or {}):
        return "no strategy state", ["no strategy state in the record"]
    st = decisions[-1]["strategyState"]
    goals = {g["id"]: g for g in st["goals"]}
    init = st["init"]
    if init["mode"] != "environment":
        faults.append(f"plan made in mode {init['mode']}")
    if init["fallback"]:
        faults.append("the plan is the fallback after rejected replies")
    events_of = (st.get("map") or {}).get("events", [])
    part_ids = [e["goalId"] for e in events_of]
    size = {e["goalId"]: len(e["parts"]) for e in events_of}
    allowed = s["researchersBudget"]
    rounds = [x["accepted"] for x in decisions if x.get("accepted")]
    first = rounds[0] if rounds else []
    tags = lambda brief: (brief.get("tag") or "").split(",")
    asked = {}
    for brief in first:
        for gid in tags(brief):
            if gid in size:
                own = sum(1 for k in brief["keyQuestions"] if k.startswith(f"[{gid}] "))
                asked[gid] = "one by one" if own > 1 else "as one question"
    expected = min(allowed, 4, len(part_ids))
    if part_ids and len(first) != expected:
        faults.append(f"first round has {len(first)} brief(s); expected {expected} (researchers allowed {allowed}, main parts {len(part_ids)})")
    necessary = [g for g in part_ids if goals[g]["need"] == "necessary"]
    for g in necessary:
        if g not in asked:
            faults.append(f"necessary part {g} is not asked in the first round")
    enough = len(first) >= len(part_ids)
    for g in part_ids:
        if enough and asked.get(g) != "one by one":
            faults.append(f"part {g} is {asked.get(g, 'not asked')} although the round has a researcher for every part")
    if len(first) > len(necessary):
        for g in necessary:
            if asked.get(g) == "as one question":
                faults.append(f"necessary part {g} is asked as one question although the round has more researchers than necessary parts")
    given = {x["id"] for x in (st.get("premises") or {}).get("given", [])}
    to_check = [a["id"] for a in st["analysis"]["assumptions"] if a["id"] not in given]
    check_goals = [g for g in st["goals"] if g["kind"] == "verify" and g["verifies"] and not g["settles"] and g["createdRound"] <= 1]
    rides = ""
    if to_check:
        if not check_goals:
            faults.append("claims to check, and no goal checks them")
        for g in check_goals:
            brief = next((b for b in first if g["id"] in tags(b)), None)
            if not brief:
                faults.append(f"the check {g['id']} is not asked in the first round")
            else:
                rides = "rides" if len(tags(brief)) > 1 else "has a researcher of its own"
                if len(tags(brief)) == 1 and len(first) > 1:
                    faults.append(f"the check {g['id']} has a researcher of its own")
    # After the first round.
    seen_first = {gid for brief in first for gid in tags(brief)}
    later = []
    for r, briefs in enumerate(rounds[1:], 2):
        for brief in briefs:
            for gid in tags(brief):
                g = goals.get(gid)
                if not g:
                    continue
                kind = "claim" if (g["verifies"] or g["settles"]) and g["need"] == "necessary" else "unasked part" if gid in size and gid not in seen_first else g["need"]
                later.append(f"r{r} {gid} ({kind})")
                if g["need"] != "necessary" and not (gid in size and gid not in seen_first):
                    faults.append(f"round {r}: {gid}, a completing goal, got a researcher")
    for c in st["conflicts"]:
        if c.get("settleGoal") and not c.get("claim") and c["type"] != "evidence_vs_assumption":
            faults.append(f"conflict {c['id']} ({c['type']}) decides no claim and has the settle goal {c['settleGoal']}")
    if st.get("extraRoundServed"):
        faults.append("an extra round of completing goals was served")
    for p in st["problems"]:
        faults.append(f"problem recorded: {p[:160]}")
    verdicts = {}
    for g in st["goals"]:
        for k, v in (g.get("verdicts") or {}).items():
            verdicts[k] = v
    shape = " ".join(f"{goals[g]['need'][0]}{size[g]}" for g in part_ids)
    conflicts = st["conflicts"]
    facts = (
        f"researchers allowed {allowed}, used {s['researchersUsed']}; plan {len(part_ids)} parts [{shape}], {len(to_check)} claim(s) to check, {len(given)} given; "
        f"round 1: {' | '.join((b.get('tag') or '') + ':' + str(len(b['keyQuestions'])) for b in first)}{'; the check ' + rides if rides else ''}; "
        f"later: {', '.join(later) if later else 'none'}; conflicts {len(conflicts)} (critical {sum(1 for c in conflicts if c.get('critical'))}, with a settle goal {sum(1 for c in conflicts if c.get('settleGoal'))}); "
        f"verdicts {verdicts if verdicts else '-'}; stop {st['stop']['kind'] if st.get('stop') else '-'}; strategy calls {s['usageByRole'].get('strategy', {}).get('calls', 0)}; ${s['costUsdEstimate']:.2f}, {s['durationMs'] / 1000:.0f} s"
    )
    return facts, faults


total = 0
for folder in sys.argv[1:]:
    for s in runs_of(folder):
        label = s["strategy"]["label"] if isinstance(s.get("strategy"), dict) else str(s.get("strategy"))
        task = s["tags"].get("task", "?")
        if s["status"] != "ok":
            total += 1
            print(f"{task} {label}: FAULT the run ended {s['status']} ({s.get('stopReason')})")
            continue
        if label == "baseline":
            print(f"{task} {label}: ok; researchers {s['researchersUsed']}, rounds {s['rounds']}, ${s['costUsdEstimate']:.2f}, {s['durationMs'] / 1000:.0f} s; diagnostics {len(s['diagnostics'])}")
            continue
        facts, faults = check(s)
        total += len(faults)
        print(f"{task} {label}: {'ok' if not faults else 'FAULT'}; {facts}")
        for f in faults:
            print(f"      FAULT: {f}")
print(f"\n{total} fault(s)")
sys.exit(1 if total else 0)
