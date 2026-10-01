"""Nullable provider token accounting and bounded numeric native evidence."""
from __future__ import annotations

from typing import Any

from ebd.contracts import canonical_json


TOKEN_COUNTS = ("input_tokens", "output_tokens", "total_tokens", "cached_input_tokens", "reasoning_output_tokens", "uncached_input_tokens")
PRIMARY_COUNTS = TOKEN_COUNTS[:3]


def unknown_usage() -> dict[str, Any]:
    return {**dict.fromkeys(TOKEN_COUNTS), "completeness": "unknown", "source": "provider", "measurement_ref": None}


def _count(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def normalize_usage(value: Any) -> dict[str, Any]:
    """Keep reported counts; never infer totals or add subset breakdowns."""
    if not isinstance(value, dict):
        return unknown_usage()
    def count(*keys):
        return next((item for key in keys if (item := _count(value.get(key))) is not None), None)
    def detail(*containers, key):
        return next((item for name in containers if isinstance(value.get(name), dict) and
                     (item := _count(value[name].get(key))) is not None), None)
    usage = unknown_usage()
    usage.update(input_tokens=count("input_tokens", "prompt_tokens"), output_tokens=count("output_tokens", "completion_tokens"),
                 total_tokens=count("total_tokens"), cached_input_tokens=count("cached_input_tokens", "prompt_cache_hit_tokens"),
                 reasoning_output_tokens=count("reasoning_output_tokens"), uncached_input_tokens=count("uncached_input_tokens", "prompt_cache_miss_tokens"))
    if usage["cached_input_tokens"] is None:
        usage["cached_input_tokens"] = detail("input_tokens_details", "prompt_tokens_details", key="cached_tokens")
    if usage["reasoning_output_tokens"] is None:
        usage["reasoning_output_tokens"] = detail("output_tokens_details", "completion_tokens_details", key="reasoning_tokens")
    supplied = sum(usage[key] is not None for key in PRIMARY_COUNTS)
    usage["completeness"] = "complete" if supplied == 3 else "partial" if supplied else "unknown"
    return usage


def provider_usage_projection(value: Any) -> dict[str, Any]:
    """Retain allowlisted integer metadata only, without arbitrary diagnostics."""
    result = {"fields": {}, "invalid_fields": [], "conflicting_aliases": [], "capture_status": "unavailable", "unretained_fields": []}
    if not isinstance(value, dict):
        return result
    result["capture_status"] = "complete"
    counters = (*TOKEN_COUNTS, "prompt_tokens", "completion_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
    details = ("input_tokens_details", "prompt_tokens_details", "output_tokens_details", "completion_tokens_details")
    detail_counters = ("cached_tokens", "reasoning_tokens", "audio_tokens", "text_tokens", "image_tokens", "accepted_prediction_tokens", "rejected_prediction_tokens")
    for key in counters:
        if key in value:
            count = _count(value[key])
            if count is not None:
                result["fields"][key] = count
            elif value[key] is not None:
                result["invalid_fields"].append(key)
    for container in details:
        if container not in value or value[container] is None:
            continue
        if not isinstance(value[container], dict):
            result["invalid_fields"].append(container)
            continue
        retained = {}
        for key in detail_counters:
            if key not in value[container]:
                continue
            count = _count(value[container][key])
            if count is not None:
                retained[key] = count
            elif value[container][key] is not None:
                result["invalid_fields"].append(container + "." + key)
        result["fields"][container] = retained
    for aliases in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens")):
        counts = [_count(value.get(key)) for key in aliases]
        if None not in counts and counts[0] != counts[1]:
            result["conflicting_aliases"].append(list(aliases))
    # Exotic metadata cannot make the canonical lifecycle event unrecordable.
    # Normalized primary/subset counts remain separate and are not discarded.
    while len(canonical_json(result)) > 8192 and result["fields"]:
        key = next(reversed(result["fields"]))
        result["fields"].pop(key)
        result["capture_status"] = "bounded"
        result["unretained_fields"].append(key)
    return result
