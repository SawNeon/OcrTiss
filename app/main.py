"""FastAPI application: upload a guide (PDF or image) and get its fields back."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router, store
from app.recognition.catalogues import register_official_tables

WEB_BUILD = Path("web/dist")
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

@asynccontextmanager
async def lifespan(application: FastAPI):
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

app.include_router(router)

if WEB_BUILD.exists():
    app.mount("/assets", StaticFiles(directory=WEB_BUILD / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_BUILD / "index.html")
