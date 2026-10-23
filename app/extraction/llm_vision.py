from __future__ import annotations

import base64

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.schemas.guide import ExtractedField, FieldSource, Procedure, SpSadtGuide

DEFAULT_CONFIDENCE = 0.75
LOW_CONFIDENCE = 0.3

SYSTEM_PROMPT = (
    "You read Brazilian TISS SP/SADT medical guides. "
    "Transcribe only what is visible, character by character. "
    "Never infer, complete or correct a value from context. "
    "Return an empty string for any field you cannot read with certainty, "
    "and list every uncertain or empty field in low_confidence_fields. "
    "Copy the professional's stamp verbatim into professional_stamp, keeping its line breaks: "
    "it usually carries the name, the specialty and the council registration."
)


class LlmExtractionError(RuntimeError):
    pass


class LlmFallbackUnavailable(LlmExtractionError):
    pass


class ProcedureReading(BaseModel):
    table: str = ""
    code: str = ""
    description: str = ""
    requested_quantity: str = ""
    authorized_quantity: str = ""


class GuideReading(BaseModel):
    provider_guide_number: str = ""
    main_guide_number: str = ""
    ans_registration: str = ""
    operator_guide_number: str = ""
    authorization_date: str = ""
    password: str = ""
    password_expiry_date: str = ""
    member_card_number: str = ""
    card_expiry_date: str = ""
    member_name: str = ""
    member_social_name: str = ""
    newborn_care: str = ""
    requester_operator_code: str = ""
    requester_provider_name: str = ""
    requesting_professional_name: str = ""
    professional_council: str = ""
    council_number: str = ""
    council_state: str = ""
    cbo_code: str = ""
    care_type: str = ""
    request_date: str = ""
    clinical_indication: str = ""
    cnes_code: str = ""
    consultation_type: str = ""
    national_health_card: str = ""
    hospital_operator_code: str = ""
    hospital_name: str = ""
    suggested_admission_date: str = ""
    admission_type: str = ""
    admission_regime: str = ""
    requested_daily_rates: str = ""
    opme_forecast: str = ""
    chemotherapy_forecast: str = ""
    main_icd10: str = ""
    icd10_2: str = ""
    icd10_3: str = ""
    icd10_4: str = ""
    accident_indication: str = ""
    notes: str = ""
    professional_stamp: str = ""
    procedures: list[ProcedureReading] = Field(default_factory=list)
    low_confidence_fields: list[str] = Field(default_factory=list)


class LlmVisionExtractor:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        if not self._settings.llm_available:
            raise LlmFallbackUnavailable(
                "LLM fallback is disabled or OPENAI_API_KEY is missing; see .env.example"
            )
        self._client = OpenAI(api_key=self._settings.openai_api_key)

    def extract(self, page_png: bytes) -> SpSadtGuide:
        reading = self._read(page_png)
        return self._to_guide(reading)

    def _read(self, page_png: bytes) -> GuideReading:
        return self._call(page_png, SYSTEM_PROMPT, "Extract the fields of this guide.", GuideReading)

    def _call(self, image_png: bytes, system_prompt: str, instruction: str, response_format):
        image_url = f"data:image/png;base64,{base64.b64encode(image_png).decode()}"
        try:
            completion = self._client.chat.completions.parse(
                model=self._settings.openai_model,
                temperature=0,
                response_format=response_format,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": instruction},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    },
                ],
            )
        except OpenAIError as error:
            raise LlmExtractionError(str(error)) from error

        reading = completion.choices[0].message.parsed
        if reading is None:
            raise LlmExtractionError("model returned no structured content")
        return reading

    def _to_guide(self, reading: GuideReading) -> SpSadtGuide:
        uncertain = set(reading.low_confidence_fields)

        def to_field(name: str, value: str) -> ExtractedField | None:
            if not value.strip():
                return None
            return ExtractedField(
                value=value.strip(),
                source=FieldSource.LLM,
                confidence=LOW_CONFIDENCE if name in uncertain else DEFAULT_CONFIDENCE,
            )

        scalar_fields = reading.model_dump(exclude={"procedures", "low_confidence_fields"})
        guide = SpSadtGuide(
            **{name: to_field(name, value) for name, value in scalar_fields.items()}
        )
        guide.procedures = [
            Procedure(
                table=to_field("procedures", item.table),
                code=to_field("procedures", item.code),
                description=to_field("procedures", item.description),
                requested_quantity=to_field("procedures", item.requested_quantity),
                authorized_quantity=to_field("procedures", item.authorized_quantity),
            )
            for item in reading.procedures
        ]
        return guide
