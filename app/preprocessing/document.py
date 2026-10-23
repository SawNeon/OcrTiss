from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

MIN_AREA_RATIO = 0.05
CANONICAL_WIDTH = 2400


@dataclass
class DocumentCrop:
    image: np.ndarray
    found: bool
    area_ratio: float


def _order_corners(points: np.ndarray) -> np.ndarray:
    ordered = np.zeros((4, 2), dtype="float32")
    totals = points.sum(axis=1)
    diffs = np.diff(points, axis=1)
    ordered[0] = points[np.argmin(totals)]
    ordered[2] = points[np.argmax(totals)]
    ordered[1] = points[np.argmin(diffs)]
    ordered[3] = points[np.argmax(diffs)]
    return ordered


def _largest_quad(mask: np.ndarray, min_area: float, max_area: float | None = None) -> np.ndarray | None:
    """Largest quadrilateral in the mask, skipping any that covers the whole frame.

    The rendered PDF page is itself a white rectangle, so without `max_area` the
    search stops on the page instead of the sheet photographed inside it.
    """
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8), iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:6]:
        area = cv2.contourArea(contour)
        if area < min_area:
            break
        if max_area is not None and area > max_area:
            continue

        approximation = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(approximation) == 4:
            return approximation.reshape(4, 2).astype("float32")
        return cv2.boxPoints(cv2.minAreaRect(contour)).astype("float32")
    return None


MIN_INTERIOR_BRIGHTNESS = 150
MIN_BACKGROUND_CONTRAST = 25


def _quad_mask(shape: tuple[int, int], quad: np.ndarray) -> np.ndarray:
    mask = np.zeros(shape, np.uint8)
    cv2.fillConvexPoly(mask, quad.astype(np.int32), 255)
    return mask


def _interior_brightness(grey: np.ndarray, quad: np.ndarray) -> float:
    eroded = cv2.erode(_quad_mask(grey.shape, quad), np.ones((25, 25), np.uint8), iterations=2)
    return float(cv2.mean(grey, mask=eroded)[0])


def _background_contrast(grey: np.ndarray, quad: np.ndarray) -> float:
    """Paper only counts as cropped out if what surrounds it is clearly darker.

    On a flatbed scan the page fills the frame and there is no darker
    background, so any bright rectangle found inside the form is not the sheet.
    """
    mask = _quad_mask(grey.shape, quad)
    outside = cv2.bitwise_not(cv2.dilate(mask, np.ones((25, 25), np.uint8), iterations=2))
    if cv2.countNonZero(outside) < grey.size * 0.02:
        return 0.0
    return _interior_brightness(grey, quad) - float(cv2.mean(grey, mask=outside)[0])


def _paper_quad(image: np.ndarray) -> np.ndarray | None:
    """The sheet: a large quadrilateral whose inside is bright. The desk around it is not."""
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(grey, (7, 7), 0)
    page_area = image.shape[0] * image.shape[1]

    masks = [
        cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1],
        cv2.dilate(cv2.Canny(blurred, 40, 140), np.ones((5, 5), np.uint8), iterations=2),
    ]

    best = None
    for mask in masks:
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8), iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
            area = cv2.contourArea(contour)
            if area < page_area * MIN_AREA_RATIO or area > page_area * 0.92:
                continue
            approximation = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
            quad = (
                approximation.reshape(4, 2).astype("float32")
                if len(approximation) == 4
                else cv2.boxPoints(cv2.minAreaRect(contour)).astype("float32")
            )
            if _interior_brightness(grey, quad) < MIN_INTERIOR_BRIGHTNESS:
                continue
            if _background_contrast(grey, quad) < MIN_BACKGROUND_CONTRAST:
                continue
            if best is None or area > cv2.contourArea(best):
                best = quad
    return best


def _frame_quad(image: np.ndarray) -> np.ndarray | None:
    """Inside the sheet, the printed form frame is the ink rectangle around every field."""
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    page_area = image.shape[0] * image.shape[1]

    ink = cv2.adaptiveThreshold(grey, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 15)
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8), iterations=3)

    contours, _ = cv2.findContours(ink, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:6]:
        area = cv2.contourArea(contour)
        if area < page_area * 0.25:
            break
        if area > page_area * 0.995:
            continue
        quad = cv2.boxPoints(cv2.minAreaRect(contour)).astype("float32")
        if _interior_brightness(grey, quad) >= MIN_INTERIOR_BRIGHTNESS:
            return quad
    return None


def _warp_to(image: np.ndarray, corners: np.ndarray, width: int, height: int) -> np.ndarray:
    destination = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32"
    )
    transform = cv2.getPerspectiveTransform(_order_corners(corners), destination)
    return cv2.warpPerspective(image, transform, (width, height))


def extract_document(image: np.ndarray, aspect_ratio: float) -> DocumentCrop:
    """Isolates the sheet of paper, then squares up the printed form frame inside it."""
    page_area = image.shape[0] * image.shape[1]
    height = int(CANONICAL_WIDTH * aspect_ratio)

    paper = _paper_quad(image)
    working = image if paper is None else _warp_to(image, paper, CANONICAL_WIDTH, height)
    area_ratio = 1.0 if paper is None else cv2.contourArea(paper) / page_area

    frame = _frame_quad(working)
    if frame is None:
        return DocumentCrop(image=working, found=paper is not None, area_ratio=area_ratio)

    return DocumentCrop(
        image=_warp_to(working, frame, CANONICAL_WIDTH, height), found=True, area_ratio=area_ratio
    )


def deskew(image: np.ndarray, max_angle: float = 6.0) -> np.ndarray:
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    inverted = cv2.bitwise_not(grey)
    threshold = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

    lines = cv2.HoughLinesP(threshold, 1, np.pi / 720, 260, minLineLength=image.shape[1] // 3, maxLineGap=24)
    if lines is None:
        return image

    angles = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        angle = np.degrees(np.arctan2(float(y2 - y1), float(x2 - x1)))
        if abs(angle) < max_angle:
            angles.append(angle)

    if not angles:
        return image

    rotation = float(np.median(angles))
    centre = (image.shape[1] // 2, image.shape[0] // 2)
    matrix = cv2.getRotationMatrix2D(centre, rotation, 1.0)
    return cv2.warpAffine(
        image, matrix, (image.shape[1], image.shape[0]),
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE,
    )
