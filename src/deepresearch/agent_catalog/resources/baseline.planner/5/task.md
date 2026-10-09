Create a focused research plan from the following untrusted data. Preserve the
original question as supplied; generated planning text must stay within its scope.

BEGIN QUESTION DATA
$question
END QUESTION DATA

BEGIN USER QUERIES DATA (JSON)
$user_queries
END USER QUERIES DATA

BEGIN MAXIMUM QUERY COUNT DATA
$max_queries
END MAXIMUM QUERY COUNT DATA

Return only one Planner JSON instance with schema_version, objective, questions,
queries and outline. Never return a schema or prose outside the object. Write
new text in English and preserve supplied identifiers and any included user query
exactly. Use concise, distinct question strings as exact downstream keys. Check
that queries has 1 to min(4, max_queries) entries and every field meets the stated
bounds. A simple definition request should retain a simple, focused plan.

BEGIN RESEARCH CONTEXT DATA (AS OF TIME, NOT A SOURCE PUBLICATION DATE)
$research_context
END RESEARCH CONTEXT DATA

BEGIN REPAIR DATA (PRIOR OUTPUT AND HOST VALIDATION ERRORS; EMPTY ON FIRST ATTEMPT)
$repair
END REPAIR DATA
