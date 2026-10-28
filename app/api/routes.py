from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, Response, UploadFile

from app.api.schemas import ExtractionResponse, ExtractionSummary, FieldCorrection, ReviewDecision
from app.api.store import AuditEntry, ExtractionStore
from app.config import get_settings
from app.extraction.pipeline import extract_page
from app.extraction.rendering import render_page_to_png
from app.extraction.triage import triage_pdf
from app.ingestion.input_file import SUPPORTED_SUFFIXES, UnsupportedFile, store_upload
from app.learning.database import session
from app.learning.feedback import (
    common_mistakes,
    field_accuracy,
    learn_professional,
    record_approval,
    record_confirmation,
    record_correction,
)
from app.learning.professionals import count as count_professionals
from app.learning.professionals import duplicate_names, rank_by_name
from app.output.consolidation import build_payload
from app.output.tiss_xml import to_xml
from app.schemas.guide import ExtractedField, FieldSource

router = APIRouter(prefix="/api")
# O healthcheck do container não tem credencial: fica fora da proteção, e não
# devolve nada além do estado do serviço.
public_router = APIRouter(prefix="/api")
store = ExtractionStore()

PREVIEW_DPI = 110
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@public_router.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ok",
        "llm_enabled": settings.llm_available,
        "render_dpi": settings.render_dpi,
        "accepted_files": sorted(SUPPORTED_SUFFIXES),
    }


@router.post("/extractions", response_model=ExtractionResponse)
async def create_extraction(file: UploadFile = File(...), page: int = 1) -> ExtractionResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="arquivo vazio")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="arquivo acima de 25 MB")

    try:
        pdf_path = store_upload(data, file.filename or "upload", store.folder)
    except UnsupportedFile as error:
        raise HTTPException(status_code=415, detail=str(error)) from error

    pages = triage_pdf(pdf_path)
    if page < 1 or page > len(pages):
        raise HTTPException(status_code=400, detail=f"página {page} fora do documento")

    settings = get_settings()
    result = extract_page(pdf_path, page, pages[page - 1], settings)
    extraction = store.add(
        file.filename or pdf_path.name, pdf_path, len(pages), build_payload(result), result.guide
    )

    return ExtractionResponse(
        id=extraction.identifier,
        original_name=extraction.original_name,
        created_at=extraction.created_at,
        page_count=extraction.page_count,
        payload=extraction.payload,
        audit=[asdict(entry) for entry in extraction.audit],
    )


@router.get("/extractions", response_model=list[ExtractionSummary])
def list_extractions() -> list[ExtractionSummary]:
    return [
        ExtractionSummary(
            id=item.identifier,
            original_name=item.original_name,
            created_at=item.created_at,
            page_count=item.page_count,
            strategy=item.payload.get("strategy", ""),
            fields_read=item.payload.get("summary", {}).get("fields_read", 0),
            fields_to_review=item.payload.get("summary", {}).get("fields_to_review", 0),
        )
        for item in store.list()
    ]


def _require(identifier: str):
    extraction = store.get(identifier)
    if extraction is None:
        raise HTTPException(status_code=404, detail="extração não encontrada")
    return extraction


@router.get("/extractions/{identifier}", response_model=ExtractionResponse)
def read_extraction(identifier: str) -> ExtractionResponse:
    extraction = _require(identifier)
    return ExtractionResponse(
        id=extraction.identifier,
        original_name=extraction.original_name,
        created_at=extraction.created_at,
        page_count=extraction.page_count,
        payload=extraction.payload,
        audit=[asdict(entry) for entry in extraction.audit],
    )


@router.get("/extractions/{identifier}/page.png")
def read_page_image(identifier: str, page: int = 1) -> Response:
    extraction = _require(identifier)
    if page < 1 or page > extraction.page_count:
        raise HTTPException(status_code=400, detail="página fora do documento")
    png = render_page_to_png(extraction.pdf_path, page, PREVIEW_DPI)
    return Response(content=png, media_type="image/png")


