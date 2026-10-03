# Retained research content token measurement

`deepresearch.engine.providers.tokenization.TokenMeter` measures supplied text locally.
It does not open a model conversation, make HTTP or container calls, discover a
tokenizer, download tokenizer files or read retained Storage content. The host
reads the authorized text and explicitly registers any locally available
verified tokenizer callback.

The service returns a frozen engine-native `TokenCount`. Its fields match the
shared workflow `TokenMeasurement` wire contract, including `schema_version: 1`.
`to_dict()` returns a fresh dictionary. Workflow code converts at its boundary:

```python
from deepresearch.engine.providers.tokenization import TokenMeter
from deepresearch.workflows.contracts import TokenMeasurement

meter = TokenMeter()
content = "Retained research evidence: 雪🙂"
measurement = meter.measure(content, "research-model")
workflow_measurement = TokenMeasurement.model_validate(measurement.to_dict())
assert workflow_measurement.kind == "estimated"
```

The engine tokenization package imports no workflow, method or interface code.
These measurements describe prospective content. Provider usage received after
a model call has its own accounting and must be recorded separately.

## API

```python
meter.register(model_ref, tokenizer_id, tokenizer_revision, count_callback)
meter.measure(
    text, model_ref, scope="selected", rendering_revision="source-text/1",
    require_verified=False,
)  # -> TokenCount
meter.estimate_document(text_bytes, text_sha256, model_ref)  # -> TokenCount
meter.fit(
    text, model_ref, token_budget, max_text_bytes, require_verified=False,
)  # -> (selected_text, TokenCount, truncated)
```

`register` binds one exact model reference to a named, pinned tokenizer revision
and a synchronous `count_callback(text: str) -> int`. The trusted host is
responsible for supplying a local deterministic callback that implements that
revision. Registration makes no verification or discovery call. The callback
receives the complete supplied string and must return a nonnegative integer;
booleans, floats, nulls and awaitables are invalid. Replacing a registration
invalidates measurements for that model, even when the declared names are the
same. No production tokenizer mapping is preconfigured.

`measure` hashes and sizes the actual UTF-8 text without normalization or added
wrappers. Scope is `document`, `selected` or `assembled`. Rendering revision
identifies the caller's format; the caller must render the actual content before
measuring it. A registered callback yields `kind="verified"`, its tokenizer
identity/revision, its count and `estimator=null`. Verification is conditional on
the host's pinned callback being correct for the selected model.

Without registration, `measure` returns `kind="estimated"`,
`estimator="utf8-byte-size/4"`, `count=(text_bytes + 3) // 4` and null tokenizer
fields. Empty text estimates zero. This heuristic is an advisory size estimate;
it is neither an exact token count nor a conservative token-budget guarantee.
`require_verified=True` raises `EngineError(code="UNVERIFIED_TOKENIZER")` when
that model has no registered callback, including for empty input.

`estimate_document` accepts a nonnegative integer byte size and an existing
`sha256:` descriptor with 64 lowercase hexadecimal digits. It always returns the
named byte estimate with `scope="document"` and
`rendering_revision="source-text/1"`; size and hash alone cannot establish an
exact count. A registered model's tokenizer fields identify the target profile,
but the callback is not called and `kind` remains `estimated`. Unsupported
models have null tokenizer fields. The caller supplies retained metadata; the
service cannot independently check its hash without the text.

`fit` accepts nonnegative integer token and byte limits, including zero. It first
caps UTF-8 bytes at a complete Unicode code point, then measures whole candidate
prefixes to select a prefix within the measured budget. The returned count,
byte size and hash belong to the final selected text. `truncated` reports whether
any original text was removed. Code point boundaries preserve valid UTF-8; a
combining sequence or displayed grapheme can still be shortened.

A single callback registration is pinned across a fit. Binary search retains
only prefixes actually measured within budget; tokenizer prefix counts can be
nonmonotonic, so the selection may be shorter than the longest possible fit.
If even empty text's callback count exceeds the budget, fitting raises
`EngineError(code="INVALID_DATA")`. A strict fit bounds only the supplied
content under its verified callback. Estimated fitting still provides no actual
token-budget guarantee. Instructions, schemas, history, wrappers and output
reservation need separate handling in the actual request budget.

Tokenization across a boundary can merge or split tokens. Counts of separately
measured selections therefore need not sum to the count of their assembled
text. Measure the final rendered assembly using `scope="assembled"` when
planning its actual contribution.

## Local verified callback

Given a tokenizer already loaded by the trusted host from pinned local files:

```python
# local_tokenizer is supplied by the host; this service does not load it.
meter.register(
    "research-model", "host/local-tokenizer", "immutable-local-revision",
    lambda text: len(local_tokenizer.encode(text, add_special_tokens=False)),
)
selected_text, count, truncated = meter.fit(
    content, "research-model", token_budget=1024, max_text_bytes=16384,
    require_verified=True,
)
assert count.kind == "verified"
assert count.count <= 1024
assert count.text_bytes == len(selected_text.encode("utf-8"))
```

The host chooses callback handling of special tokens and must match the intended
content rendering. This example requires no new service dependency and does not
claim support for any particular provider's full request encoding.

## Cache and errors

The in-memory cache retains at most 1,024 immutable measurement records and no
source text. Keys include model reference, tokenizer identity and revision,
text SHA-256, rendering revision, scope, byte size and measurement kind/estimator.
An internal registration identity also separates replacement callbacks. Document
estimates cannot populate a verified document count. Serialization copies and
frozen records prevent callers from mutating cached metadata.

Malformed inputs, callback failures and invalid callback counts raise
`EngineError(code="INVALID_DATA")`. Callback exception messages and supplied
text are omitted from the error. Failed counts are never cached or silently
replaced with estimates. Missing strict support raises `UNVERIFIED_TOKENIZER`.

Run the focused checks in the existing locked environment:

```powershell
uv --cache-dir .uv-cache run --locked --offline pytest tests/workflows/test_tokenization.py -q
```
