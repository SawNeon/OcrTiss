from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from app.config import Settings, get_settings
from app.extraction.llm_vision import LlmExtractionError, LlmVisionExtractor
from app.extraction.rendering import render_page_to_png
from app.extraction.stamp import parse_stamp
from app.extraction.template_reader import (
    CharacterModelMissing,
    LayoutNotRecognised,
    coded_field_names,
    merge_into_guide,
    read_coded_fields,
)
from app.extraction.text_layer import extract_from_pdf
from app.extraction.triage import PageKind, PageTriage, triage_pdf
from app.learning.database import session
from app.learning.professionals import rank_by_name, resolve
from app.schemas.guide import (
    ExtractedField,
    ExtractionResult,
    ExtractionStrategy,
    FieldSource,
    SpSadtGuide,
)

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("member_card_number", "request_date")
LOW_CONFIDENCE_THRESHOLD = 0.9
STAMP_CONFIDENCE = 0.7
CONFIRMED_BY_STAMP_CONFIDENCE = 0.97
DIVERGENT_CONFIDENCE = 0.4
CROSS_CHECKED_FIELDS = ("council_number", "council_state", "professional_council")
REGISTRY_CONFIDENCE = 0.99


def is_complete(guide: SpSadtGuide) -> bool:
    filled = guide.filled_fields()
    has_required = all(name in filled for name in REQUIRED_FIELDS)
    has_procedure = any(item.code and item.code.value for item in guide.procedures)
    return has_required and has_procedure


def needs_review(guide: SpSadtGuide) -> bool:
    return any(
        field.confidence < LOW_CONFIDENCE_THRESHOLD for field in guide.filled_fields().values()
    )


def merge_free_text(guide: SpSadtGuide, source: SpSadtGuide) -> SpSadtGuide:
    """Fills only what the local reader does not own and has not already read."""
    owned = coded_field_names()
    for name, value in source:
        if name in owned or value is None or isinstance(value, list):
            continue
        if getattr(guide, name, None) is None:
            setattr(guide, name, value)

    if not guide.procedures:
        guide.procedures = source.procedures
    else:
        for index, procedure in enumerate(source.procedures):
            if index < len(guide.procedures) and guide.procedures[index].description is None:
                guide.procedures[index].description = procedure.description
    return guide


def _diagnostics(triage: PageTriage) -> dict[str, object]:
    return {
        "page_kind": triage.kind.value,
        "effective_dpi": triage.effective_dpi,
        "from_self_service": triage.from_self_service,
        "is_sliced": triage.is_sliced,
        "is_landscape": triage.is_landscape,
    }


def extract_page(
    pdf_path: str | Path,
    page_number: int,
    triage: PageTriage,
    settings: Settings | None = None,
) -> ExtractionResult:
    settings = settings or get_settings()
    pdf_path = Path(pdf_path)
    result = ExtractionResult(
        file_name=pdf_path.name,
        page_number=page_number,
        strategy=ExtractionStrategy.MANUAL,
        diagnostics=_diagnostics(triage),
        warnings=list(triage.warnings),
        needs_human_review=True,
    )

    if triage.kind is PageKind.TEXT_LAYER:
        guide = extract_from_pdf(pdf_path, page_number)
        if is_complete(guide):
            result.strategy = ExtractionStrategy.TEXT_LAYER
            result.guide = guide
            result.needs_human_review = needs_review(guide)
            return result
        result.guide = guide
        result.warnings.append("camada de texto não trouxe os campos obrigatórios")

    guide = result.guide or SpSadtGuide()

    if settings.template_reader_enabled:
        try:
            reading = read_coded_fields(pdf_path, page_number, settings)
            guide = merge_into_guide(guide, reading)
            result.strategy = ExtractionStrategy.TEMPLATE
            result.diagnostics["document_found"] = reading.document_found
            result.diagnostics["aligned"] = reading.aligned
            result.diagnostics["template_score"] = round(reading.score, 2)
        except LayoutNotRecognised as error:
            result.warnings.append(f"layout não reconhecido: {error}")
        except CharacterModelMissing as error:
            result.warnings.append(f"leitor local indisponível: {error}")
        except Exception as error:  # a página pode não ser uma guia conhecida
            result.warnings.append(f"leitura por gabarito falhou: {type(error).__name__}: {error}")

    if settings.llm_available:
        try:
            page_png = render_page_to_png(pdf_path, page_number, settings.render_dpi)
            guide = merge_free_text(guide, LlmVisionExtractor(settings).extract(page_png))
            result.strategy = (
                ExtractionStrategy.HYBRID
                if result.strategy is ExtractionStrategy.TEMPLATE
                else ExtractionStrategy.LLM
            )
            from_stamp = apply_stamp(guide)
            if from_stamp:
                result.diagnostics["stamp"] = from_stamp
                divergent = [name for name, status in from_stamp.items() if status == "divergente"]
                if divergent:
                    result.warnings.append(
                        "carimbo diverge do formulário em: " + ", ".join(divergent)
                    )

            registry = apply_registry(guide)
            if registry:
                result.diagnostics["registry"] = registry
                if "suggestion" in registry:
                    result.warnings.append(
                        f"cadastro sugere {registry['suggestion']} ({registry['reason']})"
                    )
        except LlmExtractionError as error:
            logger.warning("leitura por LLM falhou: %s", error)
            result.warnings.append(
                "leitura de texto por modelo de visão indisponível; campos de texto livre ficaram em branco"
            )

    if guide.filled_fields() or guide.procedures:
        result.guide = guide
        result.needs_human_review = True
    else:
        result.warnings.append("nenhum campo extraído: página vai para digitação manual")

    return result


