from __future__ import annotations

import pytest

from app.extraction.triage import PageKind, triage_pdf
from app.ingestion.input_file import UnsupportedFile, store_upload


def test_pdf_is_stored_as_is(guide_pdf, tmp_path):
    stored = store_upload(guide_pdf.read_bytes(), "guia.pdf", tmp_path)
    assert stored.suffix == ".pdf"
    assert stored.read_bytes() == guide_pdf.read_bytes()


def test_image_becomes_a_readable_pdf(guide_png, tmp_path):
    stored = store_upload(guide_png.read_bytes(), "guia.png", tmp_path)
    pages = triage_pdf(stored)

    assert stored.suffix == ".pdf"
    assert len(pages) == 1
    assert pages[0].kind is PageKind.IMAGE
    assert pages[0].effective_dpi and pages[0].effective_dpi > 200


def test_unknown_extension_is_refused(tmp_path):
    with pytest.raises(UnsupportedFile):
        store_upload(b"qualquer coisa", "guia.docx", tmp_path)
