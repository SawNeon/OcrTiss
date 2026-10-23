from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pypdf import PdfReader

BROWSER_PRINT_HEADER = re.compile(r"^\d{2}/\d{2}/\d{4},\s*\d{2}:\d{2}\s", re.MULTILINE)
SELF_SERVICE_UPLOAD = re.compile(r"\[AUTOATENDIMENTO_BEN\]_(\d+)_", re.IGNORECASE)
PORTAL_URL = re.compile(r"https?://\S*sup\.\S+", re.IGNORECASE)

MIN_DPI_FOR_OCR = 200
MIN_CHARS_FOR_TEXT_LAYER = 300
POINTS_PER_INCH = 72


class PageKind(str, Enum):
    TEXT_LAYER = "text_layer"
    IMAGE = "image"


@dataclass
class PageTriage:
    file_name: str
    page_number: int
    kind: PageKind
    usable_chars: int
    width_pt: float
    height_pt: float
    is_landscape: bool
    effective_dpi: int | None
    image_count: int
    is_sliced: bool
    from_self_service: bool
    warnings: list[str] = field(default_factory=list)


def strip_print_artifacts(text: str) -> str:
    text = PORTAL_URL.sub("", text)
    lines = [
        line
        for line in text.splitlines()
        if not BROWSER_PRINT_HEADER.match(line) and not line.strip().endswith("1/1")
    ]
    return "\n".join(lines).strip()


def _image_sizes(page) -> list[tuple[int, int]]:
    resources = page.get("/Resources", {})
    try:
        xobjects = resources.get("/XObject", {}).get_object()
    except AttributeError:
        return []

    sizes = []
    for name in xobjects:
        xobject = xobjects[name].get_object()
        if xobject.get("/Subtype") == "/Image":
            sizes.append((int(xobject.get("/Width", 0)), int(xobject.get("/Height", 0))))
    return sizes


def _page_text(page) -> str:
    try:
        return page.extract_text() or ""
    except Exception:
        return ""


def _build_warnings(kind: PageKind, dpi: int | None, is_sliced: bool, is_landscape: bool) -> list[str]:
    warnings: list[str] = []
    if kind is PageKind.IMAGE:
        if dpi is None:
            warnings.append("página sem camada de texto e sem imagem legível")
        elif dpi < MIN_DPI_FOR_OCR:
            warnings.append(f"resolução baixa para leitura ({dpi} dpi, mínimo {MIN_DPI_FOR_OCR})")
        if is_sliced:
            warnings.append("imagem fatiada no PDF: a página é renderizada inteira")
    if is_landscape:
        warnings.append("página em paisagem: rotação é conferida no alinhamento")
    return warnings


def triage_pdf(pdf_path: str | Path) -> list[PageTriage]:
    pdf_path = Path(pdf_path)
    reader = PdfReader(pdf_path)
    pages: list[PageTriage] = []

    for page_number, page in enumerate(reader.pages, start=1):
        raw_text = _page_text(page)
        text = strip_print_artifacts(raw_text)

        image_sizes = _image_sizes(page)
        width_pt = float(page.mediabox.width)
        height_pt = float(page.mediabox.height)

        effective_dpi = None
        is_sliced = False
        if image_sizes:
            largest = max(image_sizes, key=lambda size: size[0] * size[1])
            if width_pt:
                effective_dpi = round(largest[0] / (width_pt / POINTS_PER_INCH))
            is_sliced = len(image_sizes) > 3 and largest[1] < largest[0]

        kind = (
            PageKind.TEXT_LAYER
            if len(text) >= MIN_CHARS_FOR_TEXT_LAYER
            else PageKind.IMAGE
        )
        is_landscape = width_pt > height_pt

        pages.append(
            PageTriage(
                file_name=pdf_path.name,
                page_number=page_number,
                kind=kind,
                usable_chars=len(text),
                width_pt=width_pt,
                height_pt=height_pt,
                is_landscape=is_landscape,
                effective_dpi=effective_dpi,
                image_count=len(image_sizes),
                is_sliced=is_sliced,
                from_self_service=bool(SELF_SERVICE_UPLOAD.search(raw_text)),
                warnings=_build_warnings(kind, effective_dpi, is_sliced, is_landscape),
            )
        )

    return pages
