from docgen import Doc, REFS
OUT = '/mnt/d/Projects/DeepResearchEngine/docs/proposal/EBD-DeepResearch_Design_v0.1.docx'
d = Doc('EBD-DeepResearch Design Document', 'Design Document (internal)', 'Haoxi Li, Zhuo Qiu, Kecheng Yao', '[ID 1], [ID 2], [ID 3]', 'v0.1, 2026-09-17', body_pt=10.5, margin=0.9)
d.para('Purpose. This document holds the full design of EBD-DeepResearch for the team. The three-page proposal explains the idea to the instructor; this document is where the mechanism of every position is written out, where decisions already taken are recorded, and where the open design questions are assigned to their owners. Items marked DECIDED reflect team decisions of 16 and 17 September 2026. Items marked OPEN name an owner and must be settled before the code that depends on them is written.', italic=True)
d.page_break()

d.h1('1. The idea')
d.para('Think of a small company whose only business is finding things out. A client brings a topic they care about and receives a report. Inside the company there are positions: a front desk that receives the request, an analyst who works out what needs to be known, searchers who look for it, readers who extract what the pages actually say, a checker who notices when findings disagree, a writer who produces the report, and a records system that writes down everything that happens. Each position has a job description that says what it receives, what it must produce, what it may look at, and which tools it may use. Whoever fills the position, a person or a language model, the company runs the same way. That is the property the course calls agentic: the system is defined by roles, rules and an environment, not by a single script.', lead='The company. ')
d.para('The open-source deep research systems we surveyed almost all search in a flat way. The system makes one plan of sub-questions, searches all of them in parallel, asks the model whether the findings are sufficient, and writes. Give such a system a budget of 100 page fetches and it may spend 20 on the first round, 10 on a second, declare itself satisfied, and stop with 70 unspent. The budget was not the limit; knowing what else to look for was. The plan was made before anything was learned, so nothing learned can change it.', lead='Why flat search fails. ')
d.para('In our design the search is a tree that grows one round at a time. The Analyst applies Environment-Based Design (EBD) to the request: it identifies the objects the request is about, the relations claimed between them, and the environment the answer must respect (the client\'s purpose, time frame and scope). Every object not yet understood and every relation not yet verified becomes a goal. A round of searching and reading follows. The evidence that comes back changes the picture: an object turns out to have three parts, a relation turns out to be disputed, a new object appears that nobody mentioned. Those become new goals. After every round the Analyst re-ranks all open goals by how much they matter to the client\'s target, and the next share of the budget goes to the most valuable ones, wherever they are in the tree. This is neither depth-first nor breadth-first search. It is a priority search in which the priorities are recomputed by EBD after every round. The mission ends when nothing worth knowing is left open or the budget is gone.', lead='The tree. ')
d.para('We claim that, with the same budget, the same tools and the same model, a company run this way produces better-grounded reports than a flat system: it finds contradictions between sources and false assumptions in the question that flat systems miss, and it knows when it is done. We test the claim with a matched baseline, two models, nine tasks and blind judging (section 7).', lead='The claim. ')

d.h1('2. Mapping to the course framework')
d.table(['Course concept (Module 1)', 'Where it appears in EBD-DeepResearch'], [
    ['Agent = knowledge + problem solver + interaction + communication, with a model and tools, in an environment (slides 6, 11)', 'A position. Its knowledge is what the records let it read; its problem solver is its job description and the model; its interaction is its tools; its communication is the messages it passes along the workflow.'],
    ['LLM, then agent, then agent system (slide 10)', 'The model alone answers from memory; a position is a model with a goal, instructions, tools and a control loop; the company is positions pursuing goals through observe, reason, act, adapt.'],
    ['Agent-based model = agents (attributes, behaviours) + interaction protocols + environment (slide 19)', 'Positions with job descriptions; the workflow and message formats; the records plus the web.'],
    ['Five components: model, instructions, tools, state, control loop (slide 57)', 'Per position: the model adapter, the job description, the tools it may call, its view of the records, and the round loop that calls it.'],
    ['Context, state and memory are not synonyms (slide 59)', 'Context is what one call is shown; state is the records; memory across missions (client preferences) is out of scope for the experiments.'],
    ['What a dependable system adds (slide 49)', 'Observations from search and fetch; deterministic computation in the rules; persistent state in the records; validation of every output; constraints from the client\'s environment and budgets; explicit stopping conditions.'],
    ['Split only for a reason (slide 63)', 'Context overload (one page can exceed the window), independent parallel work (one searcher per goal), required checks (the conflict checker).'],
    ['The coordinator preserves and resolves disagreement (slide 66)', 'The conflict checker records disagreements; the Analyst resolves them by asking again or by reporting them as disputed.'],
], widths=[2.6, 4.1], font=9)

