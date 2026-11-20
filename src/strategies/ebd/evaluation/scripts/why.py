"""Why did the one approach not beat the baseline? What the records of the final test show (no model call).

For each arm on the 12 real queries: what a researcher was given (objective, key questions, constraints,
source hints, instructions), what the researchers did (searches, page reads, sources, findings, notes), and
what the report holds (words, links, hosts, kinds of sources). Then the same per question beside the
judge's verdict.

Usage: python local/ebd-heldout/why.py
"""
import glob
import json
import os
import re
import statistics as st
import sys
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8")
R = "local/ebd-heldout"
ARMS = ["baseline", "ebd-one"]
S = json.load(open(sorted(glob.glob(R + "/final-sealed-2*"))[-1] + "/summaries.json", encoding="utf8"))
J = json.load(open(R + "/judge-final-results.json", encoding="utf8"))
TASKS = sorted({s["tags"]["task"] for s in S})
run = {(s["tags"]["task"], s["strategy"]["label"]): s for s in S}

SCHOLAR = re.compile(r"(\.edu$|\.ac\.[a-z]{2}$|nih\.gov|ncbi\.|pubmed|sciencedirect|springer|wiley|tandfonline|sagepub|jstor|nature\.com|science\.org|cambridge\.org|oup\.com|academic\.oup|mdpi|frontiersin|plos|arxiv|ssrn|nber\.org|researchgate|semanticscholar|ieee\.org|acm\.org|apa\.org|bmj\.com|thelancet|jamanetwork|elsevier|doi\.org|eric\.ed\.gov|asee\.org|pnas\.org|aeaweb|uchicago|mit\.edu)")
OFFICIAL = re.compile(r"(\.gov$|\.gov\.[a-z]{2}$|\.gouv\.|\.gc\.ca$|europa\.eu|oecd\.org|imf\.org|worldbank|un\.org|who\.int|unesco|ilo\.org|parliament|legislation|congress\.gov|supremecourt|nhs\.uk|ons\.gov|census\.gov|bls\.gov|\.int$|justice\.|courts?\.)")
REFERENCE = re.compile(r"(wikipedia|britannica|encyclopedia|investopedia|khanacademy|history\.com|study\.com|quora|reddit|medium\.com|sparknotes)")
PROPER = re.compile(r"\b(?:[A-Z]{2,}|[A-Z][a-z]+(?: [A-Z][a-z]+)+)\b")


def host(u):
    h = urlparse(u).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def kind(h):
    if SCHOLAR.search(h):
        return "scholarly"
    if OFFICIAL.search(h):
        return "official"
    if REFERENCE.search(h):
        return "reference"
    return "other"


def words(t):
    return len((t or "").split())


def load(s):
    d = s["dir"]
    events = [json.loads(l) for l in open(os.path.join(d, "events.jsonl"), encoding="utf8") if l.strip()]
    decisions = [e["data"] for e in events if e["type"] == "decision"]
    briefs = [b for dec in decisions for b in dec["accepted"]]
    results = [json.load(open(f, encoding="utf8")) for f in sorted(glob.glob(os.path.join(d, "results", "*.json")))]
    report = open(os.path.join(d, "report.md"), encoding="utf8").read()
    syn = json.load(open(os.path.join(d, "synthesis.json"), encoding="utf8")) if os.path.exists(os.path.join(d, "synthesis.json")) else {}
    return decisions, briefs, results, report, syn


def links(text):
    return re.findall(r"\]\((https?://[^)\s]+)\)", text) + re.findall(r"(?<!\()\bhttps?://[^\s)\]]+", re.sub(r"\]\((https?://[^)\s]+)\)", "", text))


rows = {}
for task in TASKS:
    for arm in ARMS:
        s = run[(task, arm)]
        decisions, briefs, results, report, syn = load(s)
        kq = [len(b["keyQuestions"]) for b in briefs]
        hints = [h for b in briefs for h in b["sourceHints"]]
        cons = [c for b in briefs for c in b["constraints"]]
        notes = [r["notes"] for r in results]
        findings = sum(len(re.findall(r"^- .*https?://", n, re.M)) for n in notes)
        note_urls = {u.rstrip(".,;") for n in notes for u in links(n)}
        rep_urls = [u.rstrip(".,;") for u in links(report)]
        rep_hosts = [host(u) for u in set(rep_urls)]
        kinds = [kind(h) for h in rep_hosts]
        synth = syn.get("synthesis", syn)
        rows[(task, arm)] = dict(
            briefs=len(briefs),
            kq=sum(kq),
            kq_words=st.mean(words(k) for b in briefs for k in b["keyQuestions"]),
            obj_words=st.mean(words(b["objective"]) for b in briefs),
            cons=len(cons) / len(briefs),
            cons_words=sum(words(c) for c in cons) / len(briefs),
            hints=len(hints) / len(briefs),
            hint_words=st.mean(words(h) for h in hints) if hints else 0,
            hint_named=sum(1 for h in hints if PROPER.search(h)) / len(hints) if hints else 0,
            instr_words=st.mean(words(b.get("instructions") or "") for b in briefs),
            searches=s["searches"],
            reads=s["pageReads"],
            sources=sum(len(r["sources"]) for r in results),
            cited_sources=sum(sum(1 for x in r["sources"] if x.get("cited")) for r in results),
            queries=sum(len(r["queries"]) for r in results),
            note_words=sum(words(n) for n in notes),
            findings=findings,
            note_urls=len(note_urls),
            rep_words=words(report),
            rep_links=len(rep_urls),
            rep_urls=len(set(rep_urls)),
            rep_hosts=len(set(rep_hosts)),
            used=len(set(rep_urls) & note_urls) / len(note_urls) if note_urls else 0,
            scholarly=kinds.count("scholarly"),
            official=kinds.count("official"),
            reference=kinds.count("reference"),
            other=kinds.count("other"),
            heads=len(re.findall(r"^## ", report, re.M)),
            tables=report.count("|---"),
            guidance_words=words(synth.get("guidance", "")),
            outline=len(synth.get("outline") or []),
            out_tokens=s["usageByRole"]["researcher"]["outputTokens"],
            in_tokens=s["usageByRole"]["researcher"]["inputTokens"],
        )

