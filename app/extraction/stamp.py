"""Reads the professional's stamp, which is often the only place the CRM exists.

Fields 16 to 19 of the form are frequently left blank while the doctor stamps
name, specialty and council registration at the bottom. The stamp is printed
text, so it reads far better than the handwritten boxes — and it does not
depend on the layout being recognised.
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

STATES = {
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT",
    "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
}
COUNCILS = ("CRM", "CRO", "CRF", "CRN", "CREFITO", "COREN")

# "CRM-MG: 41287", "CRM MG 41287", "CRM: 41287-MG", "CRM/MG 41.287"
COUNCIL_PATTERN = re.compile(
    r"\b(?P<council>CRM|CRO|CRF|CRN|CREFITO|COREN)\b"
    r"[\s:./-]*"
    r"(?:(?P<state_before>[A-Z]{2})\b[\s:./-]*)?"
    r"(?P<number>\d{1,3}(?:[.\s]\d{3}|\d{2,5}))"
    r"(?:[\s:./-]*(?P<state_after>[A-Z]{2})\b)?",
    re.IGNORECASE,
)
NAME_LINE = re.compile(
    r"^(?:dr[a]?\.?\s*)?(?P<name>[A-Za-zÀ-ÿ'´`^~]{2,}(?:\s+[A-Za-zÀ-ÿ'´`^~]{2,}){1,5})$",
    re.IGNORECASE,
)
NOT_A_NAME = re.compile(r"\b(CRM|CRO|CRF|RQE|CNES|CBO|CPF|CNPJ|TELEFONE|FONE|RUA|AV|AVENIDA)\b", re.IGNORECASE)


MIN_REGISTRATION_DIGITS = 4
MAX_REGISTRATION_DIGITS = 7


def is_implausible(number: str) -> bool:
    """Rejects the shapes a reader invents when it cannot actually see the digits.

    A stamp read at low resolution tends to come back as a placeholder — 123456,
    000000 — which looks like a registration and is not one.
    """
    if not number.isdigit() or not MIN_REGISTRATION_DIGITS <= len(number) <= MAX_REGISTRATION_DIGITS:
        return True
    if len(set(number)) == 1:
        return True

    steps = {int(second) - int(first) for first, second in itertools.pairwise(number)}
    return steps in ({1}, {-1})


@dataclass
class StampData:
    raw_text: str
    council: str | None = None
    council_number: str | None = None
    council_state: str | None = None
    professional_name: str | None = None
    rejected_number: str | None = None

    @property
    def has_registration(self) -> bool:
        return bool(self.council_number)


def _clean_number(value: str) -> str:
    return re.sub(r"\D", "", value)


def parse_stamp(text: str | None) -> StampData:
    if not text or not text.strip():
        return StampData(raw_text="")

    stamp = StampData(raw_text=text.strip())
    match = COUNCIL_PATTERN.search(text)

    if match:
        stamp.council = match.group("council").upper()
        number = _clean_number(match.group("number"))
        if is_implausible(number):
            stamp.rejected_number = number
        else:
            stamp.council_number = number
        state = (match.group("state_before") or match.group("state_after") or "").upper()
        if state in STATES:
            stamp.council_state = state

    for line in (item.strip(" .:-") for item in text.splitlines()):
        if not line or NOT_A_NAME.search(line):
            continue
        name = NAME_LINE.match(line)
        if name:
            stamp.professional_name = name.group("name").strip().upper()
            break

    return stamp