d.h1('3. Positions in full')
d.para('For each position: what fills it, what it receives, what it produces, what it may read and write in the records, which tools it may call, and which decisions belong to it. "Rule" means a fixed program with no model call. "Model" means a language-model call under a job description. Every model call passes through the context gate (section 5) and every action and decision is recorded (section 5).')
d.h2('3.1 Front desk')
d.para('DECIDED. An interface, not a position with judgment. It receives the client\'s request and the client\'s environment (purpose, time frame, scope, budget) and opens a mission in the records. In experiments the request is the fixed task text and the front desk is bypassed. A future version may put a person or a model here to clarify requests with the client.')
d.h2('3.2 Analyst')
d.para('Filled by a model. The senior position and the only one that sees the whole picture. Receives: the request and client environment; after each round, the distilled evidence and the checker\'s findings. Produces: the task model (objects, relations, environment components, each with a status), the list of open goals with their values, the resolutions of conflicts, the decision to continue or stop, and the report list for the Writer. May read: the task model, goals, goal summaries and conflict records. May not read raw pages, raw search results or individual evidence records; those reach it only as distilled summaries. May write: task model, goals, decisions, report list. Tools: none beyond reading its part of the records. Decisions: what the request is about; which goals exist; the value of each goal; when a node is done; when the mission ends.')
d.bullets([
    ('DECIDED. ', 'The Analyst re-ranks all open goals after every round, using the knowledge accumulated so far. The behaviour is that of a priority queue: the highest-value goal is always served first, until the budget runs out.'),
    ('DECIDED. ', 'A node can be re-opened with an added condition when new knowledge shows it deserves more depth. Its unread candidates remain in the pool and new searches under the condition are added to them.'),
    ('DECIDED. ', 'A node counts as exhausted for now when what lies beneath it has drifted far from the client\'s target. This is a judgment made each round, so a node exhausted in one round can be re-opened later if findings elsewhere raise its value.'),
    ('OPEN, Haoxi. ', 'The value function for goals (H-3), the criterion for creating a new goal from evidence (H-2), the node-done criterion (H-5), and the form of the task model (H-1). See section 8.'),
])
d.h2('3.3 Analyst\'s assistant')
d.para('Filled by a model, created on demand and dismissed after one decision. Purpose: to make decisions that need the Analyst\'s knowledge but would fill the Analyst\'s working memory with detail it should never see, such as choosing which candidate pages to fetch.')
d.bullets([
    ('DECIDED. ', 'Mechanism: the assistant is a branch of the Analyst\'s current state. The rules read the Analyst\'s permitted view of the records at this point of the round (task model, open goals with values, goal summaries), attach a temporary job description for the one decision to be made, and call the model. The decision and its reasons are written to the records. The branch is then discarded. Nothing is copied from the Analyst\'s conversation; the state is read from the records, which is why it fits in a 128K window.'),
    ('DECIDED. ', 'The assistant decides directly. Its choice is final for the round and is not sent back to the Analyst for approval.'),
    ('DECIDED. ', 'The assistant is called only when a decision is needed: when candidates exceed the round budget. If they do not, all candidates are fetched and no assistant is created.'),
    ('OPEN, Haoxi. ', 'What the assistant considers when ranking candidates (H-4): relevance to the goal, source quality, novelty against what has already been fetched, and cost.'),
])
d.h2('3.4 Searchers')
d.para('Filled by a model, one instance per goal, running in parallel. Receives: one goal, with its condition if any. Produces: the search queries it chose and a list of candidate pages with title, address, snippet and the reason each is worth reading. May read: its goal and its own past queries for this goal. May write: candidates. Tools: web search. Decisions: which queries to run, which results are worth proposing as candidates. It does not fetch pages and does not read them.')
d.para('DECIDED. Candidates from all searchers go into one shared pool for the mission, not one pool per goal. Candidates proposed under an earlier search for the same goal and not yet fetched stay in the pool. When a goal is searched again, the rules remove duplicates by address against everything already in the pool and everything already fetched.')
d.h2('3.5 Finance')
d.para('DECIDED. A rule, not a position with judgment. It holds the mission budget (for example 100 fetches) and the round budget (for example 20). After the searchers report, it counts the pending candidates in the pool. If the count is at or below the round budget, all are dispatched. If it is above, Finance calls the assistant to choose. It records every dispatch and every remaining balance. It also enforces token and time budgets per position. There are no model calls inside Finance.')
d.h2('3.6 Readers')
d.para('Filled by a rule and a model together. Receives: one candidate page to fetch and the goal it serves. The rule part fetches the page, stores it, estimates its size in tokens, and compares it with the reader\'s context budget. If the page fits, one model call extracts the evidence. If it does not, the rule splits the page into chunks that fit, with some overlap so that a fact cut at a boundary survives, and assigns one reader call per chunk; afterwards the rule merges the evidence and removes duplicates across chunks. Produces: evidence records, each a quoted passage with its page, position, goal and a one-line reading of what it shows. May read: its chunk and its goal. May write: evidence. Tools: fetch (through the rule). Decisions: what in the text counts as evidence for the goal.')
d.bullets([
    ('DECIDED. ', 'A reader never sees more than one chunk. It does not decide what to fetch; that decision was made upstream.'),
    ('DECIDED. ', 'When one page serves several goals, the rules attach a temporary job description that lists all the goals, so a single reading extracts evidence for each of them instead of reading the page several times.'),
    ('DECIDED. ', 'The reader\'s context budget is set per model by the environment owner (K-3) and is the number the chunker uses.'),
])
d.h2('3.7 Conflict checker')
d.para('Filled by a model. Receives: the task model and the new evidence of the round. Produces: conflict records, each naming the two things that disagree, quoting the evidence on both sides, classifying the conflict, and proposing a resolution. May read: task model, evidence, existing conflicts. May write: conflicts. Decisions: whether two things actually disagree, of what kind the disagreement is, and what would settle it.')
d.bullets([
    ('DECIDED. ', 'A conflict must quote evidence on both sides or it is not recorded. This is enforced by the rules, not only by the job description.'),
    ('DECIDED. ', 'Disagreements are preserved and resolved, never averaged. A conflict that cannot be settled within the budget is reported in the final report as disputed, with both sides cited.'),
    ('OPEN, Haoxi. ', 'The conflict typology and where in the round the checker runs (H-6). Candidate types: two sources disagree; evidence refutes an assumption in the request; evidence violates a client constraint such as time frame or scope; a source is about a different thing than the goal; two values are both true at different times.'),
])
d.h2('3.8 Writer')
d.para('Filled by a model. Receives: the report list registered by the Analyst, which names the items the report must cover and their order. Produces: the report. For each item the rules pull the evidence from the records and hand it to the Writer one section at a time, so that a large mission never exceeds the window. May read: the report list, the task model, evidence and conflicts for the current section. May write: report sections. Decisions: how to phrase and organise each section, which evidence to cite for each claim, and how to present disputes. The Writer cannot introduce a claim without a citation; the rules check that every citation points at an evidence record.')
d.para('OPEN, Haoxi. What exactly the Analyst registers in the report list and how it is ordered (H-7).')
d.h2('3.9 Records')
d.para('DECIDED. The company database, kept in SQLite and owned by the rules. Positions do not write to it directly; every action a position takes passes through the rules, which write the corresponding record and an event. See section 5.')
d.h2('3.10 Summary of positions')
d.table(['Position', 'Filled by', 'Receives', 'Produces', 'Reads', 'Decides'], [
    ['Front desk', 'Interface', 'Client request, client environment', 'Mission record', 'Nothing', 'Nothing'],
    ['Analyst', 'Model', 'Request; distilled evidence; conflicts', 'Task model, goals with values, resolutions, stop decision, report list', 'Task model, goals, summaries, conflicts', 'Goals, values, node done, mission end'],
    ['Assistant', 'Model, temporary', 'Analyst\'s state; one decision to make', 'One decision with reasons', 'Same as Analyst, at that moment', 'The decision asked for'],
    ['Searcher', 'Model, one per goal', 'One goal', 'Queries; candidates', 'Its goal, its past queries', 'Queries; which results are candidates'],
    ['Finance', 'Rule', 'Candidate pool; budgets', 'Dispatch list; balances', 'Pool, budgets', 'Nothing (arithmetic and thresholds)'],
    ['Reader', 'Rule + model', 'One candidate; its goal(s)', 'Evidence records', 'Its chunk, its goal(s)', 'What counts as evidence'],
    ['Conflict checker', 'Model', 'Task model; new evidence', 'Conflict records', 'Task model, evidence, conflicts', 'What disagrees and how to settle it'],
    ['Writer', 'Model', 'Report list; evidence per section', 'Report', 'Report list, evidence, conflicts', 'Phrasing, citations, disputes'],
], widths=[0.9, 0.9, 1.3, 1.5, 1.1, 1.0], font=8)

