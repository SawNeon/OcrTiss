from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from app.config import Settings, get_settings
from app.extraction.rendering import render_page_to_png
from app.preprocessing.alignment import align_to_template
from app.preprocessing.cells import extract_cells
from app.preprocessing.document import deskew, extract_document
from app.recognition.character_classifier import DEFAULT_MODEL_PATH, CharacterClassifier
from app.recognition.decoder import decode_field
from app.schemas.guide import ExtractedField, FieldSource, Procedure, SpSadtGuide
from app.synthetic.guide_generator import blank_form_image
from app.synthetic.layout import (
    FIELDS,
    PROCEDURE_COLUMNS,
    SCALE,
    SHEET_HEIGHT,
    SHEET_WIDTH,
    comb_cells,
    procedure_comb_cells,
)

PROCEDURE_ROWS_READ = 3
MIN_TEMPLATE_SCORE = 0.45
# Abaixo disso a leitura é ruído de tinta, não um caractere: melhor campo vazio.
MIN_EMIT_CONFIDENCE = 0.05
# A single character floating in a field of four or more boxes is a stray mark,
# not a value: every field this wide is filled with a code, a date or a number.
MIN_CHARACTERS_IN_WIDE_FIELD = 2
WIDE_FIELD_CELLS = 4


def coded_field_names() -> set[str]:
    """Fields the local reader owns: whatever the whole-page pass said about them is dropped."""
    return {form_field.name for form_field in FIELDS if form_field.cells}


class CharacterModelMissing(RuntimeError):
    pass


class LayoutNotRecognised(RuntimeError):
    """The page does not line up with any known form, so reading boxes would invent data."""


@dataclass
class TemplateReading:
    values: dict[str, str] = dataclass_field(default_factory=dict)
    confidences: dict[str, float] = dataclass_field(default_factory=dict)
    validated: dict[str, bool | None] = dataclass_field(default_factory=dict)
    document_found: bool = False
    area_ratio: float = 0.0
    aligned: bool = False
    matches: int = 0
    score: float = 0.0


@lru_cache(maxsize=1)
def _classifier(path: str = str(DEFAULT_MODEL_PATH)) -> CharacterClassifier:
    model_path = Path(path)
    if not model_path.exists():
        raise CharacterModelMissing(
            f"no character model at {model_path}; run scripts/train_character_model.py"
        )
    return CharacterClassifier.load(model_path)


@lru_cache(maxsize=1)
def _template() -> np.ndarray:
    return cv2.cvtColor(np.array(blank_form_image()), cv2.COLOR_RGB2BGR)


def _page_to_array(pdf_path: str | Path, page_number: int, dpi: int) -> np.ndarray:
    png = render_page_to_png(pdf_path, page_number, dpi)
    return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)


def _coded_field_cells(page: np.ndarray, scale: float) -> dict[str, list[np.ndarray]]:
    cells: dict[str, list[np.ndarray]] = {}

    for form_field in FIELDS:
        rects = comb_cells(form_field)
        if rects:
            cells[form_field.name] = extract_cells(page, rects, scale)

    for row in range(PROCEDURE_ROWS_READ):
        for column, (_, _, _, _, cell_count) in PROCEDURE_COLUMNS.items():
            if not cell_count:
                continue
            cells[f"procedure{row + 1}_{column}"] = extract_cells(
                page, procedure_comb_cells(row, column), scale
            )

    return cells


@dataclass
class AlignedPage:
    cells: dict[str, list[np.ndarray]]
    document_found: bool
    area_ratio: float
    aligned: bool
    matches: int
    score: float


def aligned_cells(pdf_path: str | Path, page_number: int = 1, dpi: int = 300) -> AlignedPage:
    """The read path: render, crop the sheet, square it against the blank form, cut the boxes."""
    page_image = _page_to_array(pdf_path, page_number, dpi)
    crop = extract_document(page_image, aspect_ratio=SHEET_HEIGHT / SHEET_WIDTH)
    alignment = align_to_template(deskew(crop.image), _template())

    document = alignment.image
    scale = document.shape[1] / (SHEET_WIDTH * SCALE)

    return AlignedPage(
        cells=_coded_field_cells(document, scale),
        document_found=crop.found,
        area_ratio=crop.area_ratio,
        aligned=alignment.aligned,
        matches=alignment.matches,
        score=alignment.score,
    )


def _is_stray_mark(value: str, cell_count: int) -> bool:
    return bool(value) and cell_count >= WIDE_FIELD_CELLS and len(value) < MIN_CHARACTERS_IN_WIDE_FIELD


def read_coded_fields(
    pdf_path: str | Path, page_number: int, settings: Settings | None = None
) -> TemplateReading:
    """Reads every character box of the aligned page with the local classifier."""
    settings = settings or get_settings()
    classifier = _classifier()

    page = aligned_cells(pdf_path, page_number, settings.render_dpi)
    if page.score < MIN_TEMPLATE_SCORE:
        raise LayoutNotRecognised(
            f"a página não corresponde ao gabarito conhecido (semelhança {page.score:.2f})"
        )

    reading = TemplateReading(
        document_found=page.document_found,
        area_ratio=page.area_ratio,
        aligned=page.aligned,
        matches=page.matches,
        score=page.score,
    )

    for field_name, cells in page.cells.items():
        if not cells:
            continue
        decoded = decode_field(classifier, field_name, cells)
        if _is_stray_mark(decoded.value, len(cells)):
            continue
        if decoded.value and decoded.confidence >= MIN_EMIT_CONFIDENCE:
            reading.values[field_name] = decoded.value
            reading.confidences[field_name] = decoded.confidence
            reading.validated[field_name] = decoded.validated

    return reading


def merge_into_guide(guide: SpSadtGuide, reading: TemplateReading) -> SpSadtGuide:
    """Coded fields read box by box replace whatever the whole-page pass produced."""
    procedures: dict[int, dict[str, str]] = {}

    for name in coded_field_names():
        if name not in reading.values and name in SpSadtGuide.model_fields:
            setattr(guide, name, None)

    for name, value in reading.values.items():
        confidence = reading.confidences.get(name, 0.5)
        if name.startswith("procedure"):
            index, _, attribute = name.partition("_")
            procedures.setdefault(int(index.removeprefix("procedure")), {})[attribute] = value
            continue
        if name in SpSadtGuide.model_fields:
            setattr(
                guide, name,
                ExtractedField(
                    value=value,
                    source=FieldSource.OCR,
                    confidence=confidence,
                    is_valid=reading.validated.get(name),
                ),
            )

    for index, attributes in sorted(procedures.items()):
        while len(guide.procedures) < index:
            guide.procedures.append(Procedure())
        procedure = guide.procedures[index - 1]
        for attribute, value in attributes.items():
            if hasattr(procedure, attribute):
                setattr(
                    procedure, attribute,
                    ExtractedField(
                        value=value,
                        source=FieldSource.OCR,
                        confidence=reading.confidences.get(f"procedure{index}_{attribute}", 0.5),
                    ),
                )

    return guide
