"""Versioned baseline evidence decisions, separate from platform authority."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator
from deepresearch.workflows.contracts import Contract, SourceRange
from .contracts import EvidenceAnalysis


class ExtractedFinding(BaseModel):
    model_config = Contract.model_config
    question: str = Field(min_length=1, max_length=1024)
    claim: str = Field(min_length=1, max_length=1536)
    segment_id: str = Field(min_length=1, max_length=160)
    quote: str = Field(min_length=1, max_length=2048)


class SourceDistillation(Contract):
    source_id: str = Field(min_length=1, max_length=128)
    chunk_id: str = Field(min_length=1, max_length=160)
    content_kind: Literal["substantive", "abstract", "bibliography", "irrelevant"]
    summary: str = Field(min_length=1, max_length=4096)
    findings: list[ExtractedFinding] = Field(max_length=12)
    limitations: list[str] = Field(max_length=6)
    reference_queries: list[str] = Field(max_length=3)

    @field_validator("limitations", "reference_queries")
    @classmethod
    def bounded_strings(cls, values):
        if any(not value.strip() or len(value) > 1024 for value in values):
            raise ValueError("Distillation strings must be bounded and nonblank")
        return values


class EvidenceReadRequest(BaseModel):
    model_config = Contract.model_config
    source_id: str = Field(min_length=1, max_length=128)
    range: SourceRange
    reason: str = Field(min_length=1, max_length=1024)


class DistilledAnalysis(EvidenceAnalysis):
    follow_up_reads: list[EvidenceReadRequest] = Field(max_length=8)
    _reported_sufficient: bool = PrivateAttr(default=False)
    _read_adjustments: list = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def sufficient_has_no_missing_evidence(self):
        self._reported_sufficient = self.sufficient
        if self.sufficient and (self.gaps or self.follow_up_reads):
            # Treat a contradictory self-assessment conservatively. Preserve
            # raw model output separately and record this host downgrade.
            self.sufficient = False
        return self
