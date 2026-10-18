import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from paper_sa.app import create_app
from paper_sa.config import Config
from paper_sa.workspaces import WorkspaceLock, WorkspaceRegistry


@pytest.fixture
def destination(tmp_path_factory):
    return tmp_path_factory.mktemp("研究 空间")


def switch(client, path):
    response = client.post("/api/workspace/switch", json={"path": str(path)})
    assert response.status_code == 200, response.text
    client.headers["X-Paper-SA-Token"] = response.json()["token"]
    return response.json()


def test_switch_round_trip_preserves_private_workspace_data(client, app, paper, pdf_bytes, destination):
    original = app.state.config.root
    original_id = app.state.config.workspace_id
    original_token = client.headers["X-Paper-SA-Token"]
    client.put("/api/settings", json={"api_key": "workspace-a-secret", "auto_summarize": False})
    note = client.post(
        "/api/notes", json={"title": "A 的笔记", "content": "重要内容", "paper_id": paper["id"]}
    ).json()
    app.state.store.add_message(paper["id"], "assistant", "A 的回答", "摘要")
    assert (
        client.post(
            "/api/papers/upload", data={"paper_id": paper["id"]}, files={"file": ("paper.pdf", pdf_bytes)}
        ).status_code
        == 200
    )

    result = switch(client, destination)
    assert result["token"] != original_token
    settings = client.get("/api/settings").json()
    assert settings["data_dir"] == str(destination)
    assert settings["has_api_key"] is False
    assert settings["workspace"]["recent"] == [str(destination), str(original)]
    assert client.get("/api/papers").json() == []
    assert client.get("/api/notes").json() == []
    assert (
        client.post(
            "/api/notes", json={"title": "旧页面误写"}, headers={"X-Paper-SA-Token": original_token}
        ).status_code
        == 401
    )
    assert client.get(f"/api/papers/{paper['id']}/pdf?workspace_id={original_id}").status_code == 409
    other_note = client.post("/api/notes", json={"title": "B 的笔记", "content": "独立内容"}).json()

    switch(client, original)
    assert client.get("/api/settings").json()["has_api_key"] is True
    assert client.get(f"/api/notes/{note['id']}").json()["content"] == "重要内容"
    assert client.get(f"/api/notes/{other_note['id']}").status_code == 404
    assert client.get(f"/api/papers/{paper['id']}/messages").json()[0]["content"] == "A 的回答"
    assert client.get(f"/api/papers/{paper['id']}/pdf?workspace_id={original_id}").content == pdf_bytes
    switch(client, destination)
    assert client.get(f"/api/notes/{other_note['id']}").json()["content"] == "独立内容"


def test_same_workspace_retains_session_and_sets_default(client, app):
    previous = client.headers["X-Paper-SA-Token"]
    assert switch(client, app.state.config.root)["token"] == previous
    assert app.state.registry.startup_path() == app.state.config.root


def test_restart_uses_remembered_workspace(tmp_path, destination):
    preferences = tmp_path / "preferences.json"
    with TestClient(
        create_app(tmp_path / "original", preferences_path=preferences), base_url="http://127.0.0.1"
    ) as first:
        first.headers["X-Paper-SA-Token"] = first.get("/api/bootstrap").json()["token"]
        switch(first, destination)
        first.post("/api/notes", json={"title": "重启后保留"})
    restarted = create_app(preferences_path=preferences)
    with TestClient(restarted, base_url="http://127.0.0.1") as second:
        second.headers["X-Paper-SA-Token"] = second.get("/api/bootstrap").json()["token"]
        assert second.get("/api/settings").json()["data_dir"] == str(destination)
        assert second.get("/api/notes").json()[0]["title"] == "重启后保留"


def test_explicit_and_environment_override_remembered_workspace(tmp_path, destination, monkeypatch):
    registry = WorkspaceRegistry(tmp_path / "preferences.json")
    registry.remember(destination)
    assert registry.startup_path() == destination
    monkeypatch.setenv("PAPER_SA_HOME", str(tmp_path / "environment"))
    assert registry.startup_path() == tmp_path / "environment"
    assert registry.startup_path(tmp_path / "explicit") == tmp_path / "explicit"


