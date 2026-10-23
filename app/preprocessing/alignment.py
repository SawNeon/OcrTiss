from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

MIN_MATCHES = 18
RATIO_TEST = 0.8
MAX_FEATURES = 6000
ECC_WIDTH = 900
ECC_ITERATIONS = 300


@dataclass
class Alignment:
    image: np.ndarray
    aligned: bool
    matches: int
    score: float = 0.0


def _keypoints(detector, image: np.ndarray):
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    grey = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(grey)
    return detector.detectAndCompute(grey, None)


def _ecc_align(image: np.ndarray, template: np.ndarray) -> Alignment:
    """Refinement for pages already close to the template: matches intensity, not features.

    The form repeats the same little box thousands of times, so feature matching
    can run out of distinctive points; intensity alignment does not care.
    """
    height, width = template.shape[:2]
    scale = ECC_WIDTH / width

    small_template = cv2.resize(cv2.cvtColor(template, cv2.COLOR_BGR2GRAY), (ECC_WIDTH, int(height * scale)))
    resized = cv2.resize(image, (ECC_WIDTH, int(image.shape[0] * ECC_WIDTH / image.shape[1])))
    small_page = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

    if small_page.shape != small_template.shape:
        small_page = cv2.resize(small_page, (small_template.shape[1], small_template.shape[0]))

    warp = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, ECC_ITERATIONS, 1e-6)

    # ECC is parallelised, and the thread split changes the last decimals of the
    # transform. A couple of pixels there is the difference between reading a box
    # and reading its neighbour, so the same guide must always align the same way.
    threads = cv2.getNumThreads()
    cv2.setNumThreads(1)
    try:
        cv2.findTransformECC(small_template, small_page, warp, cv2.MOTION_AFFINE, criteria, None, 5)
    except cv2.error:
        return Alignment(image, False, 0)
    finally:
        cv2.setNumThreads(threads)

    warp[0, 2] /= scale
    warp[1, 2] /= scale
    full = cv2.resize(image, (width, height))
    aligned = cv2.warpAffine(
        full, warp, (width, height), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE
    )
    return Alignment(aligned, True, 0)


def correlation(image: np.ndarray, template: np.ndarray) -> float:
    """How well the page's printed lines sit on top of the template's."""
    height, width = template.shape[:2]
    scale = ECC_WIDTH / width
    size = (ECC_WIDTH, int(height * scale))

    left = cv2.resize(cv2.cvtColor(template, cv2.COLOR_BGR2GRAY), size)
    right = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), size)
    return float(cv2.matchTemplate(right, left, cv2.TM_CCOEFF_NORMED)[0][0])


def align_to_template(image: np.ndarray, template: np.ndarray) -> Alignment:
    """Picks, among the alignment candidates, the one that best overlays the template."""
    height, width = template.shape[:2]
    candidates = [Alignment(cv2.resize(image, (width, height)), False, 0)]

    feature_alignment = _feature_align(image, template)
    if feature_alignment is not None:
        candidates.append(feature_alignment)
    candidates.append(_ecc_align(image, template))

    best = max(candidates, key=lambda candidate: correlation(candidate.image, template))
    best.score = correlation(best.image, template)
    return best


def _feature_align(image: np.ndarray, template: np.ndarray) -> Alignment | None:
    detector = cv2.ORB_create(MAX_FEATURES)
    page_keypoints, page_descriptors = _keypoints(detector, image)
    template_keypoints, template_descriptors = _keypoints(detector, template)

    if page_descriptors is None or template_descriptors is None:
        return None

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs = matcher.knnMatch(page_descriptors, template_descriptors, k=2)
    good = [first for first, second in (pair for pair in pairs if len(pair) == 2) if first.distance < RATIO_TEST * second.distance]

    if len(good) < MIN_MATCHES:
        return None

    source = np.float32([page_keypoints[match.queryIdx].pt for match in good]).reshape(-1, 1, 2)
    destination = np.float32([template_keypoints[match.trainIdx].pt for match in good]).reshape(-1, 1, 2)

    homography, mask = cv2.findHomography(source, destination, cv2.RANSAC, 5.0)
    if homography is None:
        return None

    height, width = template.shape[:2]
    warped = cv2.warpPerspective(image, homography, (width, height), borderMode=cv2.BORDER_REPLICATE)
    return Alignment(warped, True, int(mask.sum()))
