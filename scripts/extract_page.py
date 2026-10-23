"""Extracts a single page and prints the fields, their source and confidence.

Usage:
    python scripts/extract_page.py "DOC_TESTE/GUIA.pdf" 1 [--show-values]

Values are masked by default so results can be inspected without exposing member data.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.extraction.pipeline import extract_page
from app.extraction.triage import triage_pdf


def mask(text: str) -> str:
    return re.sub(r"\d", "#", text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument("page_number", type=int, nargs="?", default=1)
    parser.add_argument("--show-values", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    triage = triage_pdf(args.pdf_path)[args.page_number - 1]

    print(f"{args.pdf_path.name} page {args.page_number}")
    print(f"  kind={triage.kind.value} dpi={triage.effective_dpi} landscape={triage.is_landscape}")
    print(f"  llm fallback: {'enabled' if settings.llm_available else 'disabled'}")

    started = time.perf_counter()
    result = extract_page(args.pdf_path, args.page_number, triage, settings)
    elapsed = time.perf_counter() - started

    print(f"  strategy={result.strategy.value} elapsed={elapsed:.1f}s review={result.needs_human_review}")
    for warning in result.warnings:
        print(f"  warning: {warning}")

    if not result.guide:
        return

    print(f"\n  {'field':<32} {'source':<11} {'conf':<5} value")
    for name, field in result.guide.filled_fields().items():
        value = field.value or ""
        print(
            f"  {name:<32} {field.source.value:<11} {field.confidence:<5} "
            f"{value if args.show_values else mask(value)}"
        )
    for index, procedure in enumerate(result.guide.procedures, start=1):
        parts = [
            procedure.table,
            procedure.code,
            procedure.description,
            procedure.requested_quantity,
            procedure.authorized_quantity,
        ]
        line = " | ".join((part.value or "") if part else "" for part in parts)
        print(f"  procedure {index}: {line if args.show_values else mask(line)}")


if __name__ == "__main__":
    main()
