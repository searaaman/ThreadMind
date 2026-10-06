import asyncio
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient


class FakeLLM:
    configured = True

    def __init__(self):
        self.calls = []
        self.fail = False

    async def stream_reply(self, history, memories):
        self.calls.append({"history": history, "memories": memories})
        if self.fail:
            raise RuntimeError("model unavailable")
        for word in ["Hello", " there", "!"]:
            yield word

    async def generate_title(self, message):
        return "Greeting chat"

    async def extract_memories(self, known, user_message, assistant_message):
        return ["User's name is Asha."] if "Asha" in user_message else []


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("THREADMIND_DB", str(tmp_path / "test.db"))
    import importlib

    import database
    import main

    importlib.reload(database)
    importlib.reload(main)
    fake = FakeLLM()
    main.app.dependency_overrides[main.get_llm] = lambda: fake
    with TestClient(main.app, headers={"X-User-Id": "alice"}) as client:
        yield client, fake, database


def events(response):
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_requires_user_header(setup):
    client, _, _ = setup
    assert client.get("/api/threads", headers={"X-User-Id": ""}).status_code == 422


def test_full_conversation_flow(setup):
    client, fake, _ = setup
    thread = client.post("/api/threads", json={}).json()
    assert thread["title"] == "New chat"

    res = client.post(f"/api/threads/{thread['id']}/messages", json={"content": "Hi, I'm Asha"})
    evts = events(res)
    assert evts[0]["type"] == "user"
    assert "".join(e["text"] for e in evts if e["type"] == "delta") == "Hello there!"
    done = evts[-1]
    assert done["type"] == "done"
    assert done["message"]["content"] == "Hello there!"
    assert done["thread"]["title"] == "Greeting chat"

    detail = client.get(f"/api/threads/{thread['id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]

    # Second turn sends the whole thread history to the model.
    client.post(f"/api/threads/{thread['id']}/messages", json={"content": "And again"})
    assert [m["content"] for m in fake.calls[-1]["history"]] == ["Hi, I'm Asha", "Hello there!", "And again"]


def test_memory_shared_across_threads(setup):
    client, fake, _ = setup
    t1 = client.post("/api/threads", json={}).json()
    client.post(f"/api/threads/{t1['id']}/messages", json={"content": "I'm Asha"})

    # Memory extraction runs as a background task; give it a moment.
    for _ in range(50):
        if client.get("/api/memories").json():
            break
        asyncio.run(asyncio.sleep(0.01))
    assert [m["content"] for m in client.get("/api/memories").json()] == ["User's name is Asha."]

    t2 = client.post("/api/threads", json={}).json()
    client.post(f"/api/threads/{t2['id']}/messages", json={"content": "What's my name?"})
    assert fake.calls[-1]["memories"] == ["User's name is Asha."]
    assert [m["content"] for m in fake.calls[-1]["history"]] == ["What's my name?"]


def test_memory_crud(setup):
    client, _, _ = setup
    m = client.post("/api/memories", json={"content": "Likes Go"}).json()
    client.post("/api/memories", json={"content": "Lives in Kochi"})
    assert len(client.get("/api/memories").json()) == 2
    assert client.delete(f"/api/memories/{m['id']}").status_code == 204
    assert client.delete(f"/api/memories/{m['id']}").status_code == 404
    client.delete("/api/memories")
    assert client.get("/api/memories").json() == []


def test_threads_are_private_per_user(setup):
    client, _, _ = setup
    thread = client.post("/api/threads", json={}).json()
    bob = {"X-User-Id": "bob"}
    assert client.get("/api/threads", headers=bob).json() == []
    assert client.get(f"/api/threads/{thread['id']}", headers=bob).status_code == 404
    assert client.delete(f"/api/threads/{thread['id']}", headers=bob).status_code == 404


def test_rename_and_delete(setup):
    client, _, _ = setup
    thread = client.post("/api/threads", json={}).json()
    assert client.patch(f"/api/threads/{thread['id']}", json={"title": "Trip plans"}).json()["title"] == "Trip plans"
    assert client.delete(f"/api/threads/{thread['id']}").status_code == 204
    assert client.get("/api/threads").json() == []


def test_regenerate_replaces_last_reply(setup):
    client, fake, _ = setup
    thread = client.post("/api/threads", json={}).json()
    client.post(f"/api/threads/{thread['id']}/messages", json={"content": "Hi"})
    evts = events(client.post(f"/api/threads/{thread['id']}/regenerate"))
    assert evts[-1]["type"] == "done"
    messages = client.get(f"/api/threads/{thread['id']}").json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert [m["content"] for m in fake.calls[-1]["history"]] == ["Hi"]


def test_llm_error_is_reported_and_retryable(setup):
    client, fake, _ = setup
    thread = client.post("/api/threads", json={}).json()
    fake.fail = True
    evts = events(client.post(f"/api/threads/{thread['id']}/messages", json={"content": "Hi"}))
    assert evts[-1] == {"type": "error", "error": "model unavailable"}
    # The user message is kept so it can be retried.
    assert [m["role"] for m in client.get(f"/api/threads/{thread['id']}").json()["messages"]] == ["user"]
    fake.fail = False
    assert events(client.post(f"/api/threads/{thread['id']}/regenerate"))[-1]["type"] == "done"


def test_empty_message_rejected(setup):
    client, _, _ = setup
    thread = client.post("/api/threads", json={}).json()
    assert client.post(f"/api/threads/{thread['id']}/messages", json={"content": "   "}).status_code == 422


def test_legacy_conversations_migrated(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE conversations (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, role TEXT, message TEXT)")
    conn.executemany(
        "INSERT INTO conversations (user_id, role, message) VALUES (?, ?, ?)",
        [("u1", "User", "hello"), ("u1", "AI", "hi!")],
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("THREADMIND_DB", str(path))
    import importlib

    import database

    importlib.reload(database)
    database.init_db()
    threads = database.list_threads("u1")
    assert len(threads) == 1
    assert [(m["role"], m["content"]) for m in database.get_messages(threads[0]["id"])] == [
        ("user", "hello"),
        ("assistant", "hi!"),
    ]


def test_ui_served(setup):
    client, _, _ = setup
    res = client.get("/")
    assert res.status_code == 200
    assert "ThreadMind" in res.text
    assert client.get("/app.js").status_code == 200
