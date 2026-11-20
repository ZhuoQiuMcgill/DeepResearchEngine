"""Text measures of the rewritten reports of the final test beside the recorded ones (no model call):
words, links, distinct links, scholarly and official sites, share of the notes' links used, and how the
report opens. Usage: python local/ebd-heldout/rewrite_stats.py [variant ...]"""
import glob
import json
import os
import re
import statistics as st
import sys

sys.stdout.reconfigure(encoding="utf-8")
R = "local/ebd-heldout"
src = open(R + "/why.py", encoding="utf8").read()
ns = {}
exec(src.split("rows = {}")[0].replace('sys.stdout.reconfigure(encoding="utf-8")', ""), ns)
host, kind, links, run, TASKS = ns["host"], ns["kind"], ns["links"], ns["run"], ns["TASKS"]

variants = sys.argv[1:] or sorted(os.path.basename(d).replace("rewrite-final-", "") for d in glob.glob(R + "/rewrite-final-*"))


def text(source, task):
    if source in ("baseline", "ebd-one"):
        return open(os.path.join(run[(task, source)]["dir"], "report.md"), encoding="utf8").read()
    return open(os.path.join(R, f"rewrite-final-{source}", f"{task}.md"), encoding="utf8").read()


def notes_links(task, arm):
    out = set()
    for f in glob.glob(os.path.join(run[(task, arm)]["dir"], "results", "*.json")):
        out |= {u.rstrip(".,;") for u in links(json.load(open(f, encoding="utf8"))["notes"])}
    return out


def measure(source, task):
    t = text(source, task)
    arm = "baseline" if source in ("baseline", "base") else "ebd-one"
    urls = {u.rstrip(".,;") for u in links(t)}
    kinds = [kind(host(u)) for u in urls]
    nl = notes_links(task, arm)
    return dict(words=len(t.split()), links=len(links(t)), urls=len(urls), strong=kinds.count("scholarly") + kinds.count("official"), used=len(urls & nl) / len(nl), heads=len(re.findall(r"^## ", t, re.M)), tables=t.count("|---"))


sources = ["baseline", "base", "ebd-one"] + [v for v in variants if v != "base"]
sources = [s for s in sources if s in ("baseline", "ebd-one") or os.path.isdir(os.path.join(R, f"rewrite-final-{s}"))]
M = {s: {t: measure(s, t) for t in TASKS if os.path.exists(os.path.join(R, f"rewrite-final-{s}", f"{t}.md")) or s in ("baseline", "ebd-one")} for s in sources}
names = {"baseline": "baseline, as recorded", "base": "baseline, written again", "ebd-one": "approach, as recorded", "rec": "approach, written again", "none": "approach, no guidance", "full": "approach, outline and full-answer guidance"}
print(f"{'':44s} words  links  distinct  scholarly+official  share of notes' links  sections  tables")
for s in sources:
    m = lambda k: st.mean(M[s][t][k] for t in M[s])
    print(f"{names.get(s, s):44s} {m('words'):5.0f}  {m('links'):5.1f}  {m('urls'):7.1f}  {m('strong'):12.1f}  {m('used'):16.2f}  {m('heads'):12.1f}  {m('tables'):6.1f}")


def paired(a, b, key):
    d = [M[a][t][key] - M[b][t][key] for t in TASKS if t in M[a] and t in M[b]]
    sd = st.stdev(d)
    return st.mean(d), sd / len(d) ** 0.5


print("\nPaired differences over the 12 questions (mean, standard error)")
pairs = [("base", "baseline", "the baseline's writer from one run to the next"), ("rec", "ebd-one", "the approach's writer from one run to the next"), ("none", "rec", "no guidance against the recorded guidance"), ("full", "rec", "outline and full-answer guidance against the recorded guidance"), ("full", "base", "outline and full-answer guidance against the baseline written again"), ("rec", "base", "recorded guidance against the baseline written again"), ("none", "base", "no guidance against the baseline written again")]
for a, b, label in pairs:
    if a in M and b in M:
        print(f"   {label:68s} " + "  ".join(f"{k} {paired(a, b, k)[0]:+7.1f} (±{paired(a, b, k)[1]:.1f})" for k in ["words", "urls", "strong"]))

print("\nHow each report opens (title and first sentence), for the questions with a premise that did not hold")
for task in ["s02", "s08", "s10"]:
    for s in sources:
        if task in M[s]:
            t = text(s, task)
            title = next((l.lstrip("# ").strip() for l in t.split("\n") if l.startswith("# ")), "")
            first = re.sub(r"\(https?://[^)]*\)", "", next((l for l in t.split("\n") if l.strip() and not l.startswith("#")), ""))[:170]
            print(f"   {task} {names.get(s, s)[:28]:28s} | {title[:70]} | {first}")
