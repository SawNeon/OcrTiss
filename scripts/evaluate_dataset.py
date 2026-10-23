"""Runs the extraction pipeline over a synthetic dataset and scores it field by field.

Usage:
    python scripts/evaluate_dataset.py DATASET [--llm] [--profile phone_far]

Ground truth comes from the JSON written by generate_synthetic_dataset.py, so
accuracy, character error rate and fabricated values are measured, not guessed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.evaluation.metrics import FieldOutcome, PageScore, compare_guide
from app.extraction.pipeline import extract_page
from app.extraction.triage import triage_pdf


def load_ground_truth(folder: Path) -> dict[str, dict]:
    return {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in folder.glob("*.json")}


def score_file(pdf_path: Path, truth: dict, settings) -> PageScore:
    identifier, profile = pdf_path.stem.split("__")
    triage = triage_pdf(pdf_path)[0]

    started = time.perf_counter()
    result = extract_page(pdf_path, 1, triage, settings)
    elapsed = time.perf_counter() - started

    return PageScore(
        identifier=identifier,
        profile=profile,
        doctor_style=truth["doctor_style"],
        strategy=result.strategy.value,
        comparisons=compare_guide(result.guide, truth["fields"]),
        elapsed_seconds=elapsed,
    )


def print_summary(scores: list[PageScore], group_by: str) -> None:
    grouped: dict[str, list[PageScore]] = defaultdict(list)
    for score in scores:
        grouped[getattr(score, group_by)].append(score)

    print(f"\n{group_by:<14} {'acerto':>7} {'CER':>7} {'certos':>7} {'errados':>8} {'faltou':>7} {'inventou':>9} {'seg':>6}")
    print("-" * 78)
    for name, group in grouped.items():
        totals = {outcome: sum(item.count(outcome) for item in group) for outcome in FieldOutcome}
        accuracy = sum(item.accuracy for item in group) / len(group)
        mean_cer = sum(item.mean_cer for item in group) / len(group)
        elapsed = sum(item.elapsed_seconds for item in group) / len(group)
        print(
            f"{name:<14} {accuracy:>6.1%} {mean_cer:>7.2f} {totals[FieldOutcome.CORRECT]:>7} "
            f"{totals[FieldOutcome.WRONG]:>8} {totals[FieldOutcome.MISSED]:>7} "
            f"{totals[FieldOutcome.FABRICATED]:>9} {elapsed:>6.1f}"
        )


def print_worst_fields(scores: list[PageScore], limit: int = 12) -> None:
    failures: dict[str, int] = defaultdict(int)
    for score in scores:
        for comparison in score.comparisons:
            if comparison.outcome in {FieldOutcome.WRONG, FieldOutcome.FABRICATED}:
                failures[comparison.field_name] += 1

    if not failures:
        return
    print("\ncampos com leitura errada ou inventada")
    for name, count in sorted(failures.items(), key=lambda item: -item[1])[:limit]:
        print(f"  {count:>3}x {name}")


def print_examples(scores: list[PageScore], limit: int = 8) -> None:
    print("\nexemplos de invenção (esperado -> lido)")
    shown = 0
    for score in scores:
        for comparison in score.comparisons:
            if comparison.outcome is FieldOutcome.WRONG and comparison.character_error_rate > 0.4:
                print(
                    f"  [{score.profile}/{score.doctor_style}] {comparison.field_name}: "
                    f"{comparison.expected[:40]!r} -> {comparison.predicted[:40]!r} (conf {comparison.confidence})"
                )
                shown += 1
                if shown >= limit:
                    return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--template", action="store_true")
    parser.add_argument("--profile")
    parser.add_argument("--output", type=Path, help="save the scored comparisons as JSON")
    args = parser.parse_args()

    settings = get_settings()
    settings = replace(
        settings,
        llm_fallback_enabled=args.llm,
        template_reader_enabled=args.template and args.llm,
    )

    ground_truth = load_ground_truth(args.folder)
    scores: list[PageScore] = []

    for pdf_path in sorted(args.folder.glob("*.pdf")):
        identifier, profile = pdf_path.stem.split("__")
        if args.profile and profile != args.profile:
            continue
        truth = ground_truth.get(identifier)
        if not truth:
            continue

        score = score_file(pdf_path, truth, settings)
        scores.append(score)
        print(
            f"{pdf_path.stem:<40} {score.strategy:<11} acerto={score.accuracy:>6.1%} "
            f"CER={score.mean_cer:.2f} ({score.elapsed_seconds:.1f}s)"
        )

    if not scores:
        print("nada avaliado")
        return

    print_summary(scores, "profile")
    print_summary(scores, "doctor_style")
    print_worst_fields(scores)
    print_examples(scores)

    if args.output:
        payload = [
            {
                "identifier": score.identifier,
                "profile": score.profile,
                "doctor_style": score.doctor_style,
                "strategy": score.strategy,
                "accuracy": score.accuracy,
                "mean_cer": score.mean_cer,
                "fields": [
                    {
                        "field": item.field_name,
                        "expected": item.expected,
                        "predicted": item.predicted,
                        "outcome": item.outcome.value,
                        "cer": item.character_error_rate,
                        "confidence": item.confidence,
                    }
                    for item in score.comparisons
                ],
            }
            for score in scores
        ]
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nresultados salvos em {args.output}")


if __name__ == "__main__":
    main()