verdict = {}
for task in TASKS:
    two = [r for r in J["results"] if r["kind"] == "pair" and r["task"] == task]
    v = {}
    for c in ["overall", "coverage", "support", "conflicts", "usefulness"]:
        a, b = two[0]["verdict"][c], two[1]["verdict"][c]
        v[c] = a if a == b and a != "tie" else "-"
    verdict[task] = v


def mean(arm, key):
    return st.mean(rows[(t, arm)][key] for t in TASKS)


print("WHAT A RESEARCHER WAS GIVEN (mean of the 12 real queries)")
for key, label in [("briefs", "researchers"), ("kq", "key questions in all"), ("kq_words", "words a key question"), ("obj_words", "words of an objective"), ("cons", "constraints a brief"), ("cons_words", "words of constraints a brief"), ("hints", "source hints a brief"), ("hint_words", "words a source hint"), ("hint_named", "share of hints that name a source"), ("instr_words", "words of instructions a brief")]:
    print(f"   {label:36s} baseline {mean('baseline', key):7.2f}   approach {mean('ebd-one', key):7.2f}")
print("\nWHAT THE RESEARCHERS DID (mean a run)")
for key, label in [("searches", "searches"), ("reads", "pages read"), ("queries", "queries recorded"), ("sources", "sources the tools reported"), ("cited_sources", "of them cited in the notes"), ("findings", "cited findings in the notes"), ("note_urls", "distinct links in the notes"), ("note_words", "words of notes"), ("in_tokens", "researcher input tokens"), ("out_tokens", "researcher output tokens")]:
    print(f"   {label:36s} baseline {mean('baseline', key):9.1f}   approach {mean('ebd-one', key):9.1f}")
print("\nWHAT THE REPORT HOLDS (mean a report)")
for key, label in [("rep_words", "words"), ("rep_links", "links"), ("rep_urls", "distinct links"), ("rep_hosts", "distinct sites"), ("used", "share of the notes' links used"), ("scholarly", "scholarly sites"), ("official", "official sites"), ("reference", "reference and forum sites"), ("other", "other sites"), ("heads", "sections"), ("tables", "tables"), ("guidance_words", "words of guidance to the writer"), ("outline", "outline entries")]:
    print(f"   {label:36s} baseline {mean('baseline', key):7.2f}   approach {mean('ebd-one', key):7.2f}")

print("\nPER QUESTION (approach minus baseline), with the judge's verdict in both orders")
print("   task overall  support  coverage | key questions  findings  note links  report links  scholarly+official  report words")
for task in TASKS:
    a, b = rows[(task, "ebd-one")], rows[(task, "baseline")]
    v = verdict[task]
    short = lambda x: {"ebd-one": "EBD", "baseline": "base", "-": "-"}[x]
    print(f"   {task}  {short(v['overall']):5s}   {short(v['support']):5s}   {short(v['coverage']):5s}   | {a['kq'] - b['kq']:+4d} ({a['kq']}/{b['kq']})  {a['findings'] - b['findings']:+4d} ({a['findings']}/{b['findings']})  {a['note_urls'] - b['note_urls']:+4d}  {a['rep_urls'] - b['rep_urls']:+4d} ({a['rep_urls']}/{b['rep_urls']})   {a['scholarly'] + a['official'] - b['scholarly'] - b['official']:+3d} ({a['scholarly'] + a['official']}/{b['scholarly'] + b['official']})   {a['rep_words'] - b['rep_words']:+5d}")

print("\nCONSTRAINTS OF THE BRIEFS, by what they are")
for arm in ARMS:
    kinds = {}
    for task in TASKS:
        _, briefs, _, _, _ = load(run[(task, arm)])
        for b in briefs:
            for c in b["constraints"]:
                k = "frame, assumed (meta)" if re.match(r"(Time frame|Place|Assumed purpose|Not stated by the client)", c) else "how to handle evidence" if re.search(r"\b(state|report|note|give|distinguish|separate|do not|prioriti[sz]e|prefer|use the most recent|compare)\b", c, re.I) else "scope"
                kinds[k] = kinds.get(k, 0) + 1
    print(f"   {arm:9s} " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
