"""Turns per-cell candidates into a field value that satisfies the field's own rules.

A 90%-accurate character reader still gets most long codes wrong, because one
bad cell ruins the whole field. Most TISS fields are constrained — a date, a UF,
a code that exists in a table — so the reading that satisfies the constraint is
almost always the right one.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from app.recognition.character_classifier import BLANK_LABEL, CharacterClassifier, Prediction

MAX_COMBINATIONS = 4000
STATES = {
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT",
    "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
}


@dataclass
class DecodedField:
    value: str
    confidence: float
    validated: bool | None
    """True if it satisfies the field rule, False if it does not, None when the field has no rule."""


def is_valid_date(value: str) -> bool:
    if len(value) != 8 or not value.isdigit():
        return False
    try:
        date(int(value[4:]), int(value[2:4]), int(value[:2]))
    except ValueError:
        return False
    return True


def digits_of_length(length: int) -> Callable[[str], bool]:
    return lambda value: len(value) == length and value.isdigit()


def one_of(options: set[str]) -> Callable[[str], bool]:
    return lambda value: value in options


def in_catalogue(catalogue: set[str]) -> Callable[[str], bool]:
    return lambda value: value in catalogue


ICD10 = re.compile(r"^[A-Z]\d{3}$")

VALIDATORS: dict[str, Callable[[str], bool]] = {
    "authorization_date": is_valid_date,
    "password_expiry_date": is_valid_date,
    "card_expiry_date": is_valid_date,
    "suggested_admission_date": is_valid_date,
    "authorized_admission_date": is_valid_date,
    "request_date": is_valid_date,
    "council_state": one_of(STATES),
    "care_type": one_of({"E", "U"}),
    "main_icd10": lambda value: bool(ICD10.match(value)),
    "icd10_2": lambda value: bool(ICD10.match(value)),
    "icd10_3": lambda value: bool(ICD10.match(value)),
    "icd10_4": lambda value: bool(ICD10.match(value)),
    "ans_registration": digits_of_length(6),
    "cbo_code": digits_of_length(6),
    "member_card_number": digits_of_length(17),
    "requested_daily_rates": lambda value: value.isdigit() and 0 < int(value) < 100,
}


def register_catalogue(field_name: str, catalogue: set[str]) -> None:
    """Points a field at an official table (TUSS, CID-10, CBO) loaded by the caller."""
    VALIDATORS[field_name] = in_catalogue(catalogue)


def _candidates(ranked: list[list[Prediction]]) -> list[tuple[float, str]]:
    written = [options for options in ranked if options[0].character != BLANK_LABEL]
    if not written:
        return [(1.0, "")]

    beams: list[tuple[float, str]] = [(1.0, "")]
    for options in written:
        expanded = [
            (score * option.confidence, value + option.character)
            for score, value in beams
            for option in options
            if option.character != BLANK_LABEL
        ]
        expanded.sort(key=lambda item: -item[0])
        beams = expanded[:MAX_COMBINATIONS]
    return beams


def decode_field(
    classifier: CharacterClassifier, field_name: str, cells: list, top_k: int = 3
) -> DecodedField:
    ranked = classifier.predict_topk(cells, top_k)
    beams = _candidates(ranked)
    best_score, best_value = beams[0]

    validator = VALIDATORS.get(field_name)
    if validator is None:
        return DecodedField(best_value, best_score, None)

    for score, value in beams:
        if validator(value):
            return DecodedField(value, score, True)

    return DecodedField(best_value, best_score, False)
