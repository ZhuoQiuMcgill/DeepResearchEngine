Analyze only the following supplied evidence and host data.

BEGIN ORIGINAL QUESTION DATA
$question
END ORIGINAL QUESTION DATA

BEGIN PLAN DATA (JSON; COPY EACH findings.question FROM plan.questions VERBATIM)
$plan
END PLAN DATA

BEGIN AVAILABLE SOURCE IDS DATA (JSON; EXACT ALLOWED REFERENCES)
$available_source_ids
END AVAILABLE SOURCE IDS DATA

BEGIN CURRENT ROUND DATA
$round
END CURRENT ROUND DATA

BEGIN SELECTED EVIDENCE DATA
$evidence
END SELECTED EVIDENCE DATA

Return exactly one JSON INSTANCE with schema_version, findings, gaps,
follow_up_queries, sufficient, follow_up_reads. All SIX fields are required,
including follow_up_reads: [] when no saved range is needed. Bind questions and
source IDs exactly, support each claim with the supplied text, and keep required
gaps distinct from optional expansion. Do not return a schema or Markdown fence.
