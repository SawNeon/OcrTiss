"""Generates synthetic SP/SADT guides with a known ground truth.

Usage:
    python scripts/generate_synthetic_dataset.py DATASET --guides 6

Each guide is rendered once and then captured under every profile, so the same
content can be measured across resolutions. Data is fake, so these files can be
sent to third-party APIs without exposing member data.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.synthetic.capture import PROFILES, apply_capture, wrap_in_pdf
from app.synthetic.guide_generator import generate_guide, save_ground_truth
from app.synthetic.handwriting import FillMode, HandStyle

VARIANTS = [
    (HandStyle.NEAT, FillMode.TYPED_FORM),
    (HandStyle.NEAT, FillMode.MIXED),
    (HandStyle.CURSIVE, FillMode.MIXED),
    (HandStyle.CURSIVE, FillMode.HANDWRITTEN_FORM),
    (HandStyle.RUSHED, FillMode.MIXED),
    (HandStyle.RUSHED, FillMode.HANDWRITTEN_FORM),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--guides", type=int, default=len(VARIANTS))
    parser.add_argument("--seed", type=int, default=20260921)
    args = parser.parse_args()

    args.folder.mkdir(parents=True, exist_ok=True)

    for index in range(args.guides):
        style, fill_mode = VARIANTS[index % len(VARIANTS)]
        identifier = f"guide{index + 1:02d}_{style.value}_{fill_mode.value}"
        guide = generate_guide(identifier, style, seed=args.seed + index, fill_mode=fill_mode)
        save_ground_truth(guide, args.folder)

        for profile in PROFILES:
            jpeg = apply_capture(guide.image, profile, seed=args.seed + index)
            destination = args.folder / f"{identifier}__{profile.name}.pdf"
            wrap_in_pdf(jpeg, destination, profile, seed=args.seed + index)
            print(f"{destination.name:<44} {len(jpeg) // 1024:>5} KB  {profile.frame_width}px")

    print(f"\n{args.guides} guides x {len(PROFILES)} profiles written to {args.folder}")


if __name__ == "__main__":
    main()
