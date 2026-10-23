from __future__ import annotations

import cv2
import numpy as np


def _remove_form_lines(cell: np.ndarray) -> np.ndarray:
    """Keeps the pen stroke and drops the printed box around it.

    The divider between boxes is a vertical line; left in place, a reader takes
    it for the digit 1.
    """
    grey = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY) if cell.ndim == 3 else cell
    binary = cv2.adaptiveThreshold(grey, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 12)

    vertical = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(6, cell.shape[0] // 3)))
    )
    horizontal = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(6, cell.shape[1] // 2), 1))
    )
    strokes = cv2.subtract(binary, cv2.bitwise_or(vertical, horizontal))
    strokes = cv2.morphologyEx(strokes, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))

    return cv2.cvtColor(cv2.bitwise_not(strokes), cv2.COLOR_GRAY2BGR)


def extract_cells(
    page: np.ndarray, cell_rects: list[tuple[int, int, int, int]], scale: float = 1.0
) -> list[np.ndarray]:
    """One cleaned image per character box, in reading order."""
    cells = []
    for x1, y1, x2, y2 in cell_rects:
        crop = page[int(y1 * scale): int(y2 * scale), int(x1 * scale): int(x2 * scale)]
        if crop.size == 0:
            continue
        cells.append(_remove_form_lines(crop))
    return cells
