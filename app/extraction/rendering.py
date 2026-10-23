from __future__ import annotations

from pathlib import Path

import pymupdf


def render_page_to_png(pdf_path: str | Path, page_number: int, dpi: int = 300) -> bytes:
    with pymupdf.open(Path(pdf_path)) as document:
        page = document[page_number - 1]
        pixmap = page.get_pixmap(dpi=dpi)
        return pixmap.tobytes("png")
