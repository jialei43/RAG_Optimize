"""问答 API 集成测试（Mock QA 引擎）"""
import json  # SSE 解析
from unittest.mock import MagicMock, patch  # Mock 工具

import pytest  # pytest 框架
from fastapi.testclient import TestClient  # HTTP 测试客户端


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """构建 TestClient，跳过数据库真实连接"""
    with patch("app.database.mysql_client.MySQLClient._connect"), \
         patch("app.database.milvus_client.MilvusClient._get_client"):
        from app.main import app
        return TestClient(app)


@pytest.fixture()
def valid_session(client):
    """创建真实会话，用于问答接口测试"""
    hashes: dict = {}
    mock = MagicMock()
    mock.hset.side_effect = lambda key, mapping: hashes.setdefault(key, {}).update(mapping) or 0
    mock.hgetall.side_effect = lambda key: dict(hashes.get(key, {}))
    mock.expire.return_value = True
    mock.llen.return_value = 0
    mock.lrange.return_value = []
    mock.rpush.return_value = 1
    mock.delete_list.return_value = 1

    with patch("app.modules.session_manager.redis_client", mock), \
         patch("app.modules.subject_manager.redis_client", mock):
        resp = client.post("/api/v1/sessions")
        sid = resp.json()["data"]["session_id"]
        yield sid, mock  # 同时返回 Mock 供断言使用


def _mock_answer_result(answer: str = "这是答案") -> dict:
    """构造 qa_engine.answer 的标准返回值"""
    return {
        "answer": answer,
        "sources": [{"parent_id": "p1", "subject": "java", "excerpt": "Java..."}],
        "response_time_ms": 500,
    }


def _mock_stream_events(tokens: list[str] = None) -> list[dict]:
    """构造 qa_engine.answer_stream 的标准事件序列"""
    tokens = tokens or ["Java", " 答案"]
    return (
        [{"type": "start"}]
        + [{"type": "token", "content": t} for t in tokens]
        + [{"type": "sources", "sources": []}]
        + [{"type": "end", "response_time_ms": 300}]
    )


# ── 即时问答接口测试 ──────────────────────────────────────────────────────────

class TestChatEndpoint:
    def test_returns_200_on_success(self, client, valid_session):
        sid, _ = valid_session
        with patch("app.routers.chat.qa_engine.answer", return_value=_mock_answer_result()):
            resp = client.post("/api/v1/chat", json={"session_id": sid, "question": "什么是 HashMap?"})
        assert resp.status_code == 200

    def test_response_code_zero(self, client, valid_session):
        sid, _ = valid_session
        with patch("app.routers.chat.qa_engine.answer", return_value=_mock_answer_result()):
            body = client.post("/api/v1/chat", json={"session_id": sid, "question": "test"}).json()
        assert body["code"] == 0

    def test_response_contains_answer(self, client, valid_session):
        sid, _ = valid_session
        with patch("app.routers.chat.qa_engine.answer", return_value=_mock_answer_result("正确答案")):
            body = client.post("/api/v1/chat", json={"session_id": sid, "question": "test"}).json()
        assert body["data"]["answer"] == "正确答案"  # 答案内容透传

    def test_invalid_subject_returns_400(self, client, valid_session):
        sid, _ = valid_session
        resp = client.post("/api/v1/chat", json={
            "session_id": sid, "question": "test", "subject": "nonexistent"
        })
        assert resp.status_code == 400  # 非法学科返回 400

    def test_missing_question_returns_422(self, client, valid_session):
        sid, _ = valid_session
        resp = client.post("/api/v1/chat", json={"session_id": sid})
        assert resp.status_code == 422  # 缺少 question 字段返回 422

    def test_empty_question_returns_422(self, client, valid_session):
        sid, _ = valid_session
        resp = client.post("/api/v1/chat", json={"session_id": sid, "question": ""})
        assert resp.status_code == 422  # 空问题返回 422

    def test_question_over_500_chars_returns_422(self, client, valid_session):
        sid, _ = valid_session
        resp = client.post("/api/v1/chat", json={"session_id": sid, "question": "a" * 501})
        assert resp.status_code == 422  # 超长问题返回 422

    def test_nonexistent_session_returns_404(self, client):
        fake_sid = "00000000-0000-0000-0000-000000000000"
        with patch("app.routers.chat.qa_engine.answer", side_effect=ValueError("会话不存在")):
            resp = client.post("/api/v1/chat", json={"session_id": fake_sid, "question": "test"})
        assert resp.status_code == 404  # 会话不存在返回 404

    def test_valid_subject_accepted(self, client, valid_session):
        sid, _ = valid_session
        with patch("app.routers.chat.qa_engine.answer", return_value=_mock_answer_result()):
            resp = client.post("/api/v1/chat", json={
                "session_id": sid, "question": "test", "subject": "java"
            })
        assert resp.status_code == 200  # 合法学科正常处理


# ── 流式问答接口测试 ──────────────────────────────────────────────────────────

class TestChatStreamEndpoint:
    def _collect_sse_events(self, resp) -> list[dict]:
        """解析 SSE 响应体为事件字典列表"""
        events = []
        for line in resp.text.strip().split("\n"):
            line = line.strip()
            if line.startswith("data: "):  # 只处理 data: 行
                events.append(json.loads(line[6:]))
        return events

    def test_returns_200_with_sse_content_type(self, client, valid_session):
        sid, _ = valid_session
        with patch("app.routers.chat.qa_engine.answer_stream",
                   return_value=iter(_mock_stream_events())):
            resp = client.post("/api/v1/chat/stream", json={"session_id": sid, "question": "test"})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]  # Content-Type 正确

    def test_sse_contains_start_event(self, client, valid_session):
        sid, _ = valid_session
        with patch("app.routers.chat.qa_engine.answer_stream",
                   return_value=iter(_mock_stream_events())):
            resp = client.post("/api/v1/chat/stream", json={"session_id": sid, "question": "test"})
        events = self._collect_sse_events(resp)
        assert events[0]["type"] == "start"  # 第一个事件是 start

    def test_sse_contains_end_event(self, client, valid_session):
        sid, _ = valid_session
        with patch("app.routers.chat.qa_engine.answer_stream",
                   return_value=iter(_mock_stream_events())):
            resp = client.post("/api/v1/chat/stream", json={"session_id": sid, "question": "test"})
        events = self._collect_sse_events(resp)
        assert events[-1]["type"] == "end"  # 最后一个事件是 end

    def test_sse_contains_token_events(self, client, valid_session):
        sid, _ = valid_session
        with patch("app.routers.chat.qa_engine.answer_stream",
                   return_value=iter(_mock_stream_events(["A", "B"]))):
            resp = client.post("/api/v1/chat/stream", json={"session_id": sid, "question": "test"})
        events = self._collect_sse_events(resp)
        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) == 2  # 两个 token 事件

    def test_sse_error_event_on_invalid_session(self, client):
        fake_sid = "00000000-0000-0000-0000-000000000000"
        with patch("app.routers.chat.qa_engine.answer_stream",
                   side_effect=ValueError("会话不存在")):
            resp = client.post("/api/v1/chat/stream",
                               json={"session_id": fake_sid, "question": "test"})
        events = self._collect_sse_events(resp)
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1      # 有且仅有一个错误事件
        assert error_events[0]["code"] == 2001  # 错误码正确
