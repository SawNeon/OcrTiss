"""Turns an extraction result into the payload the API and the review screen consume.

The reader produces field names; a person reviewing a guide needs the printed
label and the section it belongs to, plus a clear verdict on what to check.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.schemas.guide import ExtractedField, ExtractionResult, FieldSource, SpSadtGuide
from app.synthetic.layout import FIELDS, SECTIONS

REVIEW_THRESHOLD = 0.9
PROCEDURE_LABELS = {
    "table": "Tabela",
    "code": "Código do Procedimento",
    "description": "Descrição",
    "requested_quantity": "Qtde. Solicitada",
    "authorized_quantity": "Qtde. Autorizada",
}


@dataclass
class FieldView:
    name: str
    number: str
    label: str
    section: str
    value: str | None
    source: str | None
    confidence: float | None
    validated: bool | None
    needs_review: bool
    required: bool
    note: str | None


def _section_of(top: int) -> str:
    current = "Identificação da Guia"
    for section in SECTIONS:
        if section.top <= top:
            current = section.label
    return current


EXTRA_FIELDS = {
    "provider_guide_number": ("2", "Nº da Guia no Prestador", "Identificação da Guia"),
    "main_guide_number": ("3", "Nº da Guia Principal", "Identificação da Guia"),
    "member_social_name": ("10", "Nome Social", "Dados do Beneficiário"),
    "consultation_type": ("", "Tipo de Consulta", "Dados do Atendimento"),
    "professional_stamp": ("", "Carimbo do profissional", "Dados do Contratado Solicitante"),
    "professional_specialty": ("", "Especialidade", "Dados do Contratado Solicitante"),
}

# Sem estes a guia não é lançada no Cardio, então um campo vazio aqui é pendência;
# os demais, em branco no papel, apenas ficam registrados como não preenchidos.
REQUIRED_FIELDS = frozenset({
    "member_card_number",
    "member_name",
    "request_date",
    "requesting_professional_name",
    "council_number",
})


def _field_catalogue() -> dict[str, tuple[str, str, str]]:
    catalogue = {
        form_field.name: (form_field.number, form_field.label, _section_of(form_field.top))
        for form_field in FIELDS
    }
    catalogue.update(EXTRA_FIELDS)
    return catalogue


def _needs_review(name: str, field: ExtractedField | None) -> bool:
    """A field only joins the queue if there is something to decide about it."""
    if field is None or not field.value:
        return name in REQUIRED_FIELDS
    if field.source is FieldSource.HUMAN:
        return False
    if field.is_valid is False:
        return True
    return field.confidence < REVIEW_THRESHOLD


def _to_view(name: str, field: ExtractedField | None, catalogue) -> FieldView:
    number, label, section = catalogue.get(name, ("", name, "Outros"))
    return FieldView(
        name=name,
        number=number,
        label=label,
        section=section,
        value=field.value if field else None,
        source=field.source.value if field else None,
        confidence=round(field.confidence, 2) if field else None,
        validated=field.is_valid if field else None,
        needs_review=_needs_review(name, field),
        required=name in REQUIRED_FIELDS,
        note=field.note if field else None,
    )


def guide_fields(guide: SpSadtGuide) -> list[FieldView]:
    catalogue = _field_catalogue()
    views = [
        _to_view(name, value, catalogue)
        for name, value in guide
        if not isinstance(value, list)
    ]
    return [view for view in views if view.value or view.name in catalogue]


def guide_procedures(guide: SpSadtGuide) -> list[dict[str, Any]]:
    procedures = []
    for index, procedure in enumerate(guide.procedures, start=1):
        row: dict[str, Any] = {"row": index}
        for attribute, label in PROCEDURE_LABELS.items():
            field: ExtractedField | None = getattr(procedure, attribute, None)
            row[attribute] = {
                "label": label,
                "value": field.value if field else None,
                "confidence": round(field.confidence, 2) if field else None,
                "source": field.source.value if field else None,
                "needs_review": _needs_review(attribute, field),
            }
        procedures.append(row)
    return procedures


def build_payload(result: ExtractionResult) -> dict[str, Any]:
    fields = guide_fields(result.guide) if result.guide else []
    filled = [field for field in fields if field.value]
    to_review = [field for field in filled if field.needs_review]

    return {
        "file_name": result.file_name,
        "page_number": result.page_number,
        "strategy": result.strategy.value,
        "warnings": result.warnings,
        "diagnostics": result.diagnostics,
        "summary": {
            "fields_read": len(filled),
            "fields_to_review": len(to_review),
            "fields_empty": len(fields) - len(filled),
            "automatic_rate": round(1 - len(to_review) / len(filled), 2) if filled else 0.0,
        },
        "fields": [asdict(field) for field in fields],
        "procedures": guide_procedures(result.guide) if result.guide else [],
        "suggestions": result.diagnostics.get("registry", {}).get("suggestions", []),
    }
