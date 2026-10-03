"""Quote comparison returns only actual immutable source text."""
import pytest

from deepresearch.workflows.components.quotations import locate_quote


@pytest.mark.parametrize("quote,text,expected", [
    ("One two.", "prefix One\n  two. tail", "One\n  two."),
    ("These requirements work.", "These re-\nquirements work.", "These re-\nquirements work."),
    ("Therefore we continue.", "There-\nfore we continue.", "There-\nfore we continue."),
    ("This is knowl-\nedge.", "This is know-\nledge.", "This is know-\nledge."),
    ("Knowledge matters.", "Know- \r\n  ledge matters.", "Know- \r\n  ledge matters."),
    ("word- break", "word-\nbreak", "word-\nbreak"),
    ("😀 requirements", "UTF-8 😀 re-\nquirements tail", "😀 re-\nquirements"),
    ("two", "two first; two second", "two"),
    (" A short quote. ", "A short quote.", "A short quote."),
])
def test_locates_only_original_contiguous_substring(quote, text, expected):
    actual = locate_quote(quote, text)
    assert actual == expected and actual in text
    offset = len(text[:text.index(actual)].encode("utf-8"))
    assert text.encode("utf-8")[offset:offset + len(actual.encode("utf-8"))] == actual.encode("utf-8")


@pytest.mark.parametrize("quote,text", [
    ("invented evidence", "The saved source has no such passage."),
    ("Requirements", "requirements"),
    ("environment based", "environment-based"),
    ("1234", "12-\n34"),
    ("ID_foobar", "ID_foo-\nbar"),
    ("AB12", "A-\nB12"),
    ("plain text", "plain, text"),
    ("one two", "two one"),
    ("all requirements satisfied", "all design requirements satisfied"),
    ("definition", 'de"nition'),
    ("x = 1", "x = 2"),
    ("office", "oﬃce"),
])
def test_never_repairs_punctuation_letters_numbers_order_or_unknown_evidence(quote, text):
    assert locate_quote(quote, text) is None


@pytest.mark.parametrize("quote,text", [("", ""), ("   ", "source"), (None, "source"),
    ("a" * 2049, "a" * 2049), ("a", "a" * 65537), ("a", "😀" * 17000),
    ("\ud800", "source"), ("source", "\ud800")],
    ids=["empty", "whitespace", "type", "long-quote", "long-text", "utf8-text", "invalid-quote", "invalid-text"])
def test_invalid_or_oversized_values_cannot_match(quote, text):
    assert locate_quote(quote, text) is None


def test_source_span_bound_is_checked_after_soft_wrap_expansion():
    quote = "a" * 2048
    source = "a" * 1024 + "-\n" + "a" * 1024
    assert locate_quote(quote, source) is None
