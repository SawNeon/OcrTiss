"""Trains the local character classifier on synthetic form cells.

Usage:
    python scripts/train_character_model.py --guides 40 --validation 10 [--pristine]

Cells are cut through the same path the reader uses — render, crop, align — so
the classifier learns the geometry it will actually meet. Every value is known,
so labels are exact and the training set costs nothing. No data leaves the machine.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.extraction.template_reader import aligned_cells
from app.recognition.character_classifier import BLANK_LABEL, DEFAULT_MODEL_PATH, CharacterClassifier
from app.recognition.dataset import LabelledCell, cell_labels, degrade, labelled_cells, to_bgr
from app.synthetic.capture import PROFILES, apply_capture, wrap_in_pdf
from app.synthetic.guide_generator import SyntheticGuide, generate_guide
from app.synthetic.handwriting import FillMode, HandStyle

VARIANTS = [
    (HandStyle.NEAT, FillMode.MIXED),
    (HandStyle.CURSIVE, FillMode.MIXED),
    (HandStyle.RUSHED, FillMode.MIXED),
    (HandStyle.NEAT, FillMode.HANDWRITTEN_FORM),
    (HandStyle.CURSIVE, FillMode.HANDWRITTEN_FORM),
    (HandStyle.RUSHED, FillMode.HANDWRITTEN_FORM),
    (HandStyle.NEAT, FillMode.TYPED_FORM),
]
SCAN_PROFILE = next(profile for profile in PROFILES if profile.name == "scan_good")


def make_guide(index: int, seed_base: int) -> SyntheticGuide:
    style, fill_mode = VARIANTS[index % len(VARIANTS)]
    return generate_guide(f"g{index}", style, seed=seed_base + index, fill_mode=fill_mode)


def pipeline_cells(guide: SyntheticGuide, folder: Path, index: int) -> list[LabelledCell]:
    """Same render → capture → crop → align path the reader takes at inference."""
    destination = folder / f"{index}.pdf"
    wrap_in_pdf(apply_capture(guide.image, SCAN_PROFILE, seed=index), destination, SCAN_PROFILE, seed=index)

    page = aligned_cells(destination)
    samples: list[LabelledCell] = []
    for field_name, cells in page.cells.items():
        labels = cell_labels(guide.ground_truth.get(field_name, ""), len(cells))
        samples.extend(LabelledCell(cell, label, field_name, guide.identifier) for cell, label in zip(cells, labels, strict=False))
    return samples


def build_samples(count: int, seed_base: int, pristine: bool, folder: Path) -> list[LabelledCell]:
    samples: list[LabelledCell] = []
    for index in range(count):
        guide = make_guide(index, seed_base)
        if pristine:
            page = to_bgr(guide.image)
            samples.extend(labelled_cells(guide, page))
            samples.extend(labelled_cells(guide, degrade(page, seed_base + index)))
        else:
            samples.extend(pipeline_cells(guide, folder, seed_base + index))
        print(f"  guide {index + 1}/{count}", end="\r", flush=True)
    print()
    return samples


def score(classifier: CharacterClassifier, samples: list[LabelledCell]) -> tuple[float, dict[str, list[int]]]:
    predictions = classifier.predict_many([sample.image for sample in samples])
    correct = 0
    per_label: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    for sample, prediction in zip(samples, predictions, strict=False):
        per_label[sample.label][1] += 1
        if prediction.character == sample.label:
            correct += 1
            per_label[sample.label][0] += 1

    return correct / len(samples), per_label


def score_fields(classifier: CharacterClassifier, samples: list[LabelledCell]) -> float:
    grouped: dict[tuple[str, str], list[LabelledCell]] = defaultdict(list)
    for sample in samples:
        grouped[(sample.guide_id, sample.field_name)].append(sample)

    correct = total = 0
    for field_samples in grouped.values():
        expected = "".join(sample.label for sample in field_samples if sample.label != BLANK_LABEL)
        if not expected:
            continue
        predicted, _ = classifier.read_cells([sample.image for sample in field_samples])
        total += 1
        correct += predicted == expected
    return correct / total if total else 0.0


def train_from_cache(dataset: Path, output: Path) -> None:
    import numpy as np

    cached = np.load(dataset, allow_pickle=True)
    training = [
        LabelledCell(patch, label, group.split("|")[1], group.split("|")[0])
        for patch, label, group in zip(cached["train_patches"], cached["train_labels"], cached["train_groups"], strict=False)
    ]
    validation = [
        LabelledCell(patch, label, group.split("|")[1], group.split("|")[0])
        for patch, label, group in zip(cached["val_patches"], cached["val_labels"], cached["val_groups"], strict=False)
    ]

    print(f"{len(training)} training cells, {len(validation)} validation cells")
    classifier = CharacterClassifier.train(
        [sample.image for sample in training], [sample.label for sample in training]
    )

    accuracy, _ = score(classifier, validation)
    written = [sample for sample in validation if sample.label != BLANK_LABEL]
    written_accuracy, _ = score(classifier, written)
    print(f"per-character accuracy: {accuracy:.1%} (written cells only: {written_accuracy:.1%})")
    print(f"whole-field exact match: {score_fields(classifier, validation):.1%}")
    print(f"model saved to {classifier.save(output)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guides", type=int, default=40)
    parser.add_argument("--validation", type=int, default=10)
    parser.add_argument("--pristine", action="store_true", help="skip the capture and alignment path")
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--dataset", type=Path, help="cached npz from build_cell_dataset.py")
    args = parser.parse_args()

    if args.dataset:
        train_from_cache(args.dataset, args.output)
        return

    with tempfile.TemporaryDirectory() as workspace:
        folder = Path(workspace)
        print(f"building {args.guides} training guides...")
        training = build_samples(args.guides, 1000, args.pristine, folder)
        print(f"building {args.validation} validation guides...")
        validation = build_samples(args.validation, 90000, args.pristine, folder)

    distribution = Counter(sample.label for sample in training)
    print(f"{len(training)} training cells, {len(validation)} validation cells")
    print("characters:", "".join(sorted(key for key in distribution if key != BLANK_LABEL)))
    print(f"blank cells: {distribution[BLANK_LABEL]}")

    classifier = CharacterClassifier.train(
        [sample.image for sample in training], [sample.label for sample in training]
    )

    accuracy, per_label = score(classifier, validation)
    print(f"\nper-character accuracy: {accuracy:.1%}")
    ranked = sorted(
        ((label, hits / seen, seen) for label, (hits, seen) in per_label.items() if seen >= 10),
        key=lambda item: item[1],
    )
    print("worst characters:")
    for label, rate, seen in ranked[:8]:
        print(f"  {label!r:>5} {rate:>6.1%}  ({seen} cells)")

    print(f"\nwhole-field exact match: {score_fields(classifier, validation):.1%}")

    path = classifier.save(args.output)
    print(f"model saved to {path}")


if __name__ == "__main__":
    main()
