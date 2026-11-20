"""Copy the evaluation record of the EBD strategy from this machine's run folders into the repository
(src/strategies/ebd/evaluation/), so that the team has the questions, the judge's output, the reports
and the tables behind every number in the documentation. No model call. Nothing with a path of this
machine is written: run folders are named by their test, question and side.

    python local/ebd-heldout/export_evaluation.py

Written: questions/, judgments/, reports/, tables/, scripts/ and runs.csv. The README of the folder is
written by hand and is not touched.
"""
import csv
import glob
import json
import os
import re
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
R = "local/ebd-heldout"
OUT = "src/strategies/ebd/evaluation"
MACHINE = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\"'\s]+[\\/]+Downloads[\\/]+Github[\\/]+DeepResearchEngine[\\/]+", re.I)


def clean(text):
    """A path of this machine becomes a path from the repository root."""
    return MACHINE.sub("", text)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf8", newline="\n") as f:
        f.write(text if text.endswith("\n") else text + "\n")


def copy_json(src, dst):
    data = json.load(open(os.path.join(R, src), encoding="utf8"))
    write(os.path.join(OUT, dst), clean(json.dumps(data, ensure_ascii=False, indent=1)))


# ------------------------------------------------------------------ questions and judgments
QUESTIONS = {
    "final-sealed-questions.json": "questions/final-test-real-queries.json",
    "final-planted-questions.json": "questions/final-test-planted.json",
    "planted2-questions.json": "questions/planted-problem-test.json",
    "nano-questions.json": "questions/weaker-model-run.json",
    "questions.json": "questions/test-of-2026-11-18.json",
    "fresh-questions.json": "questions/plan-check-2026-11-19.json",
}
JUDGMENTS = {
    "judge-final-results.json": "judgments/final-test.json",
    "judge-rewrite-defs.json": "judgments/writer-input-check.json",
    "judge-planted2.json": "judgments/planted-problem-test.json",
    "nano-scores.json": "judgments/weaker-model-run.json",
    "judge-results.json": "judgments/test-of-2026-11-18.json",
}
for src, dst in {**QUESTIONS, **JUDGMENTS}.items():
    copy_json(src, dst)

# ------------------------------------------------------------------ runs and reports
TESTS = [
    ("final-test", ["final-planted-2", "final-sealed-2"], {"ebd-one": "ebd"}),
    ("planted-problem-test", ["planted2-a-2", "planted2-b-2"], {}),
    ("weaker-model-run", ["nano-a-2", "nano-b-2"], {}),
]
qtext = {}
for f in QUESTIONS:
    for q in json.load(open(os.path.join(R, f), encoding="utf8")):
        qtext.setdefault(q["id"], q["question"])

rows = []
shutil.rmtree(os.path.join(OUT, "reports"), ignore_errors=True)


def add_run(test, s, side):
    report = os.path.join(s["dir"], "report.md")
    text = open(report, encoding="utf8").read() if os.path.exists(report) else ""
    task = s["tags"].get("task", "")
    if text:
        write(os.path.join(OUT, "reports", test, f"{task}-{side}.md"), text)
    usage = s["usageByRole"]
    code = s.get("code") or {}
    rows.append({
        "test": test,
        "question_id": task,
        "question": s.get("question") or qtext.get(task, ""),
        "side": side,
        "model": s.get("model", ""),
        "status": s["status"],
        "stop": s.get("stopReason", ""),
        "researchers_used": s["researchersUsed"],
        "researchers_allowed": s["researchersBudget"],
        "rounds": s["rounds"],
        "searches": s["searches"],
        "page_reads": s["pageReads"],
        "strategy_calls": usage.get("strategy", {}).get("calls", 0),
        "input_tokens": sum(u["inputTokens"] for u in usage.values()),
        "output_tokens": sum(u["outputTokens"] for u in usage.values()),
        "cost_usd_platform_estimate": round(s["costUsdEstimate"], 4),
        "seconds": round(s["durationMs"] / 1000),
        "report_words": len(text.split()),
        "report_links": len(re.findall(r"\]\((https?://[^)\s]+)\)", text)),
        "links_not_in_notes": len((s.get("citationCheck") or {}).get("unknownUrls", [])),
        "run_id": s["runId"],
        "code_commit": (code.get("commit") or "")[:7] + (" + uncommitted changes" if code.get("dirty") else ""),
    })


for test, prefixes, rename in TESTS:
    for prefix in prefixes:
        folders = sorted(d for d in glob.glob(f"{R}/{prefix}*") if os.path.exists(os.path.join(d, "summaries.json")))
        for s in json.load(open(os.path.join(folders[-1], "summaries.json"), encoding="utf8")):
            add_run(test, s, rename.get(s["strategy"]["label"], s["strategy"]["label"]))

