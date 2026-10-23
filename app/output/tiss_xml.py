"""Builds the TISS message for an extracted guide.

Draft until two things are confirmed with whoever maintains the Cardio
integration: the schema version in use and the XSD to validate against. The
element names follow TISS 4.01.00 and the version is a parameter, so swapping
it is a configuration change, not a rewrite.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime

from lxml import etree

from app.schemas.guide import SpSadtGuide

TISS_NAMESPACE = "http://www.ans.gov.br/padroes/tiss/schemas"
DEFAULT_VERSION = "4.01.00"
NSMAP = {"ans": TISS_NAMESPACE}


def _text(field) -> str | None:
    return field.value if field and field.value else None


def _iso_date(value: str | None) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 8:
        return None
    return f"{digits[4:]}-{digits[2:4]}-{digits[:2]}"


def _element(parent, tag: str, value: str | None):
    if value is None:
        return None
    child = etree.SubElement(parent, f"{{{TISS_NAMESPACE}}}{tag}")
    child.text = value
    return child


def _header(root, guide: SpSadtGuide, sequence: str, version: str) -> None:
    header = etree.SubElement(root, f"{{{TISS_NAMESPACE}}}cabecalho")
    transaction = etree.SubElement(header, f"{{{TISS_NAMESPACE}}}identificacaoTransacao")
    now = datetime.now()

    _element(transaction, "tipoTransacao", "SOLICITACAO_INTERNACAO")
    _element(transaction, "sequencialTransacao", sequence)
    _element(transaction, "dataRegistroTransacao", now.strftime("%Y-%m-%d"))
    _element(transaction, "horaRegistroTransacao", now.strftime("%H:%M:%S"))

    origin = etree.SubElement(header, f"{{{TISS_NAMESPACE}}}origem")
    provider = etree.SubElement(origin, f"{{{TISS_NAMESPACE}}}identificacaoPrestador")
    _element(provider, "codigoPrestadorNaOperadora", _text(guide.requester_operator_code))

    destination = etree.SubElement(header, f"{{{TISS_NAMESPACE}}}destino")
    _element(destination, "registroANS", _text(guide.ans_registration))

    _element(header, "versaoPadrao", version)


def _beneficiary(parent, guide: SpSadtGuide) -> None:
    beneficiary = etree.SubElement(parent, f"{{{TISS_NAMESPACE}}}dadosBeneficiario")
    _element(beneficiary, "numeroCarteira", _text(guide.member_card_number))
    _element(beneficiary, "validadeCarteira", _iso_date(_text(guide.card_expiry_date)))
    _element(beneficiary, "nomeBeneficiario", _text(guide.member_name))
    _element(beneficiary, "numeroCNS", _text(guide.national_health_card))
    _element(beneficiary, "atendimentoRN", _text(guide.newborn_care))


def _requester(parent, guide: SpSadtGuide) -> None:
    requester = etree.SubElement(parent, f"{{{TISS_NAMESPACE}}}dadosSolicitante")
    contracted = etree.SubElement(requester, f"{{{TISS_NAMESPACE}}}contratadoSolicitante")
    _element(contracted, "codigoPrestadorNaOperadora", _text(guide.requester_operator_code))
    _element(contracted, "nomeContratado", _text(guide.requester_provider_name))

    professional = etree.SubElement(requester, f"{{{TISS_NAMESPACE}}}profissionalSolicitante")
    _element(professional, "nomeProfissional", _text(guide.requesting_professional_name))
    _element(professional, "conselhoProfissional", _text(guide.professional_council))
    _element(professional, "numeroConselhoProfissional", _text(guide.council_number))
    _element(professional, "UF", _text(guide.council_state))
    _element(professional, "CBOS", _text(guide.cbo_code))


def _admission(parent, guide: SpSadtGuide) -> None:
    admission = etree.SubElement(parent, f"{{{TISS_NAMESPACE}}}dadosInternacao")
    _element(admission, "caraterAtendimento", _text(guide.care_type))
    _element(admission, "tipoInternacao", _text(guide.admission_type))
    _element(admission, "regimeInternacao", _text(guide.admission_regime))
    _element(admission, "qtdeDiariasSolicitadas", _text(guide.requested_daily_rates))
    _element(admission, "indicacaoClinica", _text(guide.clinical_indication))
    _element(admission, "dataSugeridaInternacao", _iso_date(_text(guide.suggested_admission_date)))

    for attribute in ("main_icd10", "icd10_2", "icd10_3", "icd10_4"):
        _element(admission, "CID10", _text(getattr(guide, attribute)))


def _procedures(parent, guide: SpSadtGuide) -> None:
    if not guide.procedures:
        return
    container = etree.SubElement(parent, f"{{{TISS_NAMESPACE}}}procedimentosSolicitados")
    for procedure in guide.procedures:
        if not _text(procedure.code):
            continue
        item = etree.SubElement(container, f"{{{TISS_NAMESPACE}}}procedimentoSolicitado")
        identification = etree.SubElement(item, f"{{{TISS_NAMESPACE}}}procedimento")
        _element(identification, "codigoTabela", _text(procedure.table))
        _element(identification, "codigoProcedimento", _text(procedure.code))
        _element(identification, "descricaoProcedimento", _text(procedure.description))
        _element(item, "quantidadeSolicitada", _text(procedure.requested_quantity))


def _epilogue(root) -> None:
    """TISS closes the message with an MD5 of every element value, tags excluded."""
    values = "".join(
        element.text.strip()
        for element in root.iter()
        if element.text and element.text.strip()
    )
    epilogue = etree.SubElement(root, f"{{{TISS_NAMESPACE}}}epilogo")
    _element(epilogue, "hash", hashlib.md5(values.encode("utf-8")).hexdigest())


def build_message(guide: SpSadtGuide, sequence: str = "1", version: str = DEFAULT_VERSION) -> etree._Element:
    root = etree.Element(f"{{{TISS_NAMESPACE}}}mensagemTISS", nsmap=NSMAP)
    _header(root, guide, sequence, version)

    body = etree.SubElement(root, f"{{{TISS_NAMESPACE}}}prestadorParaOperadora")
    request = etree.SubElement(body, f"{{{TISS_NAMESPACE}}}solicitacaoInternacao")
    _element(request, "numeroGuiaPrestador", _text(guide.provider_guide_number))
    _element(request, "dataSolicitacao", _iso_date(_text(guide.request_date)))

    _beneficiary(request, guide)
    _requester(request, guide)
    _admission(request, guide)
    _procedures(request, guide)
    _epilogue(root)
    return root


def to_xml(guide: SpSadtGuide, sequence: str = "1", version: str = DEFAULT_VERSION) -> str:
    message = build_message(guide, sequence, version)
    return etree.tostring(message, pretty_print=True, xml_declaration=True, encoding="UTF-8").decode()
