import io

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from paper_sa.app import create_app


@pytest.fixture(autouse=True)
def isolate_workspace_preferences(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "paper_sa.workspaces.user_config_path", lambda *args, **kwargs: tmp_path / "preferences"
    )
    monkeypatch.delenv("PAPER_SA_HOME", raising=False)


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path)


@pytest.fixture
def client(app):
    with TestClient(app, base_url="http://127.0.0.1") as session:
        token = session.get("/api/bootstrap").json()["token"]
        session.headers["X-Paper-SA-Token"] = token
        yield session


@pytest.fixture
def pdf_bytes():
    output = io.BytesIO()
    document = canvas.Canvas(output)
    for number in range(1, 4):
        document.drawString(40, 740, f"Clinical trial page {number}. Randomized study of 120 adults.")
        document.drawString(
            40, 710, "Intervention versus placebo. Primary outcome was cardiovascular survival."
        )
        document.showPage()
    document.save()
    return output.getvalue()


@pytest.fixture
def paper(app):
    return app.state.store.upsert_paper(
        {
            "pmid": "33108101",
            "doi": "10.1056/NEJMoa2026834",
            "pmcid": "PMC7847551",
            "title": "Example medical study",
            "journal": "Example J Med",
            "year": "2020",
            "authors": ["Smith J", "Lee A"],
            "abstract": "A randomized study in 120 adults.",
            "article_url": "https://pubmed.ncbi.nlm.nih.gov/33108101/",
        }
    )
