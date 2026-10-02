"""Combine disjoint, recorded child usage without inventing missing counts."""
from __future__ import annotations

from deepresearch.engine.providers.usage import PRIMARY_COUNTS, TOKEN_COUNTS


def aggregate_usage(records):
    subtotals = dict.fromkeys(TOKEN_COUNTS)
    refs, unknown, seen = [], [], set()
    incomplete = False
    for usage in records:
        if not isinstance(usage, dict):
            incomplete = True
            continue
        incomplete |= usage.get("completeness") != "complete"
        for key in TOKEN_COUNTS:
            count = usage.get("known_subtotals", {}).get(key)
            if type(count) is int and count >= 0:
                subtotals[key] = (subtotals[key] or 0) + count
        for ref in usage.get("per_attempt_usage_refs", []):
            identity = (ref.get("store_id"), ref.get("event_id"))
            if identity not in seen:
                seen.add(identity)
                refs.append(dict(ref))
        unknown.extend(value for value in usage.get("unknown_attempt_ids", []) if value not in unknown)
    known = sum(subtotals[key] is not None for key in PRIMARY_COUNTS)
    return {"known_subtotals": subtotals,
            "completeness": "complete" if known == 3 and not incomplete and not unknown else "partial" if known else "unknown",
            "unknown_attempt_ids": unknown, "per_attempt_usage_refs": refs}
