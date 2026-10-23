"""Normalises whatever arrives — PDF or photo — into a single document path.

Images are wrapped into an A4 page because that is what a guide is: the page
size is what makes the effective dpi meaningful, and it keeps one code path
for triage, cropping and reading.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pymupdf

A4_WIDTH_PT = 595
A4_HEIGHT_PT = 842

PDF_SUFFIXES = {".pdf"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
SUPPORTED_SUFFIXES = PDF_SUFFIXES | IMAGE_SUFFIXES


class UnsupportedFile(ValueError):
    pass


def image_to_pdf(data: bytes, destination: Path) -> Path:
    document = pymupdf.open()
    page = document.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
    page.insert_image(pymupdf.Rect(0, 0, A4_WIDTH_PT, A4_HEIGHT_PT), stream=data)
    document.save(destination)
    document.close()
    return destination


def store_upload(data: bytes, file_name: str, folder: Path) -> Path:
    """Writes the upload to `folder` and returns the PDF the pipeline should read."""
    suffix = Path(file_name).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedFile(
            f"{suffix or 'arquivo sem extensão'} não suportado; envie PDF ou imagem"
        )

    folder.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex

    if suffix in PDF_SUFFIXES:
        destination = folder / f"{stem}.pdf"
        destination.write_bytes(data)
        return destination

    (folder / f"{stem}{suffix}").write_bytes(data)
    return image_to_pdf(data, folder / f"{stem}.pdf")
