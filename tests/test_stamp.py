from __future__ import annotations

import pytest

from app.extraction.stamp import is_implausible, parse_stamp

REAL_STAMPS = [
    ("Alvaro Mendonca Reis\nProctologia e Cirurgia\nCRM-MG: 41287", "41287", "MG", "ALVARO MENDONCA REIS"),
    ("Dr. Bruno Castelo Lima\nCRM MG 52914\nCBO 225265", "52914", "MG", "BRUNO CASTELO LIMA"),
    ("Dra. Helena Marques Dutra\nCardiologista\nCRM/SP 51.284", "51284", "SP", "HELENA MARQUES DUTRA"),
    ("Daniela Araujo Neves\nCRM: 47163 - RQE: 15149", "47163", None, "DANIELA ARAUJO NEVES"),
]


@pytest.mark.parametrize(("text", "number", "state", "name"), REAL_STAMPS)
def test_reads_registration_from_the_stamp(text, number, state, name):
    stamp = parse_stamp(text)

    assert stamp.council == "CRM"
    assert stamp.council_number == number
    assert stamp.council_state == state
    assert stamp.professional_name == name


def test_text_without_a_stamp_yields_nothing():
    stamp = parse_stamp("carimbo ilegível")

    assert not stamp.has_registration
    assert stamp.council_number is None


def test_empty_input_is_safe():
    assert parse_stamp(None).raw_text == ""
    assert parse_stamp("   ").council_number is None


@pytest.mark.parametrize("number", ["123456", "654321", "000000", "111111", "12", "12345678"])
def test_placeholder_numbers_are_rejected(number):
    assert is_implausible(number)


@pytest.mark.parametrize("number", ["41287", "52914", "4821", "123457"])
def test_real_looking_numbers_are_accepted(number):
    assert not is_implausible(number)


def test_invented_registration_does_not_reach_the_guide():
    stamp = parse_stamp("Alvaro Mendes Reis\nProctologista\nCRM 123456")

    assert stamp.has_registration is False
    assert stamp.rejected_number == "123456"
    assert stamp.professional_name == "ALVARO MENDES REIS"


def test_stamp_confirms_what_the_boxes_said():
    from app.extraction.pipeline import apply_stamp
    from app.schemas.guide import ExtractedField, FieldSource, SpSadtGuide

    guide = SpSadtGuide(
        council_number=ExtractedField(value="52914", source=FieldSource.OCR, confidence=0.6),
        professional_stamp=ExtractedField(value="Dr. Bruno Castelo Lima\nCRM MG 52914", source=FieldSource.LLM, confidence=0.75),
    )
    outcome = apply_stamp(guide)

    assert outcome["council_number"] == "confirmado"
    assert guide.council_number.confidence >= 0.97
    assert guide.council_number.note == "confirmado pelo carimbo"


def test_stamp_divergence_lowers_confidence_and_explains_itself():
    from app.extraction.pipeline import apply_stamp
    from app.schemas.guide import ExtractedField, FieldSource, SpSadtGuide

    guide = SpSadtGuide(
        council_number=ExtractedField(value="52914", source=FieldSource.OCR, confidence=0.95),
        professional_stamp=ExtractedField(value="Dr. Bruno Castelo Lima\nCRM MG 529114", source=FieldSource.LLM, confidence=0.75),
    )
    outcome = apply_stamp(guide)

    assert outcome["council_number"] == "divergente"
    assert guide.council_number.value == "52914"
    assert guide.council_number.confidence <= 0.4
    assert "529114" in guide.council_number.note


def test_stamp_fills_only_what_is_missing():
    from app.extraction.pipeline import apply_stamp
    from app.schemas.guide import ExtractedField, FieldSource, SpSadtGuide

    guide = SpSadtGuide(
        professional_stamp=ExtractedField(value="Dra. Helena Marques Dutra\nCRM/SP 51.284", source=FieldSource.LLM, confidence=0.75),
    )
    outcome = apply_stamp(guide)

    assert outcome["council_number"] == "preenchido"
    assert guide.council_number.value == "51284"
    assert guide.council_state.value == "SP"
    assert guide.council_number.note == "lido do carimbo do profissional"
