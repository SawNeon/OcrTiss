from __future__ import annotations

import random
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from app.preprocessing.cells import extract_cells
from app.recognition.character_classifier import BLANK_LABEL
from app.synthetic.guide_generator import SyntheticGuide
from app.synthetic.layout import FIELDS, PROCEDURE_COLUMNS, comb_cells, procedure_comb_cells

PROCEDURE_ROWS_LABELLED = 3


@dataclass
class LabelledCell:
    image: np.ndarray
    label: str
    field_name: str
    guide_id: str = ""


def to_bgr(image: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def degrade(page: np.ndarray, seed: int) -> np.ndarray:
    """Mild scanner noise, so the classifier does not only know pristine renders."""
    rng = random.Random(seed)
    quality = rng.randint(55, 92)
    encoded = cv2.imencode(".jpg", page, [cv2.IMWRITE_JPEG_QUALITY, quality])[1]
    noisy = cv2.imdecode(encoded, cv2.IMREAD_COLOR)

    blur = rng.choice([0, 0, 3])
    if blur:
        noisy = cv2.GaussianBlur(noisy, (blur, blur), 0)
    return noisy


def cell_labels(value: str, cell_count: int) -> list[str]:
    characters = [character for character in value if character.isalnum()]
    return [
        characters[index] if index < len(characters) else BLANK_LABEL
        for index in range(cell_count)
    ]


def labelled_cells(guide: SyntheticGuide, page: np.ndarray | None = None) -> list[LabelledCell]:
    page = to_bgr(guide.image) if page is None else page
    samples: list[LabelledCell] = []

    for form_field in FIELDS:
        rects = comb_cells(form_field)
        if not rects:
            continue
        cells = extract_cells(page, rects)
        labels = cell_labels(guide.ground_truth.get(form_field.name, ""), len(cells))
        samples.extend(
            LabelledCell(cell, label, form_field.name, guide.identifier) for cell, label in zip(cells, labels, strict=False)
        )

    for row in range(PROCEDURE_ROWS_LABELLED):
        for column, (_, _, _, _, cell_count) in PROCEDURE_COLUMNS.items():
            if not cell_count:
                continue
            rects = procedure_comb_cells(row, column)
            cells = extract_cells(page, rects)
            field_name = f"procedure{row + 1}_{column}"
            labels = cell_labels(guide.ground_truth.get(field_name, ""), len(cells))
            samples.extend(
                LabelledCell(cell, label, field_name, guide.identifier) for cell, label in zip(cells, labels, strict=False)
            )

    return samples
