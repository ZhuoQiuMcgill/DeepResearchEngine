from docgen import Doc, REFS
OUT = '/mnt/d/Projects/DeepResearchEngine/docs/proposal/INSE691_Proposal_v0.3.1_EBD-DeepResearch.docx'
d = Doc('EBD-DeepResearch: A Multi-Agent Deep Research System Guided by Environment-Based Design', 'Project Proposal',
        'Haoxi Li, Zhuo Qiu, Kecheng Yao', '[ID 1], [ID 2], [ID 3]', '[Date: to be set by the team]', body_pt=10, margin=0.75)
d.para('Draft v0.3 for team review. Items in [square brackets] are still to be decided. A separate design document holds the implementation detail; this proposal stays at the level of concepts.', italic=True)
d.page_break()

d.h1('Objectives, Context and Scope')
d.h2('Objectives of the project')
d.para('"Deep research" is the name now used for AI assistants that do not answer a question from memory but go and find out: they run many web searches, read the pages they find, and write a report that cites its sources. OpenAI and Google sell this as a product, but neither has published how it works [6, 7]. Open-source alternatives exist, and we surveyed them (193 projects screened, 16 studied in depth). Almost all search in the same flat way: one plan, every search in that plan, a check whether the model has enough, then a report. Whatever the plan missed stays missed, and a larger budget does not help, because the system does not know what else to look for.')
d.para('This project builds an open-source deep research system that searches the way a good analyst does: it works out what it needs to know, looks for that, learns something, and then works out what it needs to know next. The method behind this is Environment-Based Design (EBD), developed by Prof. Yong Zeng at Concordia [1, 4]. EBD says that to understand a problem you describe the objects in it, the relations between them, and the environment around them; you then look for conflicts between what you assumed and what you find, and resolve them; and you repeat until nothing is left unresolved [2, 3]. Recent work in the lab shows that a language model can carry out these steps [5]. Applied to research, EBD turns searching into a tree that grows one round at a time, with EBD deciding which branches deserve the next share of the budget.')
d.para('We will compare it with a baseline that searches the flat way, on the same tasks, with the same budget and the same models, and have the reports judged blind. The objectives are:')
d.bullets([
    ('O1. ', 'Build a working multi-agent deep research system whose search is guided by EBD.'),
    ('O2. ', 'Build a flat-search baseline that shares everything except the decision-making, so that the comparison is fair.'),
    ('O3. ', 'Run both on two models, an API model (DeepSeek-V4.1-Flash) and a locally hosted open-weight model (Qwen 3.8-27B), over nine research tasks, and have the reports judged blind by three independent language models (Claude Opus 5, GPT-5.6-sol, Gemini 3.8 Flash).'),
    ('O4. ', 'Deliver a console that shows what happened in every run, and documentation that lets the project grow into a paper.'),
])

d.h2('Context and Scope statement')
d.para('The easiest way to understand the design is as a small company whose business is finding things out. A client brings a topic they care about, and the company returns a report. The company has positions, and every position has a job description: what it receives, what it must produce, what it is allowed to look at, and which tools it may use. This is the definition of an agent applied literally: an agent is a bundle of knowledge, problem solving, interaction and communication, connected to a model and to tools, and living in an environment. Because a position is defined by its job description and not by who fills it, any position could be filled by a person or by a language model and the company would still run. That interchangeability is what makes the system agentic rather than a script. The job descriptions are the behaviour design; the workflow, the rules and the tool contracts are the orchestration; and the company records are the environment of the agent-based model.', lead='The system as a company. ')
d.para('The positions are:', lead='Positions. ')
d.bullets([
    ('Front desk. ', 'Receives the client\'s request. In our experiments the request is a fixed task text, so this is an interface rather than a person.'),
    ('Analyst. ', 'The senior position. Uses EBD to break the request into objects, relations and environment (the client\'s purpose, time frame and scope), turns every unknown object and unverified relation into a search goal, judges the value of each goal, and decides when the research is finished.'),
    ('Analyst\'s assistant. ', 'A temporary copy of the Analyst, created when a decision would flood the Analyst with detail, such as choosing twenty pages out of fifty candidates. It sees the same knowledge, decides, records the decision, and is dismissed, so the Analyst\'s working memory stays clean.'),
    ('Searchers. ', 'Each takes one goal, runs web searches, and reports the candidate pages worth reading.'),
    ('Finance. ', 'A rule, not a person. It counts candidates against the round budget and calls the assistant when there are more candidates than budget.'),
    ('Readers. ', 'Each fetches one page and extracts the evidence that matters for its goal, quoting the source. If a page is too long for one reader, the rules split it and several readers share it.'),
    ('Conflict checker. ', 'Compares new evidence with what the company already believes and with the client\'s own assumptions, and flags disagreements instead of smoothing them over.'),
    ('Writer. ', 'Takes the Analyst\'s final list of what belongs in the report, pulls the evidence for each item from the records, and writes the report with citations, saying openly where sources disagree.'),
    ('Records. ', 'The company database. Every search, page, piece of evidence, decision and message is written down automatically by the system, not by the employees. A position can read only the part of the records its job description allows, and write only what its job produces.'),
])
d.para('Suppose the client allows 100 page fetches in total and the rules allow 20 per round. The Analyst reads the request and produces the first set of goals. Searchers run their searches and return, say, 50 candidate pages. Finance sees 50 against 20 and calls the assistant, who picks the 20 most valuable. Readers fetch and distill them. The Analyst receives the distilled evidence, updates its picture, and finds that one object has three parts it knew nothing about; those become new goals. The 30 unread candidates stay in the pool and compete with the new ones next round. After every round the Analyst re-ranks every open goal, so the budget always flows to the most valuable branch, wherever it sits in the tree. The mission ends when no goal is worth pursuing or the budget is gone. A flat system would have stopped after one or two rounds, satisfied, with most of the budget unspent and most of the topic unexplored.', lead='How a mission runs. ')
d.para('The baseline is the flat design common in open-source systems: one plan, parallel searches, a "do we have enough" check, then a report. It uses the same positions where they exist, the same records, tools, budget and models. Only the Analyst\'s method differs, so any difference in the reports is attributable to EBD.', lead='Baseline. ')
d.para('H1: with the same budget, the EBD system finds contradictions between sources, and false assumptions in the question, that the baseline misses. H2: blind judges rate its reports at least as good on coverage and citation accuracy. H3: it stops on its own condition more often, rather than on the budget. H4: the benefit is larger on the smaller local model.', lead='Hypotheses. ')
d.para('In scope: the company, the baseline, the records, the console, and the evaluation. Out of scope: training models, browser automation, paywalled content, a chat product, and non-English or multimodal tasks.', lead='Scope. ')

