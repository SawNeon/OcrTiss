from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FieldCorrection(BaseModel):
    value: str | None = Field(default=None, description="Valor corrigido pelo revisor")
    author: str = "demo"


class ReviewDecision(BaseModel):
    decision: str = Field(description="aprovado | negado | pendente")
    note: str | None = None
    author: str = "demo"


class ExtractionSummary(BaseModel):
    id: str
    original_name: str
    created_at: str
    page_count: int
    strategy: str
    fields_read: int
    fields_to_review: int


class ExtractionResponse(BaseModel):
    id: str
    original_name: str
    created_at: str
    page_count: int
    payload: dict[str, Any]
    audit: list[dict[str, Any]]
