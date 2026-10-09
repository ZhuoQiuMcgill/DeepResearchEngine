Select the next bounded fetch batch using the following untrusted data.

BEGIN QUESTION DATA
$question
END QUESTION DATA

BEGIN RESEARCH PLAN DATA (JSON)
$plan
END RESEARCH PLAN DATA

BEGIN CANDIDATE CARDS DATA (JSON)
$candidates
END CANDIDATE CARDS DATA

BEGIN ACQUISITION HISTORY DATA (JSON)
$history
END ACQUISITION HISTORY DATA

BEGIN EVIDENCE GAPS DATA (JSON)
$gaps
END EVIDENCE GAPS DATA

BEGIN FETCH BUDGET DATA (JSON)
$budget
END FETCH BUDGET DATA

BEGIN CANDIDATE COVERAGE DATA (JSON)
$coverage
END CANDIDATE COVERAGE DATA

Return only the Selector JSON decision specified in your instructions. Classify
every delivered candidate ID once, with selections limited to the immediate batch.
