"""Registry of professionals: the tool's memory of who signs the guides.

A CRM read from a stamp is a guess; the same CRM matched against a name already
in the registry is evidence. The registry turns one into the other, and grows
every time a reviewer confirms a guide.
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

# Measured on the operator's own registry of 392 cooperados: two different
# people share an identical name (1.000), a father and son differ by "JUNIOR"
# (0.851) and siblings share a surname (0.897) — while a correctly identified
# professional whose name was misread scores 0.773. The distributions overlap
# completely, so a name is never enough on its own, at any threshold. It only
# narrows the list a reviewer chooses from, or corroborates a number.
NAME_SUGGESTION_THRESHOLD = 0.75
NAME_CORROBORATION_THRESHOLD = 0.90
NUMBER_NEIGHBOUR_RATIO = 0.75
MAX_SUGGESTIONS = 3


@dataclass
class Professional:
    council: str
    council_number: str
    council_state: str | None
    full_name: str
    specialty: str | None = None
    operator_code: str | None = None
    confirmations: int = 0

    @property
    def label(self) -> str:
        state = f"-{self.council_state}" if self.council_state else ""
        return f"{self.full_name} ({self.council}{state} {self.council_number})"


@dataclass
class Match:
    professional: Professional
    reason: str
    score: float
    apply_automatically: bool
    corrects_number: bool = False


def normalise_name(name: str) -> str:
    without_accents = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z ]", " ", without_accents.upper())


def _collapse(name: str) -> str:
    return " ".join(normalise_name(name).split())


def _to_professional(row: sqlite3.Row) -> Professional:
    return Professional(
        council=row["council"],
        council_number=row["council_number"],
        council_state=row["council_state"],
        full_name=row["full_name"],
        specialty=row["specialty"],
        operator_code=row["operator_code"],
        confirmations=row["confirmations"],
    )


def upsert(
    connection: sqlite3.Connection,
    professional: Professional,
    source: str,
    confirm: bool = False,
) -> None:
    connection.execute(
        """
        INSERT INTO professionals (council, council_number, council_state, full_name,
                                   normalised_name, specialty, operator_code, source, confirmations)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (council, council_number, council_state) DO UPDATE SET
            full_name = COALESCE(NULLIF(excluded.full_name, ''), professionals.full_name),
            normalised_name = COALESCE(NULLIF(excluded.normalised_name, ''), professionals.normalised_name),
            specialty = COALESCE(NULLIF(excluded.specialty, ''), professionals.specialty),
            operator_code = COALESCE(NULLIF(excluded.operator_code, ''), professionals.operator_code),
            confirmations = professionals.confirmations + excluded.confirmations,
            updated_at = datetime('now')
        """,
        (
            professional.council,
            professional.council_number,
            professional.council_state,
            professional.full_name,
            _collapse(professional.full_name),
            professional.specialty,
            professional.operator_code,
            source,
            1 if confirm else 0,
        ),
    )


def count(connection: sqlite3.Connection) -> int:
    return connection.execute("SELECT COUNT(*) AS total FROM professionals").fetchone()["total"]


def duplicate_names(connection: sqlite3.Connection) -> list[tuple[str, list[str]]]:
    """Homonyms in the registry: proof that a name cannot identify a professional."""
    rows = connection.execute(
        """
        SELECT normalised_name, GROUP_CONCAT(council_number) AS numbers, COUNT(*) AS total
        FROM professionals
        GROUP BY normalised_name
        HAVING total > 1
        ORDER BY total DESC
        """
    ).fetchall()
    return [(row["normalised_name"], row["numbers"].split(",")) for row in rows]


def find_by_number(
    connection: sqlite3.Connection, council_number: str, state: str | None = None
) -> Professional | None:
    if state:
        row = connection.execute(
            "SELECT * FROM professionals WHERE council_number = ? AND council_state = ?",
            (council_number, state),
        ).fetchone()
        if row:
            return _to_professional(row)

    row = connection.execute(
        "SELECT * FROM professionals WHERE council_number = ? ORDER BY confirmations DESC",
        (council_number,),
    ).fetchone()
    return _to_professional(row) if row else None


def rank_by_name(connection: sqlite3.Connection, name: str, limit: int = MAX_SUGGESTIONS) -> list[tuple[Professional, float]]:
    """The closest names in the registry, best first — a shortlist, not an answer."""
    target = _collapse(name)
    if not target:
        return []

    scored = [
        (_to_professional(row), SequenceMatcher(None, target, row["normalised_name"]).ratio())
        for row in connection.execute("SELECT * FROM professionals")
    ]
    scored.sort(key=lambda item: -item[1])
    return [item for item in scored[:limit] if item[1] >= NAME_SUGGESTION_THRESHOLD]


def find_by_name(connection: sqlite3.Connection, name: str) -> tuple[Professional, float] | None:
    ranked = rank_by_name(connection, name, limit=1)
    return ranked[0] if ranked else None


def _is_near(left: str, right: str) -> bool:
    """Close enough that a single misread digit explains the difference."""
    if abs(len(left) - len(right)) > 1:
        return False
    return SequenceMatcher(None, left, right).ratio() >= NUMBER_NEIGHBOUR_RATIO


def resolve(
    connection: sqlite3.Connection,
    council_number: str | None,
    council_state: str | None,
    name: str | None,
) -> Match | None:
    """Finds who signed the guide, from whichever reading is trustworthy."""
    if council_number:
        exact = find_by_number(connection, council_number, council_state)
        if exact:
            return Match(exact, "registro encontrado no cadastro", 1.0, apply_automatically=True)

    if not name:
        return None

    by_name = find_by_name(connection, name)
    if not by_name:
        return None

    professional, score = by_name

    if council_number and professional.council_number != council_number:
        if _is_near(council_number, professional.council_number) and score >= NAME_CORROBORATION_THRESHOLD:
            return Match(
                professional,
                "nome e registro batem com o cadastro a menos de um dígito",
                score,
                apply_automatically=True,
                corrects_number=True,
            )
        return Match(
            professional,
            f"nome parecido no cadastro, mas o registro lido ({council_number}) diverge",
            score,
            apply_automatically=False,
        )

    return Match(
        professional,
        "nome parecido no cadastro; confirme antes de usar",
        score,
        apply_automatically=False,
    )