@router.patch("/extractions/{identifier}/fields/{field_name}", response_model=ExtractionResponse)
def correct_field(identifier: str, field_name: str, correction: FieldCorrection) -> ExtractionResponse:
    extraction = _require(identifier)
    fields = extraction.payload.get("fields", [])

    target = next((item for item in fields if item["name"] == field_name), None)
    if target is None:
        raise HTTPException(status_code=404, detail="campo não encontrado")

    previous = target.get("value")
    unchanged = (correction.value or "") == (previous or "")

    with session() as database:
        if unchanged:
            record_confirmation(
                database, identifier, field_name, previous,
                target.get("source"), target.get("confidence"),
            )
        else:
            record_correction(
                database, identifier, field_name, previous, correction.value,
                target.get("source"), target.get("confidence"),
            )
    if extraction.guide is not None and field_name in type(extraction.guide).model_fields:
        setattr(
            extraction.guide, field_name,
            ExtractedField(value=correction.value, source=FieldSource.HUMAN, confidence=1.0, is_valid=True),
        )
    target.update(
        value=correction.value,
        source=target.get("source") if unchanged else "human",
        confidence=1.0,
        validated=True,
        needs_review=False,
        note="conferido na revisão" if unchanged else "corrigido na revisão",
    )

    filled = [item for item in fields if item.get("value")]
    extraction.payload["summary"].update(
        fields_read=len(filled),
        fields_to_review=sum(1 for item in filled if item["needs_review"]),
    )
    store.record(
        extraction,
        AuditEntry(
            at=_now(),
            action="field_confirmed" if unchanged else "field_corrected",
            field_name=field_name,
            previous=previous,
            current=correction.value,
            author=correction.author,
        ),
    )
    return read_extraction(identifier)


@router.post("/extractions/{identifier}/decision", response_model=ExtractionResponse)
def register_decision(identifier: str, decision: ReviewDecision) -> ExtractionResponse:
    extraction = _require(identifier)
    extraction.payload["decision"] = {"status": decision.decision, "note": decision.note, "at": _now()}

    if decision.decision == "aprovado":
        with session() as database:
            fields = extraction.payload.get("fields", [])
            confirmed = record_approval(database, identifier, fields)
            learned = learn_professional(database, fields)
        extraction.payload["decision"]["confirmed_fields"] = confirmed
        if learned:
            extraction.payload["decision"]["registered_professional"] = learned
    store.record(
        extraction,
        AuditEntry(at=_now(), action=f"review_{decision.decision}", current=decision.note, author=decision.author),
    )
    return read_extraction(identifier)


@router.get("/extractions/{identifier}/tiss.xml")
def read_tiss_xml(identifier: str) -> Response:
    extraction = _require(identifier)
    if extraction.guide is None:
        raise HTTPException(status_code=409, detail="nenhum dado extraído para gerar o XML")
    return Response(
        content=to_xml(extraction.guide, sequence=extraction.identifier),
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="tiss-{extraction.identifier}.xml"'},
    )


@router.get("/learning/stats")
def learning_stats() -> dict[str, object]:
    """What the tool has learned so far, and where it still gets things wrong."""
    with session() as database:
        accuracy = field_accuracy(database)
        return {
            "professionals": count_professionals(database),
            "fields": [
                {
                    "field": item.field_name,
                    "confirmed": item.confirmed,
                    "corrected": item.corrected,
                    "hit_rate": round(item.hit_rate, 3),
                }
                for item in accuracy
            ],
            "reviewed_fields": sum(item.total for item in accuracy),
            "common_mistakes": common_mistakes(database),
        }


@router.get("/learning/professionals")
def search_professionals(q: str) -> list[dict[str, object]]:
    """Shortlist for the review screen: who in the registry resembles this name."""
    with session() as database:
        return [
            {
                "name": professional.full_name,
                "council": professional.council,
                "council_number": professional.council_number,
                "council_state": professional.council_state,
                "specialty": professional.specialty,
                "operator_code": professional.operator_code,
                "score": round(score, 2),
            }
            for professional, score in rank_by_name(database, q)
        ]


@router.get("/learning/registry-issues")
def registry_issues() -> dict[str, object]:
    """Homonyms in the registry — the reason a name is never enough to identify someone."""
    with session() as database:
        duplicates = duplicate_names(database)
    return {
        "duplicate_names": [{"name": name, "council_numbers": numbers} for name, numbers in duplicates]
    }
