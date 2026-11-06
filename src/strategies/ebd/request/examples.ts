/**
 * The four worked examples of Lab 2 rev 1.3, converted to rev 2: no client
 * route, no blocking or default fields, source hints on search questions, an
 * empty grounding list. E3 (missing material) is now out of scope, because
 * nobody can be asked during a mission. The ROM granularity is unchanged (D-B open).
 */
import type { Analysis } from "./schema.js";

export type WorkedExample = { id: string; teaches: string; runDate: string; request: string; analysis: Analysis };

const unknown = { value: null, basis: "unknown" as const, evidence: [] };

export const EXAMPLES: WorkedExample[] = [
  {
    id: "E1",
    teaches:
      "Full analysis: presuppositions become assumptions with verification questions; define before relating; verify before explaining; product questions go to synthesis; search questions carry generic source hints.",
    runDate: "2026-10-01",
    request:
      "Why did 2025 US tariffs raise new-car prices in Canada, and what do economists expect for prices in 2026? I'm briefing a car dealers' association.",
    analysis: {
      flags: [],
      client_directives: [],
      restated_request:
        "Explain whether and why the 2025 US tariffs raised new-car prices in Canada, and summarise what economists expect for those prices in 2026, for a briefing to a car dealers' association.",
      status: "ok",
      status_reason: null,
      frame: {
        purpose: {
          value: "A briefing for a car dealers' association; the decision the briefing should inform is not stated.",
          basis: "explicit",
          evidence: ["I'm briefing a car dealers' association"],
        },
        time_frame: {
          value: "From before the 2025 US tariffs to the latest data available on 2026-10-01, plus forecasts for 2026.",
          basis: "explicit",
          evidence: ["2025", "in 2026"],
        },
        place: { value: "Canada; where the association's members are is not stated.", basis: "explicit", evidence: ["Canada"] },
      },
      rom: {
        objects: [
          { id: "O1", text: "Why", kind: "question_word", role: "product", status: "needs_question", meaning: "The explanation the client asks for: why the tariffs raised new-car prices in Canada.", readings: [] },
          { id: "O2", text: "2025", kind: "number_or_date", role: "environment", status: "self_evident", meaning: "The calendar year 2025.", readings: [] },
          { id: "O3", text: "US", kind: "proper_noun", role: "environment", status: "self_evident", meaning: "The country that imposed the tariffs.", readings: [] },
          { id: "O4", text: "tariffs", kind: "noun", role: "environment", status: "needs_question", meaning: "Taxes on imports imposed by the US in 2025; which goods and trading partners they cover is not stated.", readings: [] },
          { id: "O5", text: "raise", kind: "verb", role: "environment", status: "needs_question", meaning: "Cause to be higher than they would otherwise have been.", readings: [] },
          { id: "O6", text: "new-car prices", kind: "noun", role: "environment", status: "needs_question", meaning: "Prices paid for new cars in Canada; the exact measure is not stated. Referred to again as \"prices\".", readings: [] },
          { id: "O7", text: "Canada", kind: "proper_noun", role: "environment", status: "self_evident", meaning: "The country Canada.", readings: [] },
          { id: "O8", text: "what", kind: "question_word", role: "product", status: "needs_question", meaning: "The summary of economists' expectations the client asks for.", readings: [] },
          { id: "O9", text: "economists", kind: "noun", role: "environment", status: "needs_question", meaning: "Economists or organisations that publish forecasts of new-car prices in Canada.", readings: [] },
          { id: "O10", text: "expect", kind: "verb", role: "environment", status: "needs_question", meaning: "Forecast.", readings: [] },
          { id: "O11", text: "2026", kind: "number_or_date", role: "environment", status: "self_evident", meaning: "The calendar year 2026.", readings: [] },
          { id: "O12", text: "briefing", kind: "verb", role: "environment", status: "self_evident", meaning: "The client is preparing to brief the association; this is the purpose of the request.", readings: [] },
          { id: "O13", text: "car dealers' association", kind: "noun", role: "environment", status: "self_evident", meaning: "An association of car dealers, the audience of the briefing; which one is not stated and does not change the research.", readings: [] },
        ],
        relations: [
          { id: "R1", type: "constraint", from: "O2", to: "O4", via: null, stance: "presupposed" },
          { id: "R2", type: "constraint", from: "O3", to: "O4", via: null, stance: "presupposed" },
          { id: "R3", type: "subject_verb", from: "O4", to: "O5", via: null, stance: "presupposed" },
          { id: "R4", type: "verb_object", from: "O5", to: "O6", via: null, stance: "presupposed" },
          { id: "R5", type: "constraint", from: "O7", to: "O6", via: "in", stance: "presupposed" },
          { id: "R6", type: "constraint", from: "O1", to: "O5", via: null, stance: "asked" },
          { id: "R7", type: "connection", from: "O5", to: "O10", via: "and", stance: "neutral" },
          { id: "R8", type: "subject_verb", from: "O9", to: "O10", via: null, stance: "asked" },
          { id: "R9", type: "verb_object", from: "O10", to: "O8", via: null, stance: "asked" },
          { id: "R10", type: "verb_object", from: "O10", to: "O6", via: "for", stance: "asked" },
          { id: "R11", type: "constraint", from: "O11", to: "O6", via: "in", stance: "neutral" },
          { id: "R12", type: "verb_object", from: "O12", to: "O13", via: null, stance: "neutral" },
        ],
        central_object_ids: ["O5", "O10"],
      },
      assumptions: [
        { id: "A1", claim: "The US imposed tariffs in 2025.", kind: "presupposed", relation_ids: ["R1", "R2"], evidence: ["2025 US tariffs"] },
        { id: "A2", claim: "New-car prices in Canada rose after the 2025 US tariffs.", kind: "presupposed", relation_ids: ["R4", "R5"], evidence: ["raise new-car prices in Canada"] },
        { id: "A3", claim: "The 2025 US tariffs caused new-car prices in Canada to rise.", kind: "presupposed", relation_ids: ["R3", "R4"], evidence: ["Why did 2025 US tariffs raise new-car prices in Canada"] },
      ],
      questions: [
        {
          id: "Q1", object_ids: ["O4"], template: "T3", guideline: "G1",
          text: "Did the US impose tariffs in 2025 that apply to new cars, car parts or materials sold in Canada? If so, which goods do they cover, at what rates, from which dates, and under which US government decision?",
          route: "search", need: "necessary", depends_on: [], verifies: ["A1"],
          done_when: "Lists each 2025 US tariff relevant to new cars sold in Canada, with goods covered, rates, effective dates and legal basis, from official or primary sources, or reports evidence that no such tariff was imposed.",
          source_hints: ["official government publications", "news reports on trade policy"],
        },
        {
          id: "Q2", object_ids: ["O6"], template: "T2", guideline: "G1",
          text: "How are new-car prices in Canada measured, what components make them up, and how did they change from the year before the 2025 US tariffs to the latest data available on 2026-10-01?",
          route: "search", need: "necessary", depends_on: [], verifies: ["A2"],
          done_when: "Defines the price measure and its components and gives a dated series from at least the year before the tariffs to the latest available period, from official statistics or industry data.",
          source_hints: ["official price statistics", "industry price data"],
        },
        {
          id: "Q3", object_ids: ["O9"], template: "T1", guideline: "G1",
          text: "Which economists or organisations publish forecasts of new-car prices in Canada for 2026 (for example banks, government agencies, research institutes or industry analysts), and when were their latest forecasts published?",
          route: "search", need: "necessary", depends_on: [], verifies: [],
          done_when: "Names at least three publishers of such forecasts, with the type of organisation and the date of each latest forecast.",
          source_hints: ["bank economic outlooks", "industry analyst reports"],
        },
        {
          id: "Q4", object_ids: ["O5"], template: "T7", guideline: "G7",
          text: "Did the 2025 US tariffs raise new-car prices in Canada, and by how much, according to studies or official analyses that separate the tariffs' effect from other price drivers such as exchange rates, interest rates and supply problems?",
          route: "search", need: "necessary", depends_on: ["Q1", "Q2"], verifies: ["A3"],
          done_when: "Reports each study's estimated effect, or its finding of no effect, with method, period and publisher; says whether the studies agree; does not infer cause from timing alone.",
          source_hints: ["economic studies", "central bank analyses"],
        },
        {
          id: "Q5", object_ids: ["O10", "O11"], template: "T6", guideline: "G2",
          text: "What do published forecasts expect for new-car prices in Canada in 2026, and on which assumptions (for example tariff levels, exchange rates, interest rates, vehicle supply) do they rest?",
          route: "search", need: "necessary", depends_on: ["Q2", "Q3"], verifies: [],
          done_when: "Gives the forecast price change or range for 2026 from at least two independent publishers, with publication date, price measure and main assumptions.",
          source_hints: ["published price forecasts", "bank economic outlooks"],
        },
        {
          id: "Q6", object_ids: ["O5"], template: "T4", guideline: "G6",
          text: "Through which mechanisms could the 2025 US tariffs affect new-car prices in Canada (for example the cost of imported cars and parts, exchange rates, supply chains, dealer margins), and what evidence supports or contradicts each mechanism?",
          route: "search", need: "necessary", depends_on: ["Q4"], verifies: [],
          done_when: "Describes each mechanism named in the sources, with the evidence for or against it and its estimated size where available.",
          source_hints: ["economic studies", "industry analyses"],
        },
        {
          id: "Q7", object_ids: ["O1", "O5"], template: "T4", guideline: "G5",
          text: "Why, and to what extent, did the 2025 US tariffs raise new-car prices in Canada; or, if the evidence does not show that they did, what explains the price changes?",
          route: "synthesis", need: "necessary", depends_on: ["Q4", "Q6"], verifies: [],
          done_when: "States whether and by how much the tariffs raised new-car prices in Canada, explains the mechanisms, cites the evidence gathered for Q4 and Q6, and reports disagreements between sources.",
          source_hints: [],
        },
        {
          id: "Q8", object_ids: ["O8", "O10"], template: "T6", guideline: "G2",
          text: "What range of new-car prices in Canada in 2026 do economists' forecasts support, and what explains the differences between them?",
          route: "synthesis", need: "necessary", depends_on: ["Q5"], verifies: [],
          done_when: "Summarises the range of forecasts and the assumptions that explain their differences, citing the evidence gathered for Q5.",
          source_hints: [],
        },
      ],
      grounding: [],
    },
  },
  {
    id: "E2",
    teaches:
      "Underspecified request: purpose, criteria and place are not stated, but nothing key is missing: facts are searched and the rest gets a disclosed neutral default; relative time resolved from the run date; the main object is defined through the steps of its lifecycle; no assumptions to verify.",
    runDate: "2026-10-01",
    request: "Which electric car is best for cold winters these days?",
    analysis: {
      flags: [],
      client_directives: [],
      restated_request:
        "Identify which electric car performs best in cold winters, using cars and evidence current as of 2026-10-01; the criteria, budget and location are not stated.",
      status: "ok",
      status_reason: null,
      frame: {
        purpose: {
          value: "Choose an electric car that copes with cold winters; whether to buy one, and what it must do, is not stated.",
          basis: "implied",
          evidence: ["Which electric car is best for cold winters"],
        },
        time_frame: { value: "Cars and evidence current as of 2026-10-01.", basis: "implied", evidence: ["these days"] },
        place: {
          value: "No country assumed; regions with cold winters, with differences in availability, prices and incentives noted.",
          basis: "default",
          evidence: [],
        },
      },
      rom: {
        objects: [
          { id: "O1", text: "Which", kind: "question_word", role: "product", status: "needs_question", meaning: "The choice the client asks for: which electric car is best for cold winters.", readings: [] },
          { id: "O2", text: "electric car", kind: "noun", role: "environment", status: "needs_question", meaning: "A car that runs on electricity from a battery; whether the client wants a model to buy or a type of car is not stated.", readings: [] },
          { id: "O3", text: "best", kind: "adjective", role: "environment", status: "needs_question", meaning: "Best by criteria the client does not state; neutral default criteria are used and disclosed.", readings: [] },
          { id: "O4", text: "cold winters", kind: "noun", role: "environment", status: "needs_question", meaning: "Winters with low temperatures; how cold, and where, is not stated.", readings: [] },
          { id: "O5", text: "these days", kind: "adverb", role: "environment", status: "self_evident", meaning: "As of the run date, 2026-10-01.", readings: [] },
        ],
        relations: [
          { id: "R1", type: "constraint", from: "O1", to: "O2", via: null, stance: "asked" },
          { id: "R2", type: "constraint", from: "O3", to: "O2", via: null, stance: "asked" },
          { id: "R3", type: "constraint", from: "O4", to: "O3", via: "for", stance: "neutral" },
          { id: "R4", type: "constraint", from: "O5", to: "O3", via: null, stance: "neutral" },
        ],
        central_object_ids: ["O2"],
      },
      assumptions: [],
      questions: [
        {
          id: "Q1", object_ids: ["O2"], template: "T1", guideline: "G1",
          text: "Which electric car models are on sale as of 2026-10-01, and for each, what does owning one involve at each step: buying (price and purchase incentives), charging (charging speed and the home or public charging it needs) and driving (battery capacity, rated driving range, cabin heating system)?",
          route: "search", need: "necessary", depends_on: [], verifies: [],
          done_when: "For each model on the market, by step of ownership: buying (dated price, market and purchase incentives), charging (charging speed, home or public charging needed) and driving (battery capacity, rated range, heating system such as a heat pump or resistive heater), from manufacturer data, official incentive pages or independent reviews.",
          source_hints: ["manufacturer specifications", "independent car reviews"],
        },
        {
          id: "Q2", object_ids: ["O4"], template: "T2", guideline: "G1",
          text: "How do cold winters affect the electric car models on sale as of 2026-10-01: driving range, charging speed, cabin heating and battery health at low temperatures, according to field or laboratory tests?",
          route: "search", need: "necessary", depends_on: ["Q1"], verifies: [],
          done_when: "Reports measured cold-weather range loss, charging speed and heating performance for each model or type of car, with test conditions, source and date.",
          source_hints: ["independent cold-weather tests", "motoring organisation reports"],
        },
        {
          id: "Q3", object_ids: ["O1", "O2", "O3"], template: "T2", guideline: "G1",
          text: "Which electric car is best for cold winters by the disclosed default criteria (driving range in the cold, total cost, charging time and reliability), and under which conditions would a different car be better?",
          route: "synthesis", need: "necessary", depends_on: ["Q1", "Q2"], verifies: [],
          done_when: "Recommends a car with reasons tied to each default criterion, cites the evidence gathered for Q1 and Q2, and discloses the defaults used for the criteria, budget and location.",
          source_hints: [],
        },
      ],
      grounding: [],
    },
  },
  {
    id: "E3",
    teaches:
      "Missing material with nothing left to research: flag it, never guess what it is, and set the status to out_of_scope, because nobody can be asked during a mission.",
    runDate: "2026-10-01",
    request: "Can you check whether the mortgage rates in my last message are still current?",
    analysis: {
      flags: [
        {
          type: "missing_referent",
          detail: "The request refers to mortgage rates in an earlier message; that message is not part of the request and, unlike a linked page, cannot be fetched.",
          evidence: ["the mortgage rates in my last message"],
        },
      ],
      client_directives: [],
      restated_request: "Check whether mortgage rates from the client's earlier message are still current as of 2026-10-01; the rates were not provided.",
      status: "out_of_scope",
      status_reason: "The request asks to check mortgage rates from an earlier message that was not provided, and nothing in it can be researched without them.",
      frame: { purpose: unknown, time_frame: unknown, place: unknown },
      rom: { objects: [], relations: [], central_object_ids: [] },
      assumptions: [],
      questions: [],
      grounding: [],
    },
  },
  {
    id: "E4",
    teaches:
      "Out of scope: no research question (creative writing). Decide the status at the gate and stop: everything after status_reason stays empty.",
    runDate: "2026-10-01",
    request: "Write a short poem about the Winter Olympics for my newsletter.",
    analysis: {
      flags: [],
      client_directives: [],
      restated_request: "The client asks for a short poem about the Winter Olympics for a newsletter; this is creative writing, not a research question.",
      status: "out_of_scope",
      status_reason: "The request asks for creative writing and contains no research question.",
      frame: { purpose: unknown, time_frame: unknown, place: unknown },
      rom: { objects: [], relations: [], central_object_ids: [] },
      assumptions: [],
      questions: [],
      grounding: [],
    },
  },
];