d.h2('The seven agent-based modelling questions')
d.para('1. Problem and value: a cited report on a topic whose evidence is scattered, contradictory, or at odds with the question\'s own assumptions; interacting agents let each round depend on what the last one found, which a chatbot and a script cannot.')
d.para('2. Agents: the positions above; the Analyst and its assistant are the decision makers; static attributes are the job description, tools and budget, dynamic attributes are what a position currently knows and has spent.')
d.para('3. Environment: the company records plus the web, sensed through permitted reads and tools, acted on by permitted writes; movement through space becomes movement through the topic.')
d.para('4. Behaviours: analysing, choosing goals, ranking candidates, searching, extracting evidence, checking conflicts, writing; exact work such as budgets and page splitting is done by rules, judgment by the model.')
d.para('5. Interactions: positions pass work along the workflow and through the records, with the Analyst at the centre as the one point of control.')
d.para('6. Data: behaviours from the EBD literature and the surveyed systems; the live web, cached so runs can be repeated; nine authored tasks with planted contradictions whose answers we know.')
d.para('7. Validation: each position tested on its own job, the company compared with the baseline under blind judging, and every run replayable from the records to check what was observed and decided.')

d.h2('Stakeholder profiles')
d.para('End users are students, analysts and engineers who need reports they can trust and trace. The instructor and teaching assistant assess the project. Prof. Zeng\'s design lab owns the EBD method and wants evidence that it improves information seeking. The team are the first users, and the open-source community can reuse the tasks, prompts and code.')

d.h1('Product and deliverables')
d.para('The company itself, released as open-source software that runs from the command line in EBD or baseline mode on either model. A mission console that replays any run from the records: who did what, when, with which tool, what they found and decided. An evaluation kit with the nine tasks, rubrics, judge prompts and scripts. A testing report, a user manual, a developer guide, and the final report and presentation.')

d.h1('Important tasks to be completed')
d.para('Five areas. Behaviour design: the job descriptions and the EBD decisions inside the Analyst. Orchestration: the workflow, rules such as Finance, the interfaces between positions, and the baseline. Environment: the records, the search and fetch tools, and both models. Evaluation: tasks, rubrics, judging and statistics, once per model. Console and documentation: the mission console, tests, manuals and the final report.')

d.h1('Project process activities, schedule and milestones')
d.para('We work in weekly increments over nine weeks and freeze the scope at week six. The first two weeks fix the design and the interfaces; weeks three to five build the company and the baseline; week six freezes the tasks; weeks seven and eight run the experiments and judging; week nine is the report and presentation. Calendar dates will be added when the course schedule is confirmed [final report due mid-December 2026].')
d.gantt([('Design and interfaces', 1, 2), ('Environment: records, tools, models', 1, 4), ('Behaviour: positions and EBD decisions', 2, 5), ('Orchestration and baseline', 2, 5),
         ('Evaluation kit and tasks', 3, 6), ('Mission console', 4, 8), ('Experiments and judging', 6, 8), ('Report and presentation', 8, 9)], 9,
        [('M1', 2), ('M2', 5), ('M3', 6), ('M4', 8), ('M5', 9)],
        'Figure 1. Schedule by project week. M1 design frozen; M2 company and baseline run end to end; M3 tasks frozen; M4 experiments judged; M5 report submitted.')

d.h1('Project team organization')
d.para('Haoxi Li leads behaviour design: the job descriptions and the EBD decisions. Zhuo Qiu is the system architect and leads orchestration: interfaces, workflow, rules and the baseline, and runs the evaluation on the API model. Kecheng Yao leads the environment: records, tools and model hosting, and runs the evaluation on the local model. Zhuo and Kecheng build the mission console together. Each member writes the tests and documentation for their own area; the final report is shared.')

d.h1('Development risks')
d.para('The local model may follow instructions less reliably than the API model; the rules check every output and the API model is the reference. The local machine produces about 100 tokens per second; runs go overnight and repeats per task can be reduced. Web search can be blocked; every result is cached and a paid service is the fallback. Model judges have known biases; judging is blind, each pair is judged in both orders, and the team spot-checks a sample by hand. Nine tasks give limited statistical power, so results are presented as a pilot. Time is short, so scope is frozen at week six and the console is built in its minimum form first.')

d.h1('Control methods')
d.para('A weekly meeting reviews milestones, the task board and the risk list, with written minutes. Code goes through pull-request review and automated tests. The records of every experiment run are kept and frozen once judged, so results cannot drift. The hypotheses and metrics above are fixed now, before any experiment runs. The instructor is consulted at milestones M1, M3 and M5.')
d.references(REFS)
d.save(OUT)
h, pages = d.estimate(); print(f'v0.3 body: {h:.1f} in, about {pages:.2f} pages')
