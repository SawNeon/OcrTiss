"""In-memory registry of extractions, with the uploaded files kept on disk.

Deliberately not a database: this is the demonstration backend. Persistence,
the Caso entity and the real audit trail come with the production backlog.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.schemas.guide import SpSadtGuide

WORK_DIR = Path("var/uploads")
RETENTION_HOURS = 24

logger = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    at: str
    action: str
    field_name: str | None = None
    previous: str | None = None
    current: str | None = None
    author: str = "demo"


@dataclass
class Extraction:
    identifier: str
    original_name: str
    pdf_path: Path
    page_count: int
    payload: dict[str, Any]
    guide: SpSadtGuide | None
    created_at: str
    audit: list[AuditEntry] = field(default_factory=list)


class ExtractionStore:
    def __init__(self, folder: Path = WORK_DIR) -> None:
        self._folder = folder
        self._items: dict[str, Extraction] = {}

    def discard_old_files(self, retention_hours: int = RETENTION_HOURS) -> int:
        """Uploads are working copies: keeping them forever fills the disk and the
        documents carry health data, so anything past the window goes."""
        if not self._folder.exists():
            return 0

        deadline = time.time() - retention_hours * 3600
        removed = 0
        for path in self._folder.iterdir():
            if path.is_file() and path.stat().st_mtime < deadline:
                path.unlink(missing_ok=True)
                removed += 1

        if removed:
            logger.info("removidos %d arquivos de upload com mais de %dh", removed, retention_hours)
        return removed

    @property
    def folder(self) -> Path:
        return self._folder

    def add(
        self,
        original_name: str,
        pdf_path: Path,
        page_count: int,
        payload: dict[str, Any],
        guide: SpSadtGuide | None,
    ) -> Extraction:
        identifier = uuid.uuid4().hex[:12]
        extraction = Extraction(
            identifier=identifier,
            original_name=original_name,
            pdf_path=pdf_path,
            page_count=page_count,
            payload=payload,
            guide=guide,
            created_at=datetime.now().isoformat(timespec="seconds"),
            audit=[AuditEntry(at=datetime.now().isoformat(timespec="seconds"), action="extracted")],
        )
        self._items[identifier] = extraction
        return extraction

    def get(self, identifier: str) -> Extraction | None:
        return self._items.get(identifier)

    def list(self) -> list[Extraction]:
        return sorted(self._items.values(), key=lambda item: item.created_at, reverse=True)

    def record(self, extraction: Extraction, entry: AuditEntry) -> None:
        extraction.audit.append(entry)
