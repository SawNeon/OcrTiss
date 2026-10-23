from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from app.schemas.guide import SpSadtGuide


class FieldOutcome(str, Enum):
    CORRECT = "correct"
    WRONG = "wrong"
    MISSED = "missed"
    FABRICATED = "fabricated"


@dataclass
class FieldComparison:
    field_name: str
    expected: str
    predicted: str
    outcome: FieldOutcome
    character_error_rate: float
    confidence: float | None


@dataclass
class PageScore:
    identifier: str
    profile: str
    doctor_style: str
    strategy: str
    comparisons: list[FieldComparison]
    elapsed_seconds: float

    def count(self, outcome: FieldOutcome) -> int:
        return sum(1 for item in self.comparisons if item.outcome is outcome)

    @property
    def filled_comparisons(self) -> list[FieldComparison]:
        """Only fields the guide actually carries a value for; blanks are scored apart."""
        return [item for item in self.comparisons if item.expected.strip()]

    @property
    def accuracy(self) -> float:
        scored = self.filled_comparisons
        if not scored:
            return 0.0
        return sum(1 for item in scored if item.outcome is FieldOutcome.CORRECT) / len(scored)

    @property
    def mean_cer(self) -> float:
        scored = [item.character_error_rate for item in self.comparisons if item.expected]
        return sum(scored) / len(scored) if scored else 0.0


def normalize(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", ascii_text.upper())


def levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def character_error_rate(expected: str, predicted: str) -> float:
    expected_normalized = normalize(expected)
    if not expected_normalized:
        return 0.0 if not normalize(predicted) else 1.0
    return levenshtein(expected_normalized, normalize(predicted)) / len(expected_normalized)


def _classify(expected: str, predicted: str, cer: float) -> FieldOutcome:
    if not normalize(expected):
        return FieldOutcome.FABRICATED if normalize(predicted) else FieldOutcome.CORRECT
    if not normalize(predicted):
        return FieldOutcome.MISSED
    return FieldOutcome.CORRECT if cer == 0 else FieldOutcome.WRONG


PROCEDURE_FIELD = re.compile(r"^procedure(\d+)_(\w+)$")


def _procedure_field(guide: SpSadtGuide, index: int, attribute: str):
    if index >= len(guide.procedures):
        return None
    return getattr(guide.procedures[index], attribute, None)


def compare_guide(guide: SpSadtGuide | None, ground_truth: dict[str, str]) -> list[FieldComparison]:
    filled = guide.filled_fields() if guide else {}

    comparisons: list[FieldComparison] = []
    for field_name, expected in ground_truth.items():
        procedure_match = PROCEDURE_FIELD.match(field_name)
        if procedure_match and guide:
            extracted = _procedure_field(guide, int(procedure_match.group(1)) - 1, procedure_match.group(2))
        elif procedure_match:
            extracted = None
        else:
            extracted = filled.get(field_name)

        predicted = (extracted.value if extracted else "") or ""
        cer = character_error_rate(expected, predicted)
        comparisons.append(
            FieldComparison(
                field_name=field_name,
                expected=expected,
                predicted=predicted,
                outcome=_classify(expected, predicted, cer),
                character_error_rate=cer,
                confidence=extracted.confidence if extracted else None,
            )
        )
    return comparisons