def extract_document(
    pdf_path: str | Path, settings: Settings | None = None
) -> list[ExtractionResult]:
    settings = settings or get_settings()
    return [
        extract_page(pdf_path, triage.page_number, triage, settings)
        for triage in triage_pdf(pdf_path)
    ]


def _cross_check(field: ExtractedField, stamp_value: str) -> None:
    """Two independent readings of the same number: agreement is evidence, divergence is a flag."""
    if field.value == stamp_value:
        field.confidence = max(field.confidence, CONFIRMED_BY_STAMP_CONFIDENCE)
        field.is_valid = True
        field.note = "confirmado pelo carimbo"
    else:
        field.confidence = min(field.confidence, DIVERGENT_CONFIDENCE)
        field.note = f"divergente do carimbo, que diz {stamp_value}"


def apply_stamp(guide: SpSadtGuide) -> dict[str, str]:
    """Uses the stamp to fill the council fields, or to corroborate what the boxes said.

    The stamp is printed, so it reads better than the handwritten boxes — but it
    is still a reading, not a fact: a value that only the stamp supports always
    goes to review.
    """
    stamp = parse_stamp(guide.professional_stamp.value if guide.professional_stamp else None)
    if stamp.rejected_number:
        logger.warning("registro do carimbo descartado por ser implausível: %s", stamp.rejected_number)
    if not stamp.has_registration and not stamp.professional_name:
        return {}

    outcome: dict[str, str] = {}
    # A rejected number taints the council and the state parsed from the same
    # string; the name is read independently, so it survives.
    candidates = (
        {
            "council_number": stamp.council_number,
            "council_state": stamp.council_state,
            "professional_council": stamp.council,
            "requesting_professional_name": stamp.professional_name,
        }
        if stamp.has_registration
        else {"requesting_professional_name": stamp.professional_name}
    )

    for name, value in candidates.items():
        if not value:
            continue
        current = getattr(guide, name, None)

        if current is None or not current.value:
            setattr(
                guide, name,
                ExtractedField(
                    value=value,
                    source=FieldSource.LLM,
                    confidence=STAMP_CONFIDENCE,
                    note="lido do carimbo do profissional",
                ),
            )
            outcome[name] = "preenchido"
        elif name in CROSS_CHECKED_FIELDS:
            _cross_check(current, value)
            outcome[name] = "confirmado" if current.value == value else "divergente"

    return outcome


def apply_registry(guide: SpSadtGuide) -> dict[str, object]:
    """Checks what was read against the registry of professionals.

    Only an exact registration, or a name whose registration is off by a single
    digit, is applied on its own: measured on real names, similarity alone
    cannot tell two professionals apart. Anything weaker is a suggestion.
    """
    number = guide.council_number.value if guide.council_number else None
    state = guide.council_state.value if guide.council_state else None
    name = guide.requesting_professional_name.value if guide.requesting_professional_name else None

    if not number and not name:
        return {}

    try:
        with session() as database:
            match = resolve(database, number, state, name)
            shortlist = (
                [
                    {"label": item.label, "specialty": item.specialty, "score": round(score, 2)}
                    for item, score in rank_by_name(database, name)
                ]
                if name and (match is None or not match.apply_automatically)
                else []
            )
    except sqlite3.Error as error:
        logger.warning("cadastro de profissionais indisponível: %s", error)
        return {}

    if match is None:
        return {"suggestions": shortlist} if shortlist else {}

    if not match.apply_automatically:
        return {"suggestions": shortlist, "reason": match.reason}

    professional = match.professional
    guide.requesting_professional_name = ExtractedField(
        value=professional.full_name, source=FieldSource.REGISTRY,
        confidence=REGISTRY_CONFIDENCE, is_valid=True, note=match.reason,
    )
    guide.council_number = ExtractedField(
        value=professional.council_number, source=FieldSource.REGISTRY,
        confidence=REGISTRY_CONFIDENCE, is_valid=True, note=match.reason,
    )
    if professional.council_state:
        guide.council_state = ExtractedField(
            value=professional.council_state, source=FieldSource.REGISTRY,
            confidence=REGISTRY_CONFIDENCE, is_valid=True,
        )
    if professional.specialty:
        guide.professional_specialty = ExtractedField(
            value=professional.specialty, source=FieldSource.REGISTRY, confidence=REGISTRY_CONFIDENCE,
        )

    return {
        "matched": professional.label,
        "reason": match.reason,
        "corrected_number": match.corrects_number,
    }