# The acceptance checks of the final code (the platform's check-strategy), when they have been run.
for model in ("haiku", "luna"):
    log = os.path.join(R, f"check-{model}.log")
    if not os.path.exists(log):
        continue
    m = re.search(r"local[\\/]checks[\\/]([\w.-]+)", open(log, encoding="utf8", errors="replace").read())
    folder = os.path.join("local", "checks", m.group(1)) if m else ""
    if folder and os.path.exists(os.path.join(folder, "summary.json")):
        s = json.load(open(os.path.join(folder, "summary.json"), encoding="utf8"))
        s.setdefault("dir", folder)
        s.setdefault("tags", {})["task"] = "ebd-question"
        add_run("acceptance-check", s, f"ebd-{model}")
        write(os.path.join(OUT, "tables", f"acceptance-check-{model}.txt"), clean("\n".join(l for l in open(log, encoding="utf8", errors="replace").read().splitlines() if re.match(r"\s*(PASS|FAIL|WARN|Run|Record|exit|\d+ check)", l))))

# The reports written again from the saved notes with the writer input of section 34, which the judge compared (section 33.9).
for f in sorted(glob.glob(f"{R}/rewrite-final-defs/*.md")):
    write(os.path.join(OUT, "reports", "writer-input-check", os.path.basename(f).replace(".md", "-ebd-rewritten.md")), open(f, encoding="utf8").read())

with open(os.path.join(OUT, "runs.csv"), "w", encoding="utf8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)

# ------------------------------------------------------------------ the printed tables
TABLES = {
    "final-test.txt": ["final_stats.py"],
    "final-test-rules-check.txt": ["final_check.py", f"{R}/final-planted-20261120-022344", f"{R}/final-sealed-20261120-023629"],
    "final-test-what-the-records-show.txt": ["why.py"],
    "writer-input-rewrites.txt": ["rewrite_stats.py"],
    "writer-input-check.txt": ["judge_rewrite_stats.py", "defs", "--reasons"],
    "writer-input-replay.txt": ["texts_check.py"],
    "planner-rules-check.txt": ["plancheck_stats.py"],
    "planted-problem-test.txt": ["planted2_stats.py", "--quotes"],
    "planning-probe-weaker-models.txt": ["weaker_probe_stats.py"],
    "weaker-model-run.txt": ["nano_stats.py"],
    "switches-replay.txt": ["switch_check.py"],
}
for name, cmd in TABLES.items():
    out = subprocess.run([sys.executable, os.path.join(R, cmd[0]), *cmd[1:]], capture_output=True, text=True, encoding="utf8", errors="replace")
    # final_check.py ends with a non-zero code when it lists a recorded problem; its table is still the record.
    if out.returncode != 0 and not out.stdout.strip():
        print(f"   {name}: the script failed: {out.stderr.strip()[-300:]}")
        continue
    write(os.path.join(OUT, "tables", name), clean(out.stdout))

# ------------------------------------------------------------------ the scripts, for the record
SCRIPTS = [
    "sample.py", "sample2.py", "final_spec.py", "judge.ts", "judge-final.ts", "final_stats.py", "final_check.py", "golden.ts", "matched-round1.ts",
    "why.py", "rewrite-final.ts", "rewrite_stats.py", "screen-final.ts", "cover-screen.ts", "judge-rewrite.ts", "judge_rewrite_stats.py", "texts_check.py",
    "deepread.ts", "plancheck.ts", "plancheck_stats.py", "planted_spec.py", "planted2_stats.py", "planted-screen.ts",
    "weaker-probe.ts", "weaker_probe_stats.py", "nano-run.ts", "nano_spec.py", "nano_stats.py", "switch_check.py", "export_evaluation.py",
]
shutil.rmtree(os.path.join(OUT, "scripts"), ignore_errors=True)
for name in SCRIPTS:
    path = os.path.join(R, name)
    if not os.path.exists(path):
        print(f"   script not found: {name}")
        continue
    # A .ts file here would be built by the project's type check, which covers all of src/; the copies are kept as text.
    write(os.path.join(OUT, "scripts", name + (".txt" if name.endswith(".ts") else "")), clean(open(path, encoding="utf8").read()))

# ------------------------------------------------------------------ nothing of this machine in what was written
bad = []
for path in glob.glob(os.path.join(OUT, "**", "*"), recursive=True):
    if os.path.isfile(path):
        text = open(path, encoding="utf8", errors="replace").read()
        if re.search(r"[A-Za-z]:[\\/]+Users|sk-[A-Za-z0-9]{20}|@qq\.com|API_KEY\s*=\s*\S", text):
            bad.append(path)
size = sum(os.path.getsize(p) for p in glob.glob(os.path.join(OUT, "**", "*"), recursive=True) if os.path.isfile(p))
print(f"{len(rows)} runs in runs.csv; {sum(len(fs) for _, _, fs in os.walk(os.path.join(OUT, 'reports')))} reports; {size / 1024:.0f} KB in {OUT}")
print("files with a path of this machine or something that looks like a key:", bad or "none")