d.h1('4. The mission loop')
d.para('DECIDED. Rounds are synchronous: a round ends only when every dispatched page has been read and the checker has run. The Analyst then updates the task model, re-ranks the goals, and the next round begins. Asynchronous rounds would be faster but would make the records and the replay much harder to reason about.')
d.h2('4.1 One round, step by step')
d.bullets([
    ('1. Analyse. ', 'The Analyst reads the request (first round) or the new distilled evidence and conflicts (later rounds), updates the task model, creates or re-opens goals, re-ranks all open goals, and decides whether to continue. If it stops, go to step 8.'),
    ('2. Search. ', 'One searcher per open goal selected for this round runs its queries and proposes candidates. The rules remove duplicates and add the rest to the shared pool as pending.'),
    ('3. Count. ', 'Finance counts pending candidates against the round budget and the remaining mission budget.'),
    ('4. Choose. ', 'If pending candidates exceed the round budget, an assistant is branched from the Analyst\'s state and chooses which to fetch. Otherwise all pending candidates are dispatched. Unchosen candidates stay pending.'),
    ('5. Read. ', 'For each dispatched candidate the reader rule fetches, sizes and if necessary splits the page; reader calls extract evidence; the rule merges and stores it. Candidates become fetched.'),
    ('6. Summarise. ', 'For each goal served this round, the rules assemble its new evidence and a searcher call writes a goal summary for the Analyst, so the Analyst never sees raw evidence.'),
    ('7. Check. ', 'The conflict checker compares new evidence with the task model and with earlier evidence and records conflicts. (Placement OPEN, Haoxi, H-6: before or after step 6.)'),
    ('8. Write. ', 'When the Analyst stops, it registers the report list; the Writer produces the report section by section; the rules verify citations; the mission closes.'),
])
d.h2('4.2 The candidate pool')
d.para('DECIDED. One pool per mission, shared by all goals. Each candidate carries the goal it was proposed for, the query that found it, its state (pending, fetched, dropped) and the history of scores it received. Candidates are never deleted while a mission runs. Because the pool is shared, a goal whose candidates are consistently judged more valuable can take a whole round\'s budget; if it deserves it, that is correct, and goals whose candidates were not chosen compete again next round with whatever the assistant then knows. Duplicate addresses are removed at entry, which also covers the case where a goal searched again under a new condition returns pages already in the pool.')
d.h2('4.3 Stopping')
d.para('DECIDED. A mission ends for one of these reasons, and the reason is recorded: the Analyst judges that no open goal is worth pursuing; the mission budget is exhausted; a decision is needed that only the client can make; or a hard safety limit on rounds is reached. Every ending leads to the Writer, so the client always receives a report, with the ending reason stated in it. Evidence insufficient for an item is reported as insufficient, not filled in from the model\'s memory.')
d.h2('4.4 A worked example')
d.para('The client allows 100 fetches; the round budget is 20. Round 1: the Analyst finds four objects and two claimed relations in the request; six goals. Six searchers propose 50 candidates. Finance sees 50 against 20 and branches an assistant, which chooses 20. Readers extract evidence; two pages are split into three chunks each. The checker finds that two sources give different dates for one event. The Analyst learns that one object has three components it did not know, opens three goals for them, marks one original goal as done, and keeps the date conflict open as a goal with the condition "which date holds as of the client\'s time frame". Round 2: nine searchers; 30 old candidates plus 41 new ones; the assistant chooses 20, including several from the old 30 that now look more valuable given what was learned. Rounds 3 to 5 continue the same way. After round 5 the budget is spent; the Analyst registers the report list, including the date conflict, now resolved, and one component that could not be settled and is reported as disputed. A flat system would have searched the six original goals, fetched 20 or 30 pages, and written, never learning about the three components.')

