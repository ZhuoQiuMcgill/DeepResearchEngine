Review the supplied current report using the following untrusted task data.
Follow the Reviewer role and evidence boundaries in your instructions.

BEGIN QUESTION DATA
$question
END QUESTION DATA

BEGIN PLAN DATA (JSON)
$plan
END PLAN DATA

BEGIN ANALYSIS DATA (JSON)
$analysis
END ANALYSIS DATA

BEGIN SELECTED EVIDENCE DATA
$evidence
END SELECTED EVIDENCE DATA

BEGIN REPORT DATA
$report
END REPORT DATA

BEGIN HOST RESEARCH QUALITY DATA (JSON; SEPARATE FROM REPORT ACCEPTANCE)
$quality
END HOST RESEARCH QUALITY DATA

Check the direct English answer, claim-level support from supplied passages,
exact eligible citation IDs, the Research coverage label matching quality.status,
specific limitations and grounded References. Accept a properly qualified limited
answer when it has no material defect. For revise, give only actionable edits
within the Writer's existing evidence and scope.

Return one JSON instance, not a JSON Schema or a rewritten report. Include only
schema_version (integer 1), verdict (accept or revise) and issues (accept: empty;
revise: 1..8 nonblank English strings, each at most 1024 characters). Do not wrap
the JSON in prose or Markdown fences.
