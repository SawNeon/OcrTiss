from __future__ import annotations

from lxml import etree

from app.output.tiss_xml import TISS_NAMESPACE, to_xml
from app.schemas.guide import ExtractedField, FieldSource, Procedure, SpSadtGuide

NS = {"ans": TISS_NAMESPACE}


def field(value: str) -> ExtractedField:
    return ExtractedField(value=value, source=FieldSource.OCR, confidence=0.9)


def sample_guide() -> SpSadtGuide:
    guide = SpSadtGuide(
        provider_guide_number=field("401286"),
        ans_registration=field("344729"),
        member_card_number=field("33260489399723185"),
        member_name=field("JOAQUIM OLIVEIRA MENDES"),
        council_number=field("52914"),
        council_state=field("MG"),
        request_date=field("12092026"),
    )
    guide.procedures = [Procedure(table=field("22"), code=field("31403336"), requested_quantity=field("05"))]
    return guide


def test_message_has_the_expected_skeleton():
    root = etree.fromstring(to_xml(sample_guide()).encode())

    assert root.tag == f"{{{TISS_NAMESPACE}}}mensagemTISS"
    assert root.find("ans:cabecalho/ans:versaoPadrao", NS).text == "4.01.00"
    assert root.find(".//ans:numeroCarteira", NS).text == "33260489399723185"
    assert root.find(".//ans:codigoProcedimento", NS).text == "31403336"


def test_dates_are_converted_to_iso():
    root = etree.fromstring(to_xml(sample_guide()).encode())
    assert root.find(".//ans:dataSolicitacao", NS).text == "2026-09-12"


def test_empty_fields_do_not_become_empty_tags():
    root = etree.fromstring(to_xml(SpSadtGuide()).encode())
    assert root.find(".//ans:numeroCarteira", NS) is None


def test_epilogue_hash_changes_with_content():
    first = etree.fromstring(to_xml(sample_guide()).encode()).find("ans:epilogo/ans:hash", NS).text

    other = sample_guide()
    other.member_card_number = field("11111111111111111")
    second = etree.fromstring(to_xml(other).encode()).find("ans:epilogo/ans:hash", NS).text

    assert len(first) == 32
    assert first != second
