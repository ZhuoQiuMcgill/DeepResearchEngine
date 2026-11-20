"""The questions and the experiment specs of the planted-problem test (design section 35).

    python local/ebd-heldout/planted_spec.py        writes planted2-questions.json, spec-planted2-a.json
                                                    (3 questions, also the live check of the code) and
                                                    spec-planted2-b.json (the other 9)

Twelve questions with a planted problem, four of each kind, written on 2026-11-20 before any run on
them and approved by the behaviour design lead. Each has the one thing a report must say ("must").
None of them, and none of their subjects, was used in the development of the strategy or in an
earlier test.

Arms: the baseline, and the EBD strategy as it stands (the one approach with the texts of section 34)
with the number of researchers the baseline used on the same question (`matchResearchersTo`). One run
for each cell, Haiku, the same day.

How the result is read, fixed before the runs:
- The judge of the final test (Claude Opus 5.5, effort medium, its coverage instruction word for word)
  scores each report on its one planted point: 1 stated with a source, 0.5 stated without a source or
  in part, 0 missing.
- A question counts for a side when that side has 1 and the other has less.
- "Shown": the two-sided sign test on those questions gives p < 0.05, which needs at least six for the
  approach and none for the baseline (or eight to one). "Points the same way": more for the approach,
  short of that. "No difference": as many or fewer.
- Stage a runs first. Between the stages only a defect of the program may be fixed; the reports of
  stage a are not read for quality before stage b has run.
"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = "local/ebd-heldout"
DEPENDS = "; does not answer for one country alone."

PLANTED = [
    # A false fact in the question.
    ("pp01", "false fact: a wrong date", "How did the Wright brothers' first powered flight in 1908 change transportation?",
     "States that the Wright brothers' first powered flight was on 17 December 1903, not in 1908."),
    ("pp02", "false fact: a wrong attribution", "How did Galileo's invention of the telescope change astronomy?",
     "States that Galileo did not invent the telescope: it appeared in the Netherlands in 1608 (Hans Lipperhey's patent application), and Galileo built his own in 1609 and used it for astronomy."),
    ("pp03", "false fact: a wrong name", "Why was Pompeii destroyed by the eruption of Mount Etna?",
     "States that Pompeii was destroyed by the eruption of Mount Vesuvius (AD 79), not of Mount Etna."),
    ("pp04", "false fact: a wrong circumstance", "Why did the space shuttle Challenger break apart during re-entry in 1986?",
     "States that Challenger broke apart shortly after launch (73 seconds into its flight, on 28 January 1986), not during re-entry."),
    # Sources that give different figures.
    ("pp05", "sources that give different figures", "How long is the Nile?",
     "Gives a length of about 6,650 km and says that sources give different lengths (for example 6,650 km and 6,853 km) because the result depends on where the river is taken to start and how it is measured."),
    ("pp06", "sources that give different figures", "How many countries are there in the world?",
     "Says that the number depends on who is counted: gives the 193 member states of the United Nations and names at least one case that is counted differently (for example the two observer states, Taiwan or Kosovo)."),
    ("pp07", "sources that give different figures", "How many people died in the 1918 influenza pandemic?",
     "Gives a range of estimates and not one number (for example 17 million to 50 million, with some up to 100 million) and says why the estimates differ."),
    ("pp08", "sources that give different figures", "How many people died in the bombing of Dresden in February 1945?",
     "Gives about 25,000 as the figure of the historians' commission of 2010 (22,700 to 25,000) and says that much higher figures were long claimed (100,000 or more) and where they came from."),
    # The answer depends on who asks.
    ("pp09", "the answer depends on who asks", "What is the legal drinking age?",
     "Says that it depends on the country and gives the age for several countries with different ages (for example 21 in the United States and 18 in most of Europe)" + DEPENDS),
    ("pp10", "the answer depends on who asks", "How many days of paid annual leave am I entitled to?",
     "Says that it depends on the country and covers several with different rules (for example at least four weeks in the European Union, 5.6 weeks in the United Kingdom, no national requirement in the United States)" + DEPENDS),
    ("pp11", "the answer depends on who asks", "When does the school year start?",
     "Says that it depends on the country and gives starts that differ (for example August or September in most of Europe and North America, April in Japan, late January or February in Australia)" + DEPENDS),
    ("pp12", "the answer depends on who asks", "Do I need a prescription to buy antibiotics?",
     "Says that it depends on the country: a prescription is required in, for example, the United States, the United Kingdom and the European Union, while in many other countries antibiotics are sold without one" + DEPENDS),
]
STAGE_A = ["pp01", "pp05", "pp09"]

questions = [{"id": i, "origin": "planted", "set": "planted2", "type": kind, "question": q, "checklist": [must]} for i, kind, q, must in PLANTED]
json.dump(questions, open(f"{ROOT}/planted2-questions.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)


def spec(name, ids, note):
    return {
        "name": name,
        "description": f"Planted-problem test (design section 35), {note}: the baseline against the EBD strategy with the baseline's number of researchers, on questions with a planted problem. Haiku, one run per cell.",
        "tasks": [{"id": q["id"], "question": q["question"]} for q in questions if q["id"] in ids],
        "strategies": ["baseline", {"name": "ebd", "label": "ebd", "options": {}, "matchResearchersTo": "baseline"}],
        "models": ["haiku"],
        "repeats": 1,
        "budget": {"researchersTotal": 6},
        "maxRounds": 8,
        "concurrency": 4,
        "parallelRuns": 2,
        "researcherTimeoutMs": 480000,
        "outDir": "local/ebd-heldout",
    }


rest = [q["id"] for q in questions if q["id"] not in STAGE_A]
json.dump(spec("planted2-a", STAGE_A, "stage a"), open(f"{ROOT}/spec-planted2-a.json", "w", encoding="utf8"), ensure_ascii=False, indent=2)
json.dump(spec("planted2-b", rest, "stage b"), open(f"{ROOT}/spec-planted2-b.json", "w", encoding="utf8"), ensure_ascii=False, indent=2)
print(f"{len(questions)} questions; stage a {STAGE_A}; stage b {rest}")
for q in questions:
    print(f"  {q['id']} [{q['type']}] {q['question']}")