d.h1('5. Records: the environment')
d.para('DECIDED. Principles: the rules own all state; positions hold nothing between calls. Every action and decision by a position is appended to the records as an event carrying the position, the time, references to what it was shown, what it produced, the model used and the cost. Records are append-only; status changes are new events, so any moment of a mission can be reconstructed. Each position has read and write rights on part of the records, and those rights are its interaction with the environment. A run can be replayed from the records and the page cache without touching the network.')
d.h2('5.1 What is recorded')
d.table(['Record', 'Content', 'Written by'], [
    ['Mission', 'Request, client environment, budgets, model configuration, ending reason', 'Front desk; Finance'],
    ['Task model', 'Objects, relations, environment components, each with a status and the evidence that set it', 'Analyst (through rules)'],
    ['Goals', 'The tree: goal, parent, condition, current value, status (open, served, done, re-opened), round opened', 'Analyst'],
    ['Candidates', 'Address, title, snippet, proposing goal, query, state, score history', 'Searchers; assistant; Finance'],
    ['Pages and chunks', 'Fetched text, fetch time, token estimate, chunk boundaries', 'Reader rule'],
    ['Evidence', 'Quoted passage, page and chunk, goal(s), reading, extracting call', 'Readers'],
    ['Goal summaries', 'Per goal per round, what was found', 'Searchers (summary call)'],
    ['Conflicts', 'Type, the two sides with their evidence, status, resolution', 'Conflict checker; Analyst'],
    ['Decisions and events', 'Every call and every rule action: position, time, inputs by reference, output, model, cost', 'Rules, automatically'],
    ['Budgets', 'Mission, round and per-position balances', 'Finance'],
    ['Report', 'Report list, sections, citation checks', 'Analyst; Writer; rules'],
], widths=[1.3, 4.0, 1.4], font=9)
d.h2('5.2 Access rights')
d.table(['Position', 'Task model', 'Goals', 'Candidates', 'Pages', 'Evidence', 'Conflicts', 'Report'], [
    ['Analyst', 'R/W', 'R/W', 'none', 'none', 'summaries only', 'R/W', 'W list'],
    ['Assistant', 'R', 'R', 'R/W scores', 'none', 'summaries only', 'R', 'none'],
    ['Searcher', 'own goal', 'own goal', 'W', 'none', 'own goal (for summary)', 'none', 'none'],
    ['Reader', 'none', 'own goal(s)', 'own item', 'own chunk', 'W', 'none', 'none'],
    ['Checker', 'R', 'R', 'none', 'none', 'R', 'R/W', 'none'],
    ['Writer', 'R', 'R', 'none', 'none', 'R (per section)', 'R', 'R/W'],
], widths=[0.9, 0.85, 0.8, 0.95, 0.7, 1.1, 0.8, 0.6], font=8)
d.para('OPEN, Kecheng (K-1). The exact table design and the enforcement of these rights in code.')
d.h2('5.3 The context gate')
d.para('DECIDED. Before every model call, the rules estimate the size in tokens of what the position is about to be shown and compare it with that position\'s budget for the model in use. If it exceeds the budget, the rules split or summarise before the call: pages are chunked for readers; evidence is handed to the Writer one section at a time; the Analyst receives goal summaries instead of evidence. Overflow is therefore impossible by construction on both models. OPEN, Kecheng (K-3): the budget per position for the 128K local model and for the API model, and the token estimator to use for each.')
d.h2('5.4 Replay and the mission console')
d.para('DECIDED. The mission console is a view over the records. It shows a timeline of events (which position, when, which tool, which query or page, what it decided, what it cost), the task model and the goal tree as they change round by round, the conflicts and their resolutions, and the report with each citation linked to its evidence. It can show two missions on the same task side by side. Because pages are cached, a mission replays without the network.')

