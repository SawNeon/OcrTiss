"""Builds and caches the labelled cell dataset, so classifier experiments do not regenerate it.

Usage:
    python scripts/build_cell_dataset.py --guides 60 --validation 15 --output data/cells.npz
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.recognition.character_classifier import to_patch
from app.recognition.dataset import LabelledCell
from scripts.train_character_model import build_samples


def to_arrays(samples: list[LabelledCell]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    patches = np.array([to_patch(sample.image) for sample in samples], dtype=np.uint8)
    labels = np.array([sample.label for sample in samples])
    groups = np.array([f"{sample.guide_id}|{sample.field_name}" for sample in samples])
    return patches, labels, groups


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guides", type=int, default=60)
    parser.add_argument("--validation", type=int, default=15)
    parser.add_argument("--output", type=Path, default=Path("data/cells.npz"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as workspace:
        folder = Path(workspace)
        print(f"building {args.guides} training guides...")
        training = build_samples(args.guides, 1000, False, folder)
        print(f"building {args.validation} validation guides...")
        validation = build_samples(args.validation, 90000, False, folder)

    train_patches, train_labels, train_groups = to_arrays(training)
    val_patches, val_labels, val_groups = to_arrays(validation)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        train_patches=train_patches, train_labels=train_labels, train_groups=train_groups,
        val_patches=val_patches, val_labels=val_labels, val_groups=val_groups,
    )
    print(f"{len(training)} train / {len(validation)} validation cells saved to {args.output}")


if __name__ == "__main__":
    main()
