"""Turns review work into data the tool can use.

Every correction and every approval is evidence: of which fields the reader gets
wrong, of which professionals exist, and of whether accuracy is moving. Nothing
here changes behaviour on its own — it accumulates the record that justifies a
change.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from app.learning.professionals import Professional, upsert

CORRECTED = "corrected"
CONFIRMED = "confirmed"
COUNCIL_FIELDS = ("council_number", "council_state", "professional_council")


@dataclass
class FieldAccuracy:
    field_name: str
    confirmed: int
    corrected: int

    @property
    def total(self) -> int:
        return self.confirmed + self.corrected

    @property
    def hit_rate(self) -> float:
        return self.confirmed / self.total if self.total else 0.0


def record_correction(
    connection: sqlite3.Connection,
    extraction_id: str,
    field_name: str,
    value_read: str | None,
    value_final: str | None,
    source: str | None,
    confidence: float | None,
) -> None:
    connection.execute(
        """
        INSERT INTO field_events (extraction_id, field_name, outcome, value_read,
                                  value_final, source, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (extraction_id, field_name, CORRECTED, value_read, value_final, source, confidence),
    )


def record_confirmation(
    connection: sqlite3.Connection,
    extraction_id: str,
    field_name: str,
    value: str | None,
    source: str | None,
    confidence: float | None,
) -> None:
    """The reviewer looked at the value and kept it: that is a hit, not a correction."""
    connection.execute(
        """
        INSERT INTO field_events (extraction_id, field_name, outcome, value_read,
                                  value_final, source, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (extraction_id, field_name, CONFIRMED, value, value, source, confidence),
    )


def record_approval(connection: sqlite3.Connection, extraction_id: str, fields: list[dict[str, Any]]) -> int:
    """An approved guide confirms every field the reviewer left untouched."""
    confirmed = 0
    for field in fields:
        if not field.get("value") or field.get("source") == "human":
            continue
        connection.execute(
            """
            INSERT INTO field_events (extraction_id, field_name, outcome, value_read,
                                      value_final, source, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                extraction_id,
                field["name"],
                CONFIRMED,
                field.get("value"),
                field.get("value"),
                field.get("source"),
                field.get("confidence"),
            ),
        )
        confirmed += 1
    return confirmed


def learn_professional(connection: sqlite3.Connection, fields: list[dict[str, Any]]) -> str | None:
    """Registers who signed an approved guide, so the next one is recognised."""
    values = {field["name"]: field.get("value") for field in fields}
    number = values.get("council_number")
    name = values.get("requesting_professional_name")

    if not number or not name:
        return None

    professional = Professional(
        council=values.get("professional_council") or "CRM",
        council_number=number,
        council_state=values.get("council_state"),
        full_name=name,
        specialty=values.get("professional_specialty"),
    )
    upsert(connection, professional, source="guia aprovada", confirm=True)
    return professional.label


def field_accuracy(connection: sqlite3.Connection, minimum: int = 1) -> list[FieldAccuracy]:
    rows = connection.execute(
        """
        SELECT field_name,
               SUM(outcome = ?) AS confirmed,
               SUM(outcome = ?) AS corrected
        FROM field_events
        GROUP BY field_name
        HAVING confirmed + corrected >= ?
        ORDER BY corrected DESC, field_name
        """,
        (CONFIRMED, CORRECTED, minimum),
    ).fetchall()

    return [
        FieldAccuracy(row["field_name"], int(row["confirmed"] or 0), int(row["corrected"] or 0))
        for row in rows
    ]


def common_mistakes(connection: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    """What the reader reads versus what the reviewer writes, most frequent first."""
    rows = connection.execute(
        """
        SELECT field_name, value_read, value_final, COUNT(*) AS occurrences
        FROM field_events
        WHERE outcome = ? AND value_read IS NOT NULL AND value_read <> ''
        GROUP BY field_name, value_read, value_final
        ORDER BY occurrences DESC
        LIMIT ?
        """,
        (CORRECTED, limit),
    ).fetchall()
    return [dict(row) for row in rows]