d.h1('6. The baseline')
d.para('The baseline is the flat design that most open-source systems use and that the LangChain Open Deep Research project documents [9]. It runs in the same company: same records, same tools, same readers, same writer, same budgets, same models, same context gate. What differs is the analyst position. The baseline analyst makes one plan of sub-questions from the request, dispatches searchers for all of them, and after each round asks itself whether the findings are sufficient to write. It has no task model, no goal values and no re-ranking; it keeps its state as notes in prose, the way such systems do. It stops when it judges the findings sufficient, when the budget is gone, or after a fixed maximum number of rounds.')
d.para('DECIDED by default, to confirm with Zhuo: the baseline uses the same Finance rule and the same assistant mechanism to choose candidates when they exceed the round budget, so that candidate selection does not confound the comparison. What the comparison then isolates is the EBD analysis and the tree-shaped, re-ranked search against a one-shot plan with a sufficiency check.')

d.h1('7. Evaluation')
d.h2('7.1 Design')
d.para('Two analysts (baseline, EBD) by two models (DeepSeek-V4.1-Flash through its API; Qwen 3.8-27B served locally on one RTX 5090 with a 128K window) on nine tasks, three runs per task, two if the schedule requires. Zhuo runs the API model missions; Kecheng runs the local model missions; both feed the same judge pipeline. Reports are judged blind by Claude Opus 5, GPT-5.6-sol and Gemini 3.8 Flash, none of which is in the family of either generator.')
d.h2('7.2 Tasks')
d.para('Nine tasks in three groups of three, each member authoring one group. Relation-heavy tasks name several objects and claimed relations, so that the task model has a lot to decompose. Conflict-laden tasks are built around disagreements we know the answer to: a number revised between two dates, a claim later retracted, two reputable sources that contradict each other, and at least two tasks whose question assumes something false, so that a good report must say so. Open synthesis tasks are ordinary broad questions. Topics are chosen after the models\' training cutoff so that searching is necessary. Three separate development tasks are used for building and prompt tuning and never for evaluation.')
d.h2('7.3 Measures')
d.bullets([
    ('Report quality, judged. ', 'Blind pairwise comparison of the two analysts\' reports on the same task, each pair judged in both orders to cancel position bias, by all three judges. Plus a rubric per task: the facts a good report must contain and the conflicts it must surface, scored item by item.'),
    ('Report quality, checked. ', 'Citation support: does the cited evidence actually contain the claim, verified against the cached page.'),
    ('Process, from the records. ', 'Conflict recall on the planted disagreements; detection of false assumptions; whether the mission ended on its own condition or on the budget; useful sources per search; cost in tokens and time.'),
    ('Tree growth. ', 'Rounds run, goals opened, depth reached, objects discovered that were not in the request, and how the budget was distributed across depths. OPEN, Haoxi with Zhuo (H-9): the exact definitions.'),
    ('Judge validity. ', 'Agreement across the three judges, and a hand check of a sample by the team.'),
])
d.h2('7.4 Hypotheses and analysis')
d.para('H1: with the same budget, the EBD analyst surfaces the planted conflicts and false assumptions more often than the baseline. H2: judges prefer the EBD reports on rubric coverage and citation support, or find them no worse. H3: the EBD analyst ends missions on its own condition more often and needs fewer searches per useful source. H4: the EBD gain is larger on the local model. Per-task differences are tested with paired tests and reported with bootstrap intervals. Nine tasks give pilot-scale evidence, and the report will say so.')
d.h2('7.5 Cost and time')
d.para('The local model at about 100 tokens per second is the bottleneck. If a mission generates 40,000 tokens, it takes roughly seven minutes; 54 local missions take about six hours and run overnight. The API model is fast and inexpensive. Judging cost is bounded by judging only final runs and caching every judgment.')

