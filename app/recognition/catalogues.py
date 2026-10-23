"""Official code tables used to validate what was read.

Each file is one code per line. Drop the real TISS/TUSS and CID-10 tables in
`data/` and they are picked up at startup; without them the reader still works,
it just cannot confirm that a code exists.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.recognition import decoder

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
PROCEDURE_TABLE = DATA_DIR / "tuss.txt"
ICD10_TABLE = DATA_DIR / "cid10.txt"
PROCEDURE_ROWS = 3


def _load(path: Path) -> set[str]:
    if not path.exists():
        return set()
    codes = {
        line.strip().upper()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    logger.info("tabela %s carregada com %d códigos", path.name, len(codes))
    return codes


def register_official_tables() -> dict[str, int]:
    """Points the decoder at whatever official tables are available on disk."""
    loaded: dict[str, int] = {}

    procedures = _load(PROCEDURE_TABLE)
    if procedures:
        for row in range(1, PROCEDURE_ROWS + 1):
            decoder.register_catalogue(f"procedure{row}_code", procedures)
        loaded["tuss"] = len(procedures)

    diagnoses = _load(ICD10_TABLE)
    if diagnoses:
        for field_name in ("main_icd10", "icd10_2", "icd10_3", "icd10_4"):
            decoder.register_catalogue(field_name, diagnoses)
        loaded["cid10"] = len(diagnoses)

    return loaded
