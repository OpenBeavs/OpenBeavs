# back/tests/test_api.py
import uuid
from unittest.mock import patch
import concurrent.futures as cf
import pytest

# 0) Health endpoint should return status ok and an agent count.
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["agents"], int)


# 1) Root endpoint should respond 200 with a readiness message prefix.
def test_1(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["message"].startswith("OpenBeavs Backend")

# 2) Agents list should include the seeded demo agent from startup.
def test_2(client, app_and_state):
    app, main = app_and_state
    r = client.get("/agents")
    assert r.status_code == 200
    agents = r.json()
    assert any(a["id"] == "cyrano_agent" for a in agents)

# 3) create-get-list-del chat should work end-to-end for a valid agent
def test_3(client, app_and_state):
    payload = {"title": "My Chat", "agent_id": "cyrano_agent"}
    r = client.post("/chats", json=payload)
    assert r.status_code == 200
    chat = r.json()
    chat_id = chat["id"]

    r = client.get(f"/chats/{chat_id}")
    assert r.status_code == 200
    assert r.json()["title"] == "My Chat"

    r = client.get("/chats")
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert chat_id in ids

    r = client.delete(f"/chats/{chat_id}")
    assert r.status_code == 200
    assert r.json()["message"] == "Chat deleted successfully"

    r = client.get(f"/chats/{chat_id}")
    assert r.status_code == 404

# 4) Sending a message to the agent should return an assistant reply and store 2 messages.
def test_4(client, app_and_state):
    r = client.post("/chats", json={"title": "T1", "agent_id": "cyrano_agent"})
    assert r.status_code == 200
    chat_id = r.json()["id"]

    r = client.post(f"/chats/{chat_id}/messages", json={"content": "Hello Cyrano"})
    assert r.status_code == 200
    msg = r.json()
    assert msg["role"] == "assistant"
    assert "Hello Cyrano" in msg["content"] or isinstance(msg["content"], str)

    r = client.get(f"/chats/{chat_id}/messages")
    assert r.status_code == 200
    history = r.json()
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"

# 5) Posting a message to a nonexistent chat should return 404.
def test_5(client):
    r = client.post(f"/chats/{uuid.uuid4()}/messages", json={"content": "hey"})
    assert r.status_code == 404
    #assert r.json()["detail"] == "Chat not found"

# 6) External agent happy path should return mocked 'external says hi'.
def test_6(client, app_and_state):
    ext_endpoint = "https://external-agent.example/jsonrpc"
    r = client.post("/agents/register", json={
        "name": "ExternalAgent",
        "description": "talks via json-rpc",
        "endpoint": ext_endpoint,
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
    })
    assert r.status_code == 200
    agent = r.json()

    r = client.post("/chats", json={"title": "ext", "agent_id": agent["id"]})
    assert r.status_code == 200
    chat_id = r.json()["id"]

    with patch("requests.post") as mock_post:
        class FakeResp:
            status_code = 200
            text = ""
            def json(self): return {"response": "external says hi"}
        mock_post.return_value = FakeResp()

        r = client.post(f"/chats/{chat_id}/messages", json={"content": "hi"})
        assert r.status_code == 200
        assert r.json()["content"] == "external says hi"

# 7) Register-by-URL and preview should map well-known agent.json into internal Agent model.
def test_7(client):
    agent_json = {
        "name": "HelloWorld",
        "description": "A minimal agent",
        "url": "https://hello-world.example/jsonrpc",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
    }

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return agent_json

    with patch("requests.get", return_value=FakeResp()):
        r = client.get("/agents/fetch-well-known", params={"agent_url": "hello-world.example"})
        assert r.status_code == 200
        preview = r.json()
        assert preview["name"] == "HelloWorld"

        r = client.post("/agents/register-by-url", json={"agent_url": "hello-world.example"})
        assert r.status_code == 200
        agent = r.json()
        assert agent["name"] == "HelloWorld"
        assert agent["endpoint"] == "https://hello-world.example/jsonrpc"

# 8) JSONRPC endpoint should return either result or error for an unknown method (no crash).
def test_8(client):
    payload = {"jsonrpc": "2.0", "method": "NonExisting", "params": {}, "id": 1}
    r = client.post("/jsonrpc", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert "error" in body or "result" in body

# 9) JSONRPC SendMessageRequest should require existing chat, expect fail for now
@pytest.mark.xfail(reason="Bug in JSON-RPC SendMessageRequest: appends to messages_db before chat exists check")
def test_9(client):
    fake_chat = str(uuid.uuid4())
    payload = {
        "jsonrpc": "2.0",
        "method": "SendMessageRequest",
        "params": {"chat_id": fake_chat, "message": "hi"},
        "id": 1
    }
    r = client.post("/jsonrpc", json=payload)
    body = r.json()
    assert body.get("error", {}).get("message") == "Chat not found"

# 10) Creating a chat with a missing agent should return 404.
def test_10(client):
    r = client.post("/chats", json={"title": "X", "agent_id": "nope"})
    assert r.status_code == 404
    assert r.json()["detail"] == "Agent not found"

# Validation Errors

# 11) Creating a chat with an empty body should return a validation error.
def test_11(client):
    r = client.post("/chats", json={})
    assert r.status_code in (400, 422)

# 12) Creating a chat with an empty title should return a validation error
def test_12(client):
    r = client.post("/chats", json={"title": ""})
    assert r.status_code in (400, 422)

# 13) Creating a chat without agent_id should return a validation error
def test_13(client):
    r = client.post("/chats", json={"title": "Has title"})
    assert r.status_code in (400, 422)

# 14) Sending a message without content should return a validation error
def test_14(client, app_and_state):
    chat = client.post("/chats", json={"title": "t", "agent_id": "cyrano_agent"}).json()
    r = client.post(f"/chats/{chat['id']}/messages", json={})
    assert r.status_code in (400, 422)

# 15) Wellknown agent JSON should include name, streaming capability, and a URL with scheme and host.
def test_15(client):
    r = client.get("/.well-known/agent.json")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "OpenBeavs"
    assert body["capabilities"]["streaming"] is True
    assert body["url"].startswith("http")

# 16) Files array on a user message should be persisted in the first history entry.
def test_16(client, app_and_state):
    chat = client.post("/chats", json={"title": "t", "agent_id": "cyrano_agent"}).json()
    files = [{"name": "note.txt", "type": "text/plain"}]
    client.post(f"/chats/{chat['id']}/messages", json={"content": "hi", "files": files})
    hist = client.get(f"/chats/{chat['id']}/messages").json()
    assert hist[0]["files"] == files

# 17) External agent non-200 response should surface as an error string in assistant content.
def test_17(client, app_and_state):
    agent = client.post("/agents/register", json={
        "name": "Ext", "description": "x",
        "endpoint": "https://ext.example/jsonrpc",
    }).json()
    chat = client.post("/chats", json={"title": "t", "agent_id": agent["id"]}).json()

    class FakeResp:
        status_code = 500
        text = "boom"

    with patch("requests.post", return_value=FakeResp()):
        r = client.post(f"/chats/{chat['id']}/messages", json={"content": "hi"})
        assert r.status_code == 200
        assert "Error contacting agent: 500" in r.json()["content"]

# 18) JSONRPC GetTaskRequest or CancelTaskRequest should return result objects, expect to fail.
@pytest.mark.xfail(reason="jsonrpc_endpoint awaits a sync dispatch; returns error until code is adjusted")
def test_18(client):
    r = client.post("/jsonrpc", json={"jsonrpc":"2.0","method":"GetTaskRequest","params":{"task_id":"t1"},"id":1})
    assert r.status_code == 200 and r.json().get("result", {}).get("status") == "completed"
    r = client.post("/jsonrpc", json={"jsonrpc":"2.0","method":"CancelTaskRequest","params":{"task_id":"t1"},"id":2})
    assert r.status_code == 200 and r.json().get("result", {}).get("cancelled") is True

# 19) CORS middleware should include acao when an Origin header is sent.
def test_19(client):
    r = client.get("/", headers={"Origin": "http://example.com"})
    assert r.headers.get("access-control-allow-origin") in ("*", "http://example.com")

# 20) Concurrent message posts should all succeed and produce paired user/assistant messages.
def test_20(client, app_and_state):
    chat = client.post("/chats", json={"title": "t", "agent_id": "cyrano_agent"}).json()
    def send(i): return client.post(f"/chats/{chat['id']}/messages", json={"content": f"hi {i}"}).status_code
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        codes = list(ex.map(send, range(10)))
    assert all(c == 200 for c in codes)
    assert len(client.get(f"/chats/{chat['id']}/messages").json()) == 20  # 10 each