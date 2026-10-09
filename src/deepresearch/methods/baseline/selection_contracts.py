"""Baseline candidate selection decisions; acquisition authority stays with the host."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from deepresearch.workflows.contracts import Contract


class SelectionChoice(BaseModel):
    model_config = Contract.model_config
    candidate_id: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=1, max_length=1024)

    @field_validator("candidate_id", "reason")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Selection identities and reasons must be nonblank")
        # Preserve exact host identities rather than normalizing model output.
        return value


class SelectionDecision(Contract):
    """Ordered immediate choices, viable reserves and exclusions.

    The host separately checks delivered-ID membership, exhaustive classification
    and the current fetch/batch budgets against the input for this decision.
    """

    selections: list[SelectionChoice] = Field(max_length=20)
    deferred: list[SelectionChoice] = Field(max_length=128)
    rejected: list[SelectionChoice] = Field(max_length=128)

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_schema_version(cls, value):
        if type(value) is not int:
            raise ValueError("Selection schema version must be an integer")
        return value

    @model_validator(mode="after")
    def unique_candidate_ids(self):
        identities = [choice.candidate_id for choices in (
            self.selections, self.deferred, self.rejected
        ) for choice in choices]
        if len(set(identities)) != len(identities):
            duplicate = list(dict.fromkeys(identity for identity in identities if identities.count(identity) > 1))
            raise ValueError("Candidate identities must be unique across all selection lists; duplicates: " + ", ".join(duplicate[:16]))
        return self
