"""Imports the professionals spreadsheet into the registry.

Usage:
    python scripts/import_professionals.py data/profissionais.csv
    python scripts/import_professionals.py data/profissionais.xlsx --sheet Cooperados

Accepted column names (case and accent insensitive):
    nome / nome completo / profissional
    crm / registro / numero no conselho / conselho
    uf / estado
    especialidade
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.learning.database import DEFAULT_PATH, session
from app.learning.professionals import Professional, count, upsert

COLUMNS = {
    "name": (
        "nome", "nome completo", "profissional", "nome do profissional",
        "nome prestador", "prestador", "medico", "nome medico",
    ),
    "number": (
        "crm", "registro", "numero", "numero no conselho", "numero conselho",
        "registro conselho", "crm prestador",
    ),
    "state": ("uf", "estado", "uf conselho", "uf crm"),
    "specialty": ("especialidade", "especialidades", "area", "especialidade prestador"),
    "council": ("conselho", "tipo conselho"),
    "operator_code": ("codigo prestador", "codigo na operadora", "codigo operadora"),
}


def normalise_header(value: str) -> str:
    without_accents = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    spaced = without_accents.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", spaced.strip().lower())


def map_columns(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for header in headers:
        normalised = normalise_header(header or "")
        for field, options in COLUMNS.items():
            if field not in mapping and normalised in options:
                mapping[field] = header
    return mapping


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
        return list(csv.DictReader(handle, delimiter=delimiter))


def read_xlsx(path: Path, sheet: str | None) -> list[dict[str, str]]:
    try:
        from openpyxl import load_workbook
    except ImportError as error:  # pragma: no cover
        raise SystemExit("para ler .xlsx instale openpyxl, ou exporte a planilha como CSV") from error

    workbook = load_workbook(path, read_only=True, data_only=True)
    worksheet = workbook[sheet] if sheet else workbook.active
    rows = worksheet.iter_rows(values_only=True)

    headers = [str(cell) if cell is not None else "" for cell in next(rows)]
    return [
        {header: "" if value is None else str(value) for header, value in zip(headers, row, strict=False)}
        for row in rows
    ]


def clean_number(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("spreadsheet", type=Path)
    parser.add_argument("--sheet", help="aba da planilha, quando for .xlsx")
    parser.add_argument("--database", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--uf", help="UF do conselho, quando a planilha não traz a coluna")
    args = parser.parse_args()

    if not args.spreadsheet.exists():
        raise SystemExit(f"arquivo não encontrado: {args.spreadsheet}")

    rows = (
        read_xlsx(args.spreadsheet, args.sheet)
        if args.spreadsheet.suffix.lower() in {".xlsx", ".xlsm"}
        else read_csv(args.spreadsheet)
    )
    if not rows:
        raise SystemExit("planilha vazia")

    mapping = map_columns(list(rows[0].keys()))
    missing = {"name", "number"} - set(mapping)
    if missing:
        raise SystemExit(
            f"não encontrei as colunas {sorted(missing)}; cabeçalhos lidos: {list(rows[0].keys())}"
        )

    grouped: dict[tuple[str, str, str | None], Professional] = {}
    specialties: dict[tuple[str, str, str | None], list[str]] = {}
    skipped = 0

    for row in rows:
        name = (row.get(mapping["name"]) or "").strip()
        number = clean_number(row.get(mapping["number"]) or "")
        if not name or not number:
            skipped += 1
            continue

        council = (row.get(mapping.get("council", "")) or "CRM").strip().upper() or "CRM"
        state = (row.get(mapping.get("state", "")) or args.uf or "").strip().upper()[:2] or None
        key = (council, number, state)

        specialty = (row.get(mapping.get("specialty", "")) or "").strip()
        if specialty and specialty not in specialties.setdefault(key, []):
            specialties[key].append(specialty)

        grouped[key] = Professional(
            council=council,
            council_number=number,
            council_state=state,
            full_name=name,
            operator_code=(row.get(mapping.get("operator_code", "")) or "").strip() or None,
        )

    with session(args.database) as database:
        before = count(database)
        for key, professional in grouped.items():
            professional.specialty = "; ".join(specialties.get(key, [])) or None
            upsert(database, professional, source=f"planilha {args.spreadsheet.name}")
        after = count(database)

    imported = len(grouped)

    print(f"linhas lidas    : {len(rows)}")
    print(f"profissionais   : {imported} (linhas da mesma pessoa foram agrupadas)")
    print(f"ignoradas       : {skipped} (sem nome ou sem registro)")
    print(f"no cadastro     : {after} profissionais ({after - before} novos)")


if __name__ == "__main__":
    main()
