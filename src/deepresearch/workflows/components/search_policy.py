"""Workflow-owned query preparation and metadata screening, without models/I/O."""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


def terms(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return tuple(dict.fromkeys(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", normalized)))


def infer_topic(question):
    """Infer only a definition subject or an adjacent, matching acronym expansion.

    Parenthesized capacities, dates and audience constraints are not the topic.
    Comparison questions deliberately have no single inferred subject.
    """
    for match in re.finditer(r"\b([A-Z]{2,10})\s*[（(]([^()（）]{3,256})[）)]", question):
        acronym, phrase = match.groups()
        words = re.findall(r"[A-Za-z]+", phrase)
        significant = [word for word in words if word.lower() not in {"of", "the", "and", "for", "in"}]
        if len(words) >= 2 and acronym.lower() in {
                "".join(word[0].lower() for word in words),
                "".join(word[0].lower() for word in significant)}:
            return phrase.strip()
    match = re.match(r"\s*(?:what\s+is|define|explain)\s+(?:the\s+)?([^?(),;]{3,256})", question, re.I)
    if match:
        phrase = re.split(r"\s+and\s+(?:what|how|why|its)\b", match.group(1), flags=re.I)[0].strip().strip('"“”')
        if 2 <= len(terms(phrase)) <= 8:
            return phrase
    return None


@dataclass(frozen=True)
class SearchPolicy:
    topic: str | None = None

    def prepare(self, query, source_ids=(), *, rewrite=True):
        for identity in source_ids:
            if re.search(r"(?<![\w.-])" + re.escape(identity) + r"(?![\w.-])", query):
                return None, "references_retained_source"
        if not rewrite:
            return query, "host_literal_query"
        quoted = re.findall(r'"([^"\n]{3,512})"', query)
        if re.match(r"\s*(?:retrieve|fetch|read|obtain|download)\b", query, re.I) and quoted:
            # A cited title is useful search input; surrounding retrieval
            # instructions and private source identifiers are not.
            authors = re.findall(r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})['’]s\b", query)
            years = re.findall(r"\b(?:19|20)\d{2}\b", query)
            identifiers = list(dict.fromkeys(authors + years[:1]))
            return " ".join(['"' + quoted[0] + '"', *identifiers]), "quoted_title_from_retrieval_request"
        if not self.topic:
            return query, "literal_query"
        words = terms(self.topic)
        if not words or any(not re.fullmatch(r"[a-z0-9]+", word) for word in words):
            return query, "literal_query"
        pattern = r"(?<!\w)" + r"[\s\-–—]+".join(re.escape(word) for word in words) + r"(?!\w)"
        match = re.search(pattern, query, re.I)
        if not match or (match.start() > 0 and query[match.start() - 1] == '"'):
            return query, "literal_query"
        subject = query[match.start():match.end()]
        rewritten = query[:match.start()] + '"' + subject + '"' + query[match.end():]
        rewritten = re.sub(r"^\s*what\s+is\s+", "", rewritten, flags=re.I)
        if len(rewritten.encode("utf-8")) > 4096:
            return query, "literal_query_at_byte_limit"
        return rewritten, "quoted_topic"

    def screen(self, rows):
        required = terms(self.topic or "")
        accepted, decisions = [], []
        for index, row in enumerate(rows, 1):
            title = row.get("title") or " ".join(row.get("titles", []))
            text = " ".join((title, row.get("snippet") or ""))
            actual = set(terms(text))
            missing = [term for term in required if term not in actual]
            keep = not missing
            decisions.append({"rank":row.get("rank", index),"title":title,"accepted":keep,
                "reason":"topic_terms_present" if required and keep else "topic_terms_missing" if required else "no_explicit_topic",
                "missing_terms":missing})
            if keep:
                accepted.append(row)
        return accepted, decisions
