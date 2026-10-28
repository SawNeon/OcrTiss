"""FastAPI application: upload a guide (PDF or image) and get its fields back."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import public_router, router, store
from app.api.security import require_access, warn_if_open
from app.extraction.template_reader import CharacterModelMissing, load_classifier
from app.recognition.catalogues import register_official_tables

logger = logging.getLogger(__name__)

# O uvicorn configura só os próprios loggers: sem isto, os avisos do serviço
# (leitor indisponível, acesso aberto) não chegam ao `docker compose logs`.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

WEB_BUILD = Path("web/dist")
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

def _check_reader() -> bool:
    """Falha de modelo aparece no start, não na primeira guia do atendente."""
    try:
        load_classifier()
    except (CharacterModelMissing, Exception) as error:
        logger.error("leitor local indisponível: %s", error)
        return False
    logger.info("leitor local pronto")
    return True


@asynccontextmanager
async def lifespan(application: FastAPI):
    warn_if_open()
    application.state.reader_ready = _check_reader()
    application.state.catalogues = register_official_tables()
    store.discard_old_files()
    yield


app = FastAPI(
    title="TISS OCR",
    description="Leitura de guias médicas em PDF ou imagem, com extração estruturada dos campos.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(public_router)
app.include_router(router, dependencies=[Depends(require_access)])

if WEB_BUILD.exists():
    app.mount("/assets", StaticFiles(directory=WEB_BUILD / "assets"), name="assets")

    @app.get("/")
    def index(_: str = Depends(require_access)) -> FileResponse:
        return FileResponse(WEB_BUILD / "index.html")