d.h1('8. Open design items')
d.h2('8.1 Haoxi Li, behaviour design')
d.bullets([
    ('H-1 Task model form. ', 'How objects, relations and environment components are represented so that the Analyst can produce them, the rules can store them, and their statuses (unknown, defined, presupposed, verified, refuted, disputed) can be tracked.'),
    ('H-2 New goal criterion. ', 'When distilled evidence creates a new goal: a new object with no definition, a relation that turned out to be unverified, a conflict that needs settling, or a component discovered inside an object.'),
    ('H-3 Goal value. ', 'How the Analyst scores every open goal after each round: distance from the client\'s target, how much of the answer depends on it, how much is already known, and the cost of pursuing it. This is the priority in the priority search.'),
    ('H-4 Candidate value. ', 'What the assistant weighs when choosing pages within the round budget.'),
    ('H-5 Node done and re-open. ', 'When a node is exhausted for now, and what new knowledge re-opens it; how a condition is attached to a re-opened node.'),
    ('H-6 Conflicts. ', 'The typology, the placement of the checker in the round, the form of a resolution, and how the Analyst acts on each type.'),
    ('H-7 Report list. ', 'What the Analyst registers for the Writer and in what order; how disputed items are marked.'),
    ('H-8 Job descriptions. ', 'The instructions for every position, for both models, with output formats that the rules can validate.'),
    ('H-9 Tree metrics. ', 'With Zhuo: the definitions used to quantify tree growth for the evaluation.'),
    ('H-10 Behaviour validation. ', 'Hand-made decompositions of the development tasks to check the Analyst; planted conflicts to score the checker.'),
])
d.h2('8.2 Zhuo Qiu, architecture and orchestration')
d.bullets([
    ('Z-1 Interfaces. ', 'The contracts between positions, the records, the tools and the model adapter; the event format.'),
    ('Z-2 Pipeline. ', 'The mission runner and the synchronous round scheduler; one command runs a task on either analyst and either model.'),
    ('Z-3 Rules in the workflow. ', 'Finance; the assistant branching mechanism; dispatch and return of work.'),
    ('Z-4 Baseline. ', 'The flat analyst as specified in section 6.'),
    ('Z-5 Evaluation kit. ', 'Rubric format, judge pipeline, statistics; the DeepSeek half of the runs.'),
    ('Z-6 Console views. ', 'Timeline, side-by-side and report views, with Kecheng.'),
])
d.h2('8.3 Kecheng Yao, environment')
d.bullets([
    ('K-1 Records. ', 'The SQLite design, the access rights, and their enforcement.'),
    ('K-2 Events. ', 'The append-only event log with cost capture, and replay.'),
    ('K-3 Context gate. ', 'Per-position budgets for the 128K local model and the API model; the token estimators; the chunking and merging rules for readers.'),
    ('K-4 Tools. ', 'Search, fetch, cache and duplicate removal; rate limits and retries.'),
    ('K-5 Models. ', 'One adapter with two configurations; local serving of Qwen 3.8-27B on the RTX 5090; output validation and repair; the Qwen half of the runs.'),
    ('K-6 Trace metrics. ', 'The queries over the records that produce the process measures.'),
    ('K-7 Console data. ', 'The event stream and the task model view, with Zhuo.'),
])

