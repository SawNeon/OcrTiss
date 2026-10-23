"""Triages a folder of guides and reports which extraction strategy each page takes.

Usage:
    python scripts/analyze_batch.py DOC_TESTE [--show-values] [--llm]

The LLM fallback stays off unless --llm is given, so a batch run never sends the
whole folder to a third party by accident. Values are masked by default.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.extraction.pipeline import extract_page
from app.extraction.triage import triage_pdf
from app.schemas.guide import ExtractionStrategy, SpSadtGuide

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def mask(text: str) -> str:
    return re.sub(r"\d", "#", text)


def print_guide(guide: SpSadtGuide, show_values: bool) -> None:
    for name, field in guide.filled_fields().items():
        value = field.value or ""
        print(f"    {name:<32} {value if show_values else mask(value)}")
    for index, procedure in enumerate(guide.procedures, start=1):
        parts = [
            procedure.table,
            procedure.code,
            procedure.description,
            procedure.requested_quantity,
            procedure.authorized_quantity,
        ]
        line = " | ".join((part.value or "") if part else "" for part in parts)
        print(f"    procedure {index}: {line if show_values else mask(line)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--show-values", action="store_true")
    parser.add_argument("--llm", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if not args.llm:
        settings = replace(settings, llm_fallback_enabled=False)
    strategies: Counter[str] = Counter()
    warnings: Counter[str] = Counter()

    print(f"LLM fallback: {'enabled' if settings.llm_available else 'disabled'}\n")
    print(f"{'file':<40} {'page':>4} {'strategy':<11} {'dpi':>5}  warnings")
    print("-" * 110)

    for path in sorted(args.folder.iterdir()):
        if path.suffix.lower() in IMAGE_SUFFIXES:
            strategies["loose image"] += 1
            continue
        if path.suffix.lower() != ".pdf":
            continue

        for triage in triage_pdf(path):
            result = extract_page(path, triage.page_number, triage, settings)
            strategies[result.strategy.value] += 1
            for warning in result.warnings:
                warnings[warning.split(" (")[0]] += 1

            name = path.name[:40] if triage.page_number == 1 else ""
            print(
                f"{name:<40} {triage.page_number:>4} {result.strategy.value:<11} "
                f"{triage.effective_dpi or '-'!s:>5}  {'; '.join(result.warnings)}"
            )

            if result.guide and result.strategy is not ExtractionStrategy.MANUAL:
                print_guide(result.guide, args.show_values)

    print("\nSTRATEGIES")
    for name, count in strategies.most_common():
        print(f"  {name:<24} {count}")
    print("\nWARNINGS")
    for name, count in warnings.most_common():
        print(f"  {count:>3}x {name}")


if __name__ == "__main__":
    main()
