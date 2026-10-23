from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from app.extraction.triage import strip_print_artifacts
from app.schemas.guide import ExtractedField, FieldSource, Procedure, SpSadtGuide

TISS_LABELS: dict[str, str] = {
    "no guia no prestador": "provider_guide_number",
    "no guia principal": "main_guide_number",
    "registro ans": "ans_registration",
    "numero da guia atribuido pela operadora": "operator_guide_number",
    "data da autorizacao": "authorization_date",
    "senha": "password",
    "data de validade da senha": "password_expiry_date",
    "numero da carteira": "member_card_number",
    "validade da carteira": "card_expiry_date",
    "nome social": "member_social_name",
    "nome": "member_name",
    "atendimento a rn": "newborn_care",
    "codigo na operadora": "requester_operator_code",
    "nome do contratado": "requester_provider_name",
    "nome do profissional solicitante": "requesting_professional_name",
    "conselho profissional": "professional_council",
    "numero no conselho": "council_number",
    "uf": "council_state",
    "codigo cbo": "cbo_code",
    "carater do atendimento": "care_type",
    "data da solicitacao": "request_date",
    "indicacao clinica": "clinical_indication",
    "codigo cnes": "cnes_code",
    "tipo de consulta": "consultation_type",
}

LABEL_START = re.compile(r"^\s*(\d{1,2})\s*-\s*(.*)$")
INLINE_LABEL = re.compile(r"\d{1,2}\s*-\s*[A-Za-zÀ-ÿ]")
PROCEDURE_ROW = re.compile(
    r"^\s*\d+\s*-\s*(\d{2})\s+(\d{6,10})\s+(.+?)\s{2,}([\d.,]+)\s+([\d.,]+)\s*$"
)
BLANK_VALUE = re.compile(r"^[\s/_.-]*$")

PROCEDURE_TABLE_HEADER = "codigo do procedimento"
PROCEDURE_TABLE_END = "dados do contratado executante"
SECTION_PREFIX = "dados d"


def normalize(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", " ", ascii_text.lower()).strip()


def _clean_value(raw: str) -> str | None:
    value = re.sub(r"\s{2,}", " ", raw).strip()
    return None if not value or BLANK_VALUE.match(value) else value


def _as_field(value: str | None) -> ExtractedField | None:
    if value is None:
        return None
    return ExtractedField(value=value, source=FieldSource.TEXT_LAYER, confidence=1.0)


def _procedure_table_bounds(lines: list[str]) -> tuple[int, int]:
    start = end = -1
    for index, line in enumerate(lines):
        normalized = normalize(line)
        if start == -1 and PROCEDURE_TABLE_HEADER in normalized:
            start = index + 1
        elif start != -1 and PROCEDURE_TABLE_END in normalized:
            end = index
            break
    if start == -1:
        return (-1, -1)
    return (start, end if end != -1 else len(lines))


def _split_label_from_value(text: str, label: str) -> str | None:
    """Consumes the label word by word; normalization changes string length."""
    words = text.split()
    for count in range(1, len(words) + 1):
        if normalize(" ".join(words[:count])) == label:
            return " ".join(words[count:]).strip()
    return None


def _match_label(lines: list[str], index: int) -> tuple[str, str, int] | None:
    match = LABEL_START.match(lines[index])
    if not match:
        return None
    remainder = match.group(2)

    labels = sorted(TISS_LABELS.items(), key=lambda item: -len(item[0]))

    for extra_lines in (0, 1):
        label_text = remainder
        if extra_lines:
            if index + extra_lines >= len(lines):
                continue
            next_line = lines[index + extra_lines].strip()
            if not next_line or LABEL_START.match(next_line):
                continue
            label_text = f"{remainder} {next_line}"

        normalized = normalize(label_text)
        for label, field_name in labels:
            if normalized != label and not normalized.startswith(label + " "):
                continue
            value = "" if normalized == label else _split_label_from_value(label_text, label)
            if value is None:
                continue
            return field_name, value, 1 + extra_lines
    return None


def _collect_values(lines: list[str], table_start: int, table_end: int) -> dict[str, str]:
    values: dict[str, str] = {}
    index = 0

    while index < len(lines):
        if table_start <= index < table_end:
            index += 1
            continue

        # a header line holding several labels makes the value below ambiguous
        if len(INLINE_LABEL.findall(lines[index])) > 1:
            index += 1
            continue

        match = _match_label(lines, index)
        if not match:
            index += 1
            continue

        field_name, remainder, consumed_lines = match
        value = _clean_value(remainder)

        next_index = index + consumed_lines
        while value is None and next_index < len(lines):
            line = lines[next_index]
            if LABEL_START.match(line) or normalize(line).startswith(SECTION_PREFIX):
                break
            value = _clean_value(line)
            next_index += 1

        if value and field_name not in values:
            values[field_name] = value
        index = max(next_index, index + consumed_lines)

    return values


def _collect_procedures(lines: list[str], table_start: int, table_end: int) -> list[Procedure]:
    procedures: list[Procedure] = []
    if table_start == -1:
        return procedures

    for line in lines[table_start:table_end]:
        row = PROCEDURE_ROW.match(line)
        if not row:
            continue
        table, code, description, requested, authorized = row.groups()
        procedures.append(
            Procedure(
                table=_as_field(table),
                code=_as_field(code),
                description=_as_field(_clean_value(description)),
                requested_quantity=_as_field(requested),
                authorized_quantity=_as_field(authorized),
            )
        )
    return procedures


def extract_from_text(text: str) -> SpSadtGuide:
    lines = [line.rstrip() for line in text.splitlines()]
    table_start, table_end = _procedure_table_bounds(lines)

    values = _collect_values(lines, table_start, table_end)
    guide = SpSadtGuide(**{name: _as_field(value) for name, value in values.items()})
    guide.procedures = _collect_procedures(lines, table_start, table_end)
    return guide


def extract_from_pdf(pdf_path: str | Path, page_number: int = 1) -> SpSadtGuide:
    reader = PdfReader(Path(pdf_path))
    text = reader.pages[page_number - 1].extract_text() or ""
    return extract_from_text(strip_print_artifacts(text))