@pytest.mark.parametrize("invalid", ["   ", "relative/path", "bad\x00path"])
def test_switch_rejects_invalid_path(client, app, invalid):
    original = app.state.config.root
    assert client.post("/api/workspace/switch", json={"path": invalid}).status_code == 422
    assert app.state.config.root == original


@pytest.mark.parametrize(
    "kind", ["file", "nonempty", "broken_database", "broken_settings", "child", "parent"]
)
def test_switch_rejects_unsafe_or_broken_target(client, app, destination, kind):
    original = app.state.config.root
    target = destination
    if kind == "file":
        target = destination / "file.txt"
        target.write_text("keep me", encoding="utf-8")
    elif kind == "nonempty":
        (target / "unrelated.txt").write_text("keep me", encoding="utf-8")
    elif kind == "broken_database":
        (target / "workspace.sqlite3").write_bytes(b"not a sqlite database")
        (target / ".secret.key").write_text("invalid", encoding="utf-8")
    elif kind == "broken_settings":
        with TestClient(create_app(target)):
            pass
        (target / "settings.json").write_text(json.dumps({"api_key": "not-encrypted"}), encoding="utf-8")
    elif kind == "child":
        target = original / "nested"
    else:
        target = original.parent
    assert client.post("/api/workspace/switch", json={"path": str(target)}).status_code == 422
    assert app.state.config.root == original
    assert client.get("/api/notes").status_code == 200
    if kind == "nonempty":
        assert list(target.iterdir()) == [target / "unrelated.txt"]


def test_switch_blocks_active_jobs(client, app, destination):
    app.state.agents.tasks["test-active"] = object()
    try:
        assert client.post("/api/workspace/switch", json={"path": str(destination)}).status_code == 409
        assert not (destination / "workspace.sqlite3").exists()
    finally:
        app.state.agents.tasks.clear()


def test_switch_blocks_inflight_search(client, app, destination):
    started, release = threading.Event(), threading.Event()

    async def slow_search(*args):
        started.set()
        while not release.is_set():
            await asyncio.sleep(0.01)
        return {"papers": [], "query": "test", "translation": "test", "total": 0}

    app.state.pubmed.search = slow_search
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(client.post, "/api/search", json={"query": "test"})
        try:
            assert started.wait(5)
            assert client.post("/api/workspace/switch", json={"path": str(destination)}).status_code == 409
        finally:
            release.set()
        assert pending.result(timeout=5).status_code == 200
    switch(client, destination)


def test_switch_rejects_workspace_used_by_another_instance(client, app, destination):
    original = app.state.config.root
    with TestClient(create_app(destination)):
        response = client.post("/api/workspace/switch", json={"path": str(destination)})
        assert response.status_code == 422
        assert "占用" in response.json()["detail"]
        assert app.state.config.root == original
    switch(client, destination)


def test_preference_failure_keeps_original_workspace_and_releases_target(
    client, app, destination, monkeypatch
):
    original = app.state.config.root

    def fail(*args):
        raise PermissionError("read-only preferences")

    monkeypatch.setattr(app.state.registry, "remember", fail)
    assert client.post("/api/workspace/switch", json={"path": str(destination)}).status_code == 422
    assert app.state.config.root == original
    assert client.post("/api/notes", json={"title": "原目录仍可写"}).status_code == 200
    lease = WorkspaceLock(destination)
    lease.close()


def test_copied_workspaces_have_distinct_draft_ids(tmp_path, destination):
    assert Config(tmp_path).workspace_id != Config(destination).workspace_id


def test_switch_blocks_requests_while_closing_previous_browser(client, app, destination):
    started, release = threading.Event(), threading.Event()
    close = app.state.browser.close

    async def slow_close():
        started.set()
        while not release.is_set():
            await asyncio.sleep(0.01)
        await close()

    app.state.browser.close = slow_close
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(client.post, "/api/workspace/switch", json={"path": str(destination)})
        try:
            assert started.wait(5)
            assert client.get("/api/bootstrap").status_code == 409
            assert client.post("/api/notes", json={"title": "旧会话"}).status_code == 401
        finally:
            release.set()
        response = pending.result(timeout=5)
    assert response.status_code == 200
    client.headers["X-Paper-SA-Token"] = response.json()["token"]
    assert client.get("/api/notes").json() == []
