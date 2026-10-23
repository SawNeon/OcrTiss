from __future__ import annotations

import pytest

from app.config import get_settings
from app.extraction.pipeline import extract_page
from app.extraction.template_reader import LayoutNotRecognised, read_coded_fields
from app.extraction.triage import triage_pdf
from app.schemas.guide import ExtractionStrategy

MINIMUM_HIT_RATE = 0.5


@pytest.fixture(scope="module")
def settings():
    from dataclasses import replace

    return replace(get_settings(), llm_fallback_enabled=False, template_reader_enabled=True)


def test_reads_the_coded_fields_of_a_known_layout(guide_pdf, synthetic_guide, settings):
    reading = read_coded_fields(guide_pdf, 1, settings)

    expected = {
        name: "".join(character for character in value if character.isalnum())
        for name, value in synthetic_guide.ground_truth.items()
        if value
    }
    checked = {name: value for name, value in reading.values.items() if name in expected}
    hits = sum(1 for name, value in checked.items() if value == expected[name])

    assert reading.score > 0.45
    assert len(checked) >= 5
    assert hits / len(checked) >= MINIMUM_HIT_RATE


def test_never_fills_a_field_that_is_blank_on_the_form(guide_pdf, synthetic_guide, settings):
    reading = read_coded_fields(guide_pdf, 1, settings)
    blank = {name for name, value in synthetic_guide.ground_truth.items() if not value}

    invented = {
        name: reading.confidences[name]
        for name in set(reading.values) & blank
    }
    assert not invented, f"campos em branco preenchidos: {invented}"


def test_unknown_layout_is_refused_instead_of_invented(tmp_path, settings):
    import pymupdf

    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((80, 120), "RECEITUARIO MEDICO", fontsize=18)
    page.insert_text((80, 160), "Paciente: fulano de tal", fontsize=11)
    destination = tmp_path / "receituario.pdf"
    document.save(destination)
    document.close()

    with pytest.raises(LayoutNotRecognised):
        read_coded_fields(destination, 1, settings)


def test_pipeline_degrades_to_manual_without_crashing(tmp_path, settings):
    import pymupdf

    document = pymupdf.open()
    document.new_page(width=595, height=842)
    destination = tmp_path / "branco.pdf"
    document.save(destination)
    document.close()

    result = extract_page(destination, 1, triage_pdf(destination)[0], settings)

    assert result.strategy is ExtractionStrategy.MANUAL
    assert result.needs_human_review is True
    assert result.warnings
