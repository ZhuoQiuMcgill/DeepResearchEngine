"""Baseline research decisions; these do not belong to the generic Engine."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal

from deepresearch.workflows.contracts import Contract


class ResearchPlan(Contract):
    objective: str = Field(min_length=1, max_length=2048)
    questions: list[str] = Field(min_length=1, max_length=4)
    queries: list[str] = Field(min_length=1, max_length=4)
    outline: list[str] = Field(min_length=1, max_length=8)

    @field_validator("questions", "queries", "outline")
    @classmethod
    def bounded_text(cls, value, info):
        limit = {"questions": 1024, "queries": 4096, "outline": 256}[info.field_name]
        if any(not text.strip() or len(text.encode("utf-8")) > limit for text in value):
            raise ValueError("Plan contains blank or oversized text")
        if len(set(value)) != len(value):
            raise ValueError("Plan entries must be unique")
        return value


class Finding(BaseModel):
    model_config = Contract.model_config
    finding_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    question: str = Field(min_length=1, max_length=1024)
    claim: str = Field(min_length=1, max_length=2048)
    source_ids: list[str] = Field(min_length=1, max_length=8)


class EvidenceAnalysis(Contract):
    findings: list[Finding] = Field(min_length=1, max_length=24)
    gaps: list[str] = Field(max_length=8)
    follow_up_queries: list[str] = Field(max_length=2)
    sufficient: bool

    @model_validator(mode="after")
    def valid_decisions(self):
        if len({finding.finding_id for finding in self.findings}) != len(self.findings):
            raise ValueError("Finding identities must be unique")
        for text in self.gaps:
            if not text.strip() or len(text) > 1024:
                raise ValueError("Evidence gaps require bounded nonblank text")
        for query in self.follow_up_queries:
            if not query.strip() or len(query.encode("utf-8")) > 4096:
                raise ValueError("Follow-up queries require bounded literal text")
        return self


class ReportReview(Contract):
    verdict: Literal["accept", "revise"]
    issues: list[str] = Field(max_length=8)

    @model_validator(mode="after")
    def coherent_verdict(self):
        if (self.verdict == "accept") != (not self.issues):
            raise ValueError("Accepted reports have no issues; revisions require issues")
        if any(not issue.strip() or len(issue) > 1024 for issue in self.issues):
            raise ValueError("Review issues must be bounded nonblank text")
        return self
