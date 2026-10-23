from __future__ import annotations

import pytest

from app.extraction.pipeline import apply_registry
from app.learning import database
from app.learning.feedback import (
    common_mistakes,
    field_accuracy,
    learn_professional,
    record_approval,
    record_correction,
)
from app.learning.professionals import Professional, count, resolve, upsert
from app.schemas.guide import ExtractedField, FieldSource, SpSadtGuide

REGISTRY = [
    Professional("CRM", "41287", "MG", "ALVARO MENDONCA REIS", "Proctologia"),
    Professional("CRM", "52914", "MG", "BRUNO CASTELO LIMA", "Ortopedia"),
    Professional("CRM", "72641", "MG", "TATIANE REZENDE CAMPOS", "Pediatria"),
]


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "learning.db"
    monkeypatch.setattr(database, "DEFAULT_PATH", path)
    with database.session(path) as connection:
        for professional in REGISTRY:
            upsert(connection, professional, source="planilha")
    return path


def test_registry_holds_the_imported_people(db):
    with database.session(db) as connection:
        assert count(connection) == len(REGISTRY)


def test_exact_registration_is_applied_automatically(db):
    with database.session(db) as connection:
        match = resolve(connection, "41287", None, None)

    assert match.apply_automatically is True
    assert match.professional.specialty == "Proctologia"


def test_name_plus_near_number_corrects_the_reading(db):
    with database.session(db) as connection:
        match = resolve(connection, "529114", None, "BRUNO CASTELO LIMA")

    assert match.apply_automatically is True
    assert match.corrects_number is True
    assert match.professional.council_number == "52914"


def test_similar_name_alone_is_only_a_suggestion(db):
    """TATIANA and TATIANE are different people: a name cannot decide identity."""
    with database.session(db) as connection:
        match = resolve(connection, None, None, "TATIANA REZENDE CAMPOS")

    assert match is not None
    assert match.apply_automatically is False


def test_pipeline_applies_the_registry_to_the_guide(db, monkeypatch):
    monkeypatch.setattr("app.extraction.pipeline.session", lambda *args, **kwargs: database.session(db))

    guide = SpSadtGuide(
        council_number=ExtractedField(value="529114", source=FieldSource.LLM, confidence=0.7),
        requesting_professional_name=ExtractedField(value="BRUNO CASTELO LIMA", source=FieldSource.LLM, confidence=0.75),
    )
    outcome = apply_registry(guide)

    assert outcome["corrected_number"] is True
    assert guide.council_number.value == "52914"
    assert guide.council_number.source is FieldSource.REGISTRY
    assert guide.professional_specialty.value == "Ortopedia"


def test_pipeline_only_suggests_when_the_name_stands_alone(db, monkeypatch):
    monkeypatch.setattr("app.extraction.pipeline.session", lambda *args, **kwargs: database.session(db))

    guide = SpSadtGuide(
        requesting_professional_name=ExtractedField(value="TATIANA REZENDE CAMPOS", source=FieldSource.LLM, confidence=0.75),
    )
    outcome = apply_registry(guide)

    assert outcome["suggestions"][0]["label"].startswith("TATIANE REZENDE CAMPOS")
    assert guide.council_number is None


def test_corrections_and_approvals_build_the_accuracy_record(db):
    fields = [
        {"name": "council_number", "value": "52914", "source": "ocr", "confidence": 0.9},
        {"name": "ans_registration", "value": "344729", "source": "ocr", "confidence": 1.0},
    ]
    with database.session(db) as connection:
        record_correction(connection, "abc", "member_card_number", "123", "456", "ocr", 0.4)
        record_correction(connection, "def", "member_card_number", "123", "456", "ocr", 0.4)
        record_approval(connection, "abc", fields)

        accuracy = {item.field_name: item for item in field_accuracy(connection)}
        mistakes = common_mistakes(connection)

    assert accuracy["member_card_number"].corrected == 2
    assert accuracy["member_card_number"].hit_rate == 0.0
    assert accuracy["council_number"].hit_rate == 1.0
    assert mistakes[0]["occurrences"] == 2


def test_approved_guide_registers_an_unknown_professional(db):
    fields = [
        {"name": "council_number", "value": "19758", "source": "ocr", "confidence": 0.9},
        {"name": "council_state", "value": "RJ", "source": "ocr", "confidence": 0.9},
        {"name": "requesting_professional_name", "value": "EDUARDO NASCIMENTO PRADO", "source": "human", "confidence": 1.0},
        {"name": "professional_specialty", "value": "Neurologia", "source": "human", "confidence": 1.0},
    ]
    with database.session(db) as connection:
        label = learn_professional(connection, fields)
        found = resolve(connection, "19758", "RJ", None)

    assert "EDUARDO NASCIMENTO PRADO" in label
    assert found.professional.specialty == "Neurologia"
