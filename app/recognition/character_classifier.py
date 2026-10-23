from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from sklearn.neural_network import MLPClassifier

PATCH_SIZE = 24
BLANK_LABEL = "_"
DEFAULT_MODEL_PATH = Path("models/character_mlp.pkl")
MIN_INK_PIXELS = 12
HOG_CELL = 6
HOG_BINS = 9
HIDDEN_LAYERS = (512, 256)
MAX_ITERATIONS = 200


@dataclass
class Prediction:
    character: str
    confidence: float


def to_patch(cell: np.ndarray) -> np.ndarray:
    """Normalises one cell crop into a fixed-size, centred, binary patch."""
    grey = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY) if cell.ndim == 3 else cell
    binary = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

    points = cv2.findNonZero(binary)
    if points is not None and len(points) >= MIN_INK_PIXELS:
        x, y, width, height = cv2.boundingRect(points)
        cropped = binary[y: y + height, x: x + width]
        side = max(width, height)
        square = np.zeros((side, side), np.uint8)
        top, left = (side - height) // 2, (side - width) // 2
        square[top: top + height, left: left + width] = cropped
        binary = square

    return cv2.resize(binary, (PATCH_SIZE, PATCH_SIZE), interpolation=cv2.INTER_AREA)


def is_blank(cell: np.ndarray) -> bool:
    return int(np.count_nonzero(to_patch(cell))) < MIN_INK_PIXELS


def hog_features(patch: np.ndarray) -> np.ndarray:
    """Gradient orientation histogram: what the stroke does, not which pixels it hits."""
    image = patch.astype(np.float32) / 255.0
    gradient_x = cv2.Sobel(image, cv2.CV_32F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(image, cv2.CV_32F, 0, 1, ksize=3)

    magnitude = np.hypot(gradient_x, gradient_y)
    angle = np.rad2deg(np.arctan2(gradient_y, gradient_x)) % 180
    bins = np.minimum((angle / (180 / HOG_BINS)).astype(int), HOG_BINS - 1)

    size = patch.shape[0] // HOG_CELL
    histogram = np.zeros((size, size, HOG_BINS), np.float32)
    for row in range(size):
        for column in range(size):
            window = (slice(row * HOG_CELL, (row + 1) * HOG_CELL), slice(column * HOG_CELL, (column + 1) * HOG_CELL))
            histogram[row, column] = np.bincount(
                bins[window].ravel(), weights=magnitude[window].ravel(), minlength=HOG_BINS
            )

    blocks = []
    for row in range(size - 1):
        for column in range(size - 1):
            block = histogram[row: row + 2, column: column + 2].ravel()
            blocks.append(block / (np.linalg.norm(block) + 1e-6))
    return np.concatenate(blocks).astype(np.float32)


def to_features(cell: np.ndarray) -> np.ndarray:
    patch = to_patch(cell) if cell.shape[:2] != (PATCH_SIZE, PATCH_SIZE) or cell.ndim == 3 else cell
    normalised = patch.astype(np.float32) / 255.0
    columns = normalised.sum(axis=0) / PATCH_SIZE
    rows = normalised.sum(axis=1) / PATCH_SIZE
    return np.concatenate(
        [normalised.flatten(), columns, rows, hog_features(patch)]
    ).astype(np.float32)


class CharacterClassifier:
    def __init__(self, model: MLPClassifier) -> None:
        self._model = model

    @classmethod
    def train(cls, cells: list[np.ndarray], labels: list[str]) -> CharacterClassifier:
        samples = np.array([to_features(cell) for cell in cells], dtype=np.float32)
        model = MLPClassifier(hidden_layer_sizes=HIDDEN_LAYERS, max_iter=MAX_ITERATIONS, random_state=0)
        model.fit(samples, labels)
        return cls(model)

    def predict_many(self, cells: list[np.ndarray]) -> list[Prediction]:
        predictions: list[Prediction] = [Prediction(BLANK_LABEL, 1.0)] * len(cells)
        pending = [(index, cell) for index, cell in enumerate(cells) if not is_blank(cell)]
        if not pending:
            return predictions

        features = np.array([to_features(cell) for _, cell in pending], dtype=np.float32)
        probabilities = self._model.predict_proba(features)
        classes = self._model.classes_

        for row, (index, _) in enumerate(pending):
            best = int(np.argmax(probabilities[row]))
            predictions[index] = Prediction(str(classes[best]), float(probabilities[row][best]))
        return predictions

    def predict_topk(self, cells: list[np.ndarray], k: int = 3) -> list[list[Prediction]]:
        """Per cell, the k most likely characters — the raw material for constrained decoding."""
        ranked: list[list[Prediction]] = [[Prediction(BLANK_LABEL, 1.0)] for _ in cells]
        pending = [(index, cell) for index, cell in enumerate(cells) if not is_blank(cell)]
        if not pending:
            return ranked

        features = np.array([to_features(cell) for _, cell in pending], dtype=np.float32)
        probabilities = self._model.predict_proba(features)
        classes = self._model.classes_

        for row, (index, _) in enumerate(pending):
            order = np.argsort(probabilities[row])[::-1][:k]
            ranked[index] = [
                Prediction(str(classes[position]), float(probabilities[row][position]))
                for position in order
            ]
        return ranked

    def predict(self, cell: np.ndarray) -> Prediction:
        return self.predict_many([cell])[0]

    def read_cells(self, cells: list[np.ndarray]) -> tuple[str, float]:
        predictions = [item for item in self.predict_many(cells) if item.character != BLANK_LABEL]
        if not predictions:
            return "", 1.0
        value = "".join(item.character for item in predictions)
        return value, float(np.mean([item.confidence for item in predictions]))

    def save(self, path: Path = DEFAULT_MODEL_PATH) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps(self._model))
        return path

    @classmethod
    def load(cls, path: Path = DEFAULT_MODEL_PATH) -> CharacterClassifier:
        return cls(pickle.loads(path.read_bytes()))