d.h1('9. Work breakdown')
d.para('The 55 atomic jobs, numbered as in the team list, assigned by member. Shared jobs are listed last.')
d.table(['Member', 'Jobs'], [
    ['Haoxi Li', 'Seat behaviours: (24) Researcher, (25) Distiller agent, (27) Conflict Checker and typology, (28) Writer. EBD judgments: (31) task analysis, (32) goal generation, (33) environment update, (34) conflict resolution. (29) prompt set per position for both models; (22) output formats and retry prompts per model. Behaviour validation: hand-made decompositions, checker scoring on planted conflicts, (47) citation support check.'],
    ['Zhuo Qiu', 'Architecture: (1) repository and module skeletons, (2) interface contracts, (36) mission runner. Orchestration: (30) baseline analyst, (35) EBD stopping and escalation in the loop, (4) development task set. Evaluation: (43) rubric format, (44) judge prompts and blind pairwise pipeline, (45) rubric scoring, (48) inter-judge agreement and human check, (49) statistics, (50) DeepSeek half of the run matrix, (51) results dataset, (53) integration tests. Console: (38) timeline view, (40) side-by-side view, (41) report view.'],
    ['Kecheng Yao', 'Records and rules: (5) schema, (6) event log with cost capture, (7) access rights, (8) state machines, (9) goal ordering, (10) budgets, (11) stopping evaluator, (12) context gate sized to 128K, (13) deterministic conflict checks, (14) output validation and repair, (15) replay. Tools and models: (16) search, (17) fetch, (18) cache, (19) rate limiting, (20) model adapter, (21) local Qwen serving, (26) reader chunking and merge rules. (3) continuous integration, (46) trace metrics, (50) Qwen half of the run matrix. Console: (37) event stream, (39) task model view.'],
    ['Shared', '(42) the nine tasks, three per member, with Zhuo keeping the rubric format consistent; (52) unit tests, each for their own components; (54) documentation, each for their aspect; (55) final report and presentation.'],
], widths=[1.1, 5.6], font=9)

