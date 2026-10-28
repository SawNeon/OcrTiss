from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def protected(monkeypatch):
    monkeypatch.setenv("AUTH_USER", "atendente")
    monkeypatch.setenv("AUTH_PASSWORD", "segredo")
    with TestClient(app) as client:
        yield client


def test_without_credentials_the_service_refuses(protected):
    resposta = protected.get("/api/extractions")

    assert resposta.status_code == 401
    assert "Basic" in resposta.headers["WWW-Authenticate"]


def test_health_stays_open_for_the_container_healthcheck(protected):
    assert protected.get("/api/health").status_code == 200


def test_wrong_password_is_refused(protected):
    assert protected.get("/api/extractions", auth=("atendente", "errada")).status_code == 401


def test_right_credentials_pass(protected):
    resposta = protected.get("/api/health", auth=("atendente", "segredo"))

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "ok"


def test_without_configuration_the_service_stays_open(monkeypatch):
    monkeypatch.delenv("AUTH_USER", raising=False)
    monkeypatch.delenv("AUTH_PASSWORD", raising=False)

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
