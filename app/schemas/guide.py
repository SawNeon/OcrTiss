from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FieldSource(str, Enum):
    TEXT_LAYER = "text_layer"
    OCR = "ocr"
    CHECKBOX = "checkbox"
    LLM = "llm"
    REGISTRY = "registry"
    HUMAN = "human"


class ExtractionStrategy(str, Enum):
    TEXT_LAYER = "text_layer"
    OCR = "ocr"
    LLM = "llm"
    TEMPLATE = "template"
    HYBRID = "hybrid"
    MANUAL = "manual"


class ExtractedField(BaseModel):
    value: str | None = None
    source: FieldSource
    confidence: float = Field(ge=0.0, le=1.0)
    is_valid: bool | None = None
    note: str | None = None


class Procedure(BaseModel):
    table: ExtractedField | None = None
    code: ExtractedField | None = None
    description: ExtractedField | None = None
    requested_quantity: ExtractedField | None = None
    authorized_quantity: ExtractedField | None = None


class SpSadtGuide(BaseModel):
    provider_guide_number: ExtractedField | None = None
    main_guide_number: ExtractedField | None = None
    ans_registration: ExtractedField | None = None
    operator_guide_number: ExtractedField | None = None
    authorization_date: ExtractedField | None = None
    password: ExtractedField | None = None
    password_expiry_date: ExtractedField | None = None

    member_card_number: ExtractedField | None = None
    card_expiry_date: ExtractedField | None = None
    member_name: ExtractedField | None = None
    member_social_name: ExtractedField | None = None
    newborn_care: ExtractedField | None = None
    national_health_card: ExtractedField | None = None

    requester_operator_code: ExtractedField | None = None
    requester_provider_name: ExtractedField | None = None
    requesting_professional_name: ExtractedField | None = None
    professional_council: ExtractedField | None = None
    council_number: ExtractedField | None = None
    council_state: ExtractedField | None = None
    cbo_code: ExtractedField | None = None

    care_type: ExtractedField | None = None
    request_date: ExtractedField | None = None
    clinical_indication: ExtractedField | None = None
    procedures: list[Procedure] = Field(default_factory=list)

    cnes_code: ExtractedField | None = None
    consultation_type: ExtractedField | None = None

    hospital_operator_code: ExtractedField | None = None
    hospital_name: ExtractedField | None = None
    suggested_admission_date: ExtractedField | None = None
    admission_type: ExtractedField | None = None
    admission_regime: ExtractedField | None = None
    requested_daily_rates: ExtractedField | None = None
    opme_forecast: ExtractedField | None = None
    chemotherapy_forecast: ExtractedField | None = None
    main_icd10: ExtractedField | None = None
    icd10_2: ExtractedField | None = None
    icd10_3: ExtractedField | None = None
    icd10_4: ExtractedField | None = None
    accident_indication: ExtractedField | None = None
    notes: ExtractedField | None = None
    professional_stamp: ExtractedField | None = None
    professional_specialty: ExtractedField | None = None

    def filled_fields(self) -> dict[str, ExtractedField]:
        return {
            name: value
            for name, value in self
            if isinstance(value, ExtractedField) and value.value
        }


class ExtractionResult(BaseModel):
    file_name: str
    page_number: int
    strategy: ExtractionStrategy
    guide: SpSadtGuide | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    needs_human_review: bool = False