d.h1('10. Timeline and milestones')
d.para('Nine project weeks; calendar dates to be added when the course schedule is confirmed. The final report is due in mid-December 2026.')
d.table(['Week', 'What is due'], [
    ['W1', 'Interfaces (Z-1) and repository skeleton; records design (K-1); task model form (H-1). Development tasks written.'],
    ['W2', 'Records, tools and model adapter running; local Qwen served; first job descriptions (H-8) on the development tasks. M1: design frozen.'],
    ['W3', 'Baseline analyst runs end to end on both models. Searcher and reader positions working with the context gate.'],
    ['W4', 'EBD analyst first version: task model, goals, re-ranking (H-2, H-3, H-5). Assistant branching and Finance in the loop.'],
    ['W5', 'Conflict checker (H-6), Writer and report list (H-7). M2: the company runs end to end on both models.'],
    ['W6', 'Nine tasks and rubrics written and reviewed; judge pipeline ready. M3: tasks frozen; scope frozen.'],
    ['W7', 'Experiment runs on both models; console timeline and task model views.'],
    ['W8', 'Judging, trace metrics, statistics. M4: all runs judged.'],
    ['W9', 'Final report, manuals, presentation. M5: submission.'],
], widths=[0.6, 6.1], font=9)

d.h1('11. Risks')
d.table(['Risk', 'Effect', 'What we do'], [
    ['The local model follows structured instructions less reliably than the API model', 'Malformed outputs, wasted calls', 'Rules validate and repair every output; job descriptions kept short and structured; the API model is the reference; the gap itself is reported (H4)'],
    ['Local throughput of about 100 tokens per second', 'Runs take hours', 'Context and fetch caps per position; overnight runs; two runs per task as fallback'],
    ['Search engine blocked or rate-limited', 'Missing candidates, unrepeatable runs', 'Every result cached; paid search service as fallback; fixed experiment window'],
    ['The Analyst\'s decomposition varies between runs', 'Noisy comparison', 'Fixed decoding settings; validation of the task model; repeated runs; variance reported'],
    ['Goal explosion', 'Budget spread too thin', 'Round budget and goal value ranking; caps on goals per round'],
    ['Judge bias and disagreement', 'Unreliable verdicts', 'Blind, both orders, rubrics, agreement statistics, human spot check; judges from other model families'],
    ['Nine tasks', 'Limited statistical power', 'Repeated runs, paired tests, pilot-scale claims; the conflict group built for a clear effect'],
    ['Nine weeks, three people, console scope creep', 'Unfinished work', 'Scope frozen at W6; minimum console first; extras only after M4'],
], widths=[2.0, 1.5, 3.2], font=9)

d.h1('12. Glossary')
d.table(['Term', 'Meaning in this project'], [
    ['Deep research', 'An AI system that answers a question by searching the web, reading sources, iterating, and writing a cited report, rather than answering from memory.'],
    ['EBD', 'Environment-Based Design, Prof. Zeng\'s method: describe the objects, relations and environment of a problem; identify conflicts; generate a solution; repeat as the environment changes.'],
    ['Object, relation, environment', 'The three units of the task model: the things the request is about, the claims linking them, and the conditions the answer must respect.'],
    ['Position (seat)', 'A role in the company with a job description; an agent in the course\'s sense.'],
    ['Job description', 'The behaviour of a position: what it receives, produces, may read, may write, may call, and decides.'],
    ['Records (ledger)', 'The company database, owned by the rules; the environment of the agent-based model.'],
    ['Round', 'One cycle of analyse, search, count, choose, read, summarise, check.'],
    ['Goal (node)', 'One thing to find out; a node of the search tree, with a value and a status.'],
    ['Candidate pool', 'All pages proposed for fetching in a mission, with their states.'],
    ['Distill', 'Extract the evidence a page holds for a goal, as quoted passages.'],
    ['Context window, context gate', 'The most a model call can be shown; the rule that measures and splits inputs before every call.'],
    ['Conflict', 'A recorded disagreement between two pieces of evidence, or between evidence and an assumption or constraint.'],
    ['Branch (assistant)', 'A temporary model call given the Analyst\'s current state for one decision, then discarded.'],
    ['Baseline', 'The flat analyst: one plan, parallel search, sufficiency check, report.'],
    ['Blind judging', 'Judges see reports without knowing which analyst produced them.'],
    ['Rubric', 'The list of facts and conflicts a good report on a task must contain.'],
], widths=[1.6, 5.1], font=9)
d.references(REFS)
d.save(OUT)
print('design document saved')
