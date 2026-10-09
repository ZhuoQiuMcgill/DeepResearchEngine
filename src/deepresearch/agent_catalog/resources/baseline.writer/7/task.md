Write or revise the complete final English report using the following untrusted
task data. Follow the Writer role and evidence boundaries in your instructions.

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

BEGIN FEEDBACK DATA (JSON)
$feedback
END FEEDBACK DATA

BEGIN HOST RESEARCH QUALITY DATA (JSON; SEPARATE FROM REPORT ACCEPTANCE)
$quality
END HOST RESEARCH QUALITY DATA

Return only raw English Markdown, not JSON or a quoted string. Lead with a useful
answer, include the exact Research coverage label from quality.status near the
beginning, support substantive claims with exact eligible source IDs, explain
specific limitations concisely, and end with grounded References. Address supplied
feedback through the report itself without adding unsupported evidence.

BEGIN RESEARCH CONTEXT DATA (AS OF TIME, NOT A SOURCE PUBLICATION DATE)
$research_context
END RESEARCH CONTEXT DATA

BEGIN REPAIR DATA (PRIOR OUTPUT AND HOST VALIDATION ERRORS; EMPTY ON FIRST ATTEMPT)
$repair
END REPAIR DATA
