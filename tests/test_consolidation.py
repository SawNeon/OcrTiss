from __future__ import annotations

from app.output.consolidation import build_payload
from app.schemas.guide import (
    ExtractedField,
    ExtractionResult,
    ExtractionStrategy,
    FieldSource,
    SpSadtGuide,
)


def result_with(**fields) -> ExtractionResult:
    guide = SpSadtGuide(**fields)
    return ExtractionResult(
        file_name="guia.pdf", page_number=1, strategy=ExtractionStrategy.TEMPLATE, guide=guide
    )


def test_fields_carry_the_printed_label_and_section():
    payload = build_payload(
        result_with(member_card_number=ExtractedField(value="123", source=FieldSource.OCR, confidence=1.0))
    )
    card = next(item for item in payload["fields"] if item["name"] == "member_card_number")

    assert card["number"] == "7"
    assert card["label"] == "Número da Carteira"
    assert card["section"] == "Dados do Beneficiário"


def test_low_confidence_is_flagged_for_review():
    payload = build_payload(
        result_with(cbo_code=ExtractedField(value="225125", source=FieldSource.OCR, confidence=0.4))
    )
    cbo = next(item for item in payload["fields"] if item["name"] == "cbo_code")

    assert cbo["needs_review"] is True
    assert payload["summary"]["fields_to_review"] == 1


def test_failed_validation_is_flagged_even_with_high_confidence():
    payload = build_payload(
        result_with(main_icd10=ExtractedField(value="6502", source=FieldSource.OCR, confidence=1.0, is_valid=False))
    )
    icd = next(item for item in payload["fields"] if item["name"] == "main_icd10")

    assert icd["needs_review"] is True


def test_field_without_rule_is_not_flagged_when_confident():
    payload = build_payload(
        result_with(council_number=ExtractedField(value="52914", source=FieldSource.OCR, confidence=1.0))
    )
    council = next(item for item in payload["fields"] if item["name"] == "council_number")

    assert council["needs_review"] is False
    assert payload["summary"]["automatic_rate"] == 1.0


def test_empty_optional_field_is_not_a_pending_task():
    payload = build_payload(result_with())
    optional = next(item for item in payload["fields"] if item["name"] == "password")

    assert optional["value"] is None
    assert optional["needs_review"] is False
    assert optional["required"] is False


def test_empty_required_field_is_pending():
    payload = build_payload(result_with())
    required = next(item for item in payload["fields"] if item["name"] == "member_card_number")

    assert required["required"] is True
    assert required["needs_review"] is True


def test_value_confirmed_by_a_person_leaves_the_queue():
    payload = build_payload(
        result_with(council_number=ExtractedField(value="52914", source=FieldSource.HUMAN, confidence=1.0))
    )
    field = next(item for item in payload["fields"] if item["name"] == "council_number")

    assert field["needs_review"] is False
