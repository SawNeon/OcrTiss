from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.routes import store
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def uploaded(client, guide_pdf):
    with guide_pdf.open("rb") as handle:
        response = client.post("/api/extractions", files={"file": ("guia.pdf", handle, "application/pdf")})
    assert response.status_code == 200
    return response.json()


def test_health_reports_accepted_files(client):
    body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert ".pdf" in body["accepted_files"]
    assert ".jpg" in body["accepted_files"]


def test_upload_returns_fields_with_source_and_confidence(uploaded):
    payload = uploaded["payload"]
    read = [field for field in payload["fields"] if field["value"]]

    assert uploaded["id"]
    assert payload["strategy"] in {"template", "hybrid", "text_layer"}
    assert read, "nenhum campo lido"
    assert all(field["source"] for field in read)
    assert payload["summary"]["fields_read"] == len(read)


def test_upload_rejects_unsupported_type(client):
    response = client.post("/api/extractions", files={"file": ("guia.docx", b"conteudo", "application/msword")})
    assert response.status_code == 415


def test_upload_rejects_empty_file(client):
    response = client.post("/api/extractions", files={"file": ("guia.pdf", b"", "application/pdf")})
    assert response.status_code == 400


def test_correction_marks_the_field_as_human_and_leaves_an_audit_trail(client, uploaded):
    identifier = uploaded["id"]
    target = next(field["name"] for field in uploaded["payload"]["fields"] if field["value"])

    response = client.patch(f"/api/extractions/{identifier}/fields/{target}", json={"value": "99999"})
    body = response.json()
    field = next(item for item in body["payload"]["fields"] if item["name"] == target)

    assert response.status_code == 200
    assert field["value"] == "99999"
    assert field["source"] == "human"
    assert field["needs_review"] is False
    assert [entry["action"] for entry in body["audit"]] == ["extracted", "field_corrected"]


def test_correction_of_unknown_field_is_404(client, uploaded):
    response = client.patch(f"/api/extractions/{uploaded['id']}/fields/nao_existe", json={"value": "1"})
    assert response.status_code == 404


def test_decision_is_recorded(client, uploaded):
    response = client.post(
        f"/api/extractions/{uploaded['id']}/decision",
        json={"decision": "aprovado", "note": "conferido"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["payload"]["decision"]["status"] == "aprovado"
    assert body["audit"][-1]["action"] == "review_aprovado"


def test_page_image_is_returned_as_png(client, uploaded):
    response = client.get(f"/api/extractions/{uploaded['id']}/page.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content[:4] == b"\x89PNG"


def test_tiss_xml_carries_the_corrected_value(client, uploaded):
    identifier = uploaded["id"]
    client.patch(f"/api/extractions/{identifier}/fields/member_card_number", json={"value": "12345678901234567"})

    response = client.get(f"/api/extractions/{identifier}/tiss.xml")

    assert response.status_code == 200
    assert "12345678901234567" in response.text
    assert response.headers["content-disposition"].endswith('.xml"')


def test_unknown_extraction_is_404(client):
    assert client.get("/api/extractions/naoexiste").status_code == 404


def test_listing_includes_the_uploaded_guide(client, uploaded):
    listed = client.get("/api/extractions").json()
    assert any(item["id"] == uploaded["id"] for item in listed)
    assert store.get(uploaded["id"]) is not None
