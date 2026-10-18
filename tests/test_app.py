import io
import json
import time
import zipfile
from unittest.mock import AsyncMock

import pytest
from pypdf import PdfReader


def wait_job(client, job_id):
    for _attempt in range(100):
        job = next(item for item in client.get("/api/jobs").json() if item["id"] == job_id)
        if job["status"] not in {"queued", "running", "waiting_user"}:
            return job
        time.sleep(0.02)
    raise AssertionError("Job did not finish")


def test_bootstrap_static_and_security(client):
    assert client.get("/").status_code == 200
    assert (
        client.get("/app.js")
        .headers["content-type"]
        .startswith(("text/javascript", "application/javascript"))
    )
    assert client.get("/api/health").json()["application"] == "paper-sa"
    assert client.get("/api/settings", headers={"X-Paper-SA-Token": ""}).status_code == 401
    assert client.get("/api/bootstrap", headers={"Origin": "https://attacker.example"}).status_code == 403
    assert client.get("/api/bootstrap", headers={"Host": "attacker.example"}).status_code == 403
    assert client.get("/api/bootstrap", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert "script-src 'self'" in client.get("/").headers["content-security-policy"]


def test_settings_encryption_redaction_and_target_change(client, app):
    saved = client.put(
        "/api/settings", json={"api_key": "test-secret-not-real", "ncbi_api_key": "ncbi-secret"}
    )
    assert saved.status_code == 200
    assert saved.json()["has_api_key"] is True
    assert "test-secret" not in saved.text
    assert "test-secret" not in app.state.config.path.read_text()
    assert "ncbi-secret" not in app.state.config.path.read_text()
    client.put("/api/settings", json={"api_key": "", "model": "another-model"})
    assert app.state.config.settings.api_key == "test-secret-not-real"
    client.put("/api/settings", json={"base_url": "https://different.example/v1", "api_key": ""})
    assert app.state.config.settings.api_key == ""
    assert client.put("/api/settings", json={"base_url": "http://remote.example/v1"}).status_code == 422
    assert client.put("/api/settings", json={"cdp_url": "http://remote.example:9222"}).status_code == 422


def test_settings_bad_types_do_not_echo_secret(client):
    response = client.put("/api/settings", json={"api_key": ["sensitive"]})
    assert response.status_code == 422
    assert "sensitive" not in response.text


def test_upload_pdf_and_page_range(client, app, paper, pdf_bytes):
    response = client.post(
        "/api/papers/upload",
        data={"paper_id": paper["id"]},
        files={"file": ("paper.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    uploaded = response.json()
    assert uploaded["has_pdf"] and uploaded["page_count"] == 3
    assert uploaded["text_status"] == "fulltext"
    assert len(app.state.store.pages(paper["id"])) == 3
    pdf = client.get(f"/api/papers/{paper['id']}/pdf")
    assert pdf.content.startswith(b"%PDF-")
    ranged = client.get(f"/api/papers/{paper['id']}/pdf", headers={"Range": "bytes=0-4"})
    assert ranged.status_code == 206
    assert ranged.content == b"%PDF-"
    assert (
        client.post(
            "/api/papers/upload", data={"paper_id": paper["id"]}, files={"file": ("other.pdf", pdf_bytes)}
        ).status_code
        == 409
    )


def test_bad_pdf_not_archived(client, app):
    response = client.post("/api/papers/upload", files={"file": ("fake.pdf", b"<html>Login</html>")})
    assert response.status_code == 502
    assert client.get("/api/papers").json() == []
    assert list((app.state.config.root / "staging").iterdir()) == []
    assert list((app.state.config.root / "papers").iterdir()) == []


def test_new_local_pdf(client, pdf_bytes):
    paper = client.post("/api/papers/upload", files={"file": ("Local study.pdf", pdf_bytes)}).json()
    assert paper["metadata"]["title"] == "Local study"
    assert paper["pmid"] is None
    assert client.post("/api/snowball", json={"paper_ids": [paper["id"]]}).status_code == 422


def test_notes_revision_and_exports(client, paper):
    content = (
        "# 医学文献笔记\n\n研究结果需要核验。\n\n| 指标 | 结果 |\n| --- | --- |\n| 样本量 | 120 |\n\n- 局限性"
    )
    note = client.post(
        "/api/notes", json={"title": "研究笔记", "content": content, "paper_id": paper["id"]}
    ).json()
    updated = client.put(
        "/api/notes/" + note["id"], json={"title": "新标题", "content": content, "revision": 1}
    )
    assert updated.json()["revision"] == 2
    assert (
        client.put(
            "/api/notes/" + note["id"], json={"title": "冲突", "content": "", "revision": 1}
        ).status_code
        == 409
    )
    assert client.get(f"/api/notes/{note['id']}/export?format=md").content.decode() == content
    pdf = client.get(f"/api/notes/{note['id']}/export?format=pdf")
    assert pdf.status_code == 200
    assert len(PdfReader(io.BytesIO(pdf.content)).pages) >= 1
    assert "医学文献" in PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()
    word = client.get(f"/api/notes/{note['id']}/export?format=docx")
    with zipfile.ZipFile(io.BytesIO(word.content)) as archive:
        xml = archive.read("word/document.xml").decode()
    assert "研究结果需要核验" in xml
    assert "<w:tbl>" in xml
    assert client.get(f"/api/notes/{note['id']}/export?format=exe").status_code == 422


def test_markdown_rejects_executable_html(client):
    html = client.post(
        "/api/markdown", json={"content": "<script>alert(1)</script>\n\n[bad](javascript:alert(1))"}
    ).json()["html"]
    assert "<script>" not in html
    assert 'href="javascript:' not in html


def test_search_persists_deduplicates_and_records_query(client, app, paper):
    app.state.pubmed.search = AsyncMock(
        return_value={
            "query": "trial",
            "translation": "trial[All Fields]",
            "total": 1,
            "warnings": {},
            "papers": [paper["metadata"]],
        }
    )
    for _attempt in range(2):
        result = client.post("/api/search", json={"query": "trial"})
        assert result.status_code == 200
    assert len(client.get("/api/papers").json()) == 1
    history = client.get("/api/search/history").json()
    assert len(history) == 2
    assert json.loads(history[0]["details"])["translation"] == "trial[All Fields]"


def test_invalid_search_years(client):
    assert (
        client.post("/api/search", json={"query": "trial", "year_from": 2025, "year_to": 2020}).status_code
        == 422
    )
    assert client.post("/api/search", json={"query": "  "}).status_code == 422


def test_chat_evidence_and_persisted_messages(client, app, paper):
    app.state.llm.complete = AsyncMock(return_value="研究设计需要核对全文。[P1 · 摘要]")
    response = client.post(f"/api/papers/{paper['id']}/chat", json={"summarize": True})
    assert response.status_code == 200
    assert "仅摘要" in response.json()["scope"]
    assert len(client.get(f"/api/papers/{paper['id']}/messages").json()) == 2
    assert "A randomized study" in app.state.llm.complete.call_args.args[0]
    assert client.post(f"/api/papers/{paper['id']}/chat", json={"question": ""}).status_code == 422


@pytest.mark.parametrize("summarize", [True, False])
def test_reading_chat_requests_verbatim_original_passages(client, app, paper, summarize):
    from paper_sa.llm import READING_SYSTEM

    answer = (
        "> **论文原文** [P1 · 摘要]\n>\n> A randomized study in 120 adults.\n\n**解读**：摘要报告了研究人群。"
    )
    app.state.llm.complete = AsyncMock(return_value=answer)
    response = client.post(
        f"/api/papers/{paper['id']}/chat",
        json={"question": "请引用原文解释研究人群", "summarize": summarize},
    )
    assert response.status_code == 200
    assert response.json()["answer"] == answer
    assert app.state.llm.complete.call_args.kwargs["system"] == READING_SYSTEM
    assert "原文保持原语言、数字和限定条件" in READING_SYSTEM
    assert "无法在当前提供的证据中找到" in READING_SYSTEM
    messages = client.get(f"/api/papers/{paper['id']}/messages").json()
    assert messages[-1]["content"] == answer


def test_multiple_reading_notes_stay_linked_and_independent(client, paper):
    first = client.post(
        "/api/notes", json={"title": "方法笔记", "content": "原有想法", "paper_id": paper["id"]}
    ).json()
    second = client.post(
        "/api/notes", json={"title": "结果笔记", "content": "结果摘录", "paper_id": paper["id"]}
    ).json()
    excerpt = "> 选中的对话文字\n\n**来源**：Example medical study"
    updated = client.put(
        "/api/notes/" + first["id"],
        json={"title": first["title"], "content": first["content"] + "\n\n" + excerpt, "revision": 1},
    )
    assert updated.status_code == 200
    assert client.get("/api/notes/" + second["id"]).json()["content"] == "结果摘录"
    notes = client.get("/api/notes", params={"paper_id": paper["id"]}).json()
    assert {note["id"] for note in notes} == {first["id"], second["id"]}
    assert client.get(f"/api/notes/{first['id']}/export?format=md").text.endswith(excerpt)


def test_model_missing_key_does_not_create_messages(client, paper):
    response = client.post(f"/api/papers/{paper['id']}/chat", json={"question": "研究结果？"})
    assert response.status_code == 502
    assert client.get(f"/api/papers/{paper['id']}/messages").json() == []


def test_snowball_bfs_dedup_and_edge_provenance(client, app, paper):
    metadata = dict(paper["metadata"], pmid="33108102", doi="10.1000/other", title="Related study")
    app.state.pubmed.neighbors = AsyncMock(return_value=[metadata, metadata, paper["metadata"]])
    job = client.post("/api/snowball", json={"paper_ids": [paper["id"]], "depth": 2, "max_papers": 3}).json()
    result = wait_job(client, job["id"])
    assert result["status"] == "completed"
    assert len(result["result"]["paper_ids"]) == 1
    graph = client.get("/api/graph").json()
    assert len(graph["nodes"]) == 2
    assert {edge["relation"] for edge in graph["edges"]} == {"similar", "references", "cited_by"}
    assert all(edge["source"] != edge["target"] for edge in graph["edges"])


def test_download_skips_existing_pdf(client, app, paper, pdf_bytes):
    client.post(
        "/api/papers/upload", data={"paper_id": paper["id"]}, files={"file": ("paper.pdf", pdf_bytes)}
    )
    app.state.pubmed.routes = AsyncMock()
    job = client.post("/api/downloads", json={"paper_ids": [paper["id"]]}).json()
    result = wait_job(client, job["id"])
    assert result["status"] == "completed"
    assert result["result"]["papers"][0]["status"] == "existing"
    app.state.pubmed.routes.assert_not_called()


def test_failed_download_requires_user_not_false_success(client, app, paper):
    app.state.pubmed.routes = AsyncMock(return_value=[])
    job = client.post("/api/downloads", json={"paper_ids": [paper["id"]]}).json()
    result = wait_job(client, job["id"])
    assert result["status"] == "needs_action"
    assert not app.state.store.paper(paper["id"])["has_pdf"]


def test_report_real_selection_and_evidence_cards(client, app, paper):
    second = app.state.store.upsert_paper(
        dict(paper["metadata"], pmid="33108102", doi="10.1000/second", title="Second trial")
    )
    app.state.llm.complete = AsyncMock(
        side_effect=[
            "Evidence card 1 [P1 · 摘要]",
            "Evidence card 2 [P2 · 摘要]",
            "## 比较\n\n设计有所不同 [P1] [P2]",
        ]
    )
    job = client.post(
        "/api/reports", json={"paper_ids": [paper["id"], second["id"]], "topic": "临床获益"}
    ).json()
    result = wait_job(client, job["id"])
    assert result["status"] == "completed"
    note = client.get("/api/notes/" + result["result"]["note_id"]).json()
    assert note["kind"] == "report"
    assert "Second trial" in note["content"]
    assert "叙述性综述初稿" in note["content"]
    assert len(note["metadata"]["sources"]) == 2
    assert app.state.llm.complete.call_count == 3


@pytest.mark.parametrize(
    "payload",
    [
        {"paper_ids": ["missing"], "topic": "test"},
        {"paper_ids": ["same", "same"], "topic": "test"},
    ],
)
def test_report_selection_validation(client, payload):
    assert client.post("/api/reports", json=payload).status_code == 422


def test_api_missing_resources(client):
    for path in ["/papers/missing", "/notes/missing", "/papers/missing/messages"]:
        assert client.get("/api" + path).status_code == 404
    assert client.post("/api/downloads", json={"paper_ids": ["missing"]}).status_code == 404
