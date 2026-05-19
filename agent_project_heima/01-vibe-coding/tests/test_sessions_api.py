"""会话管理 API 集成测试"""
from unittest.mock import MagicMock, patch  # Mock 工具

import pytest  # pytest 框架
from fastapi.testclient import TestClient  # HTTP 测试客户端


@pytest.fixture(scope="module")  # 模块内共享同一 app 实例
def client():
    """构建 TestClient，跳过数据库真实连接"""
    with patch("app.database.mysql_client.MySQLClient._connect"), \
         patch("app.database.milvus_client.MilvusClient._get_client"):
        from app.main import app
        return TestClient(app)


@pytest.fixture(autouse=True)  # 每个测试前隔离 Redis 状态
def mock_redis_session():
    """内存 Redis Mock，独立于其他测试"""
    hashes: dict = {}
    lists: dict = {}

    mock = MagicMock()
    mock.hset.side_effect = lambda key, mapping: hashes.setdefault(key, {}).update(mapping) or 0
    mock.hgetall.side_effect = lambda key: dict(hashes.get(key, {}))
    mock.expire.return_value = True
    mock.rpush.side_effect = lambda key, *v: lists.setdefault(key, []).extend(v) or len(lists[key])
    mock.lrange.side_effect = lambda key, s, e: (
        lists.get(key, [])[s: (None if e == -1 else e + 1)]
    )
    mock.llen.side_effect = lambda key: len(lists.get(key, []))
    mock.delete_list.side_effect = lambda key: lists.pop(key, None) and 1 or 1

    with patch("app.modules.session_manager.redis_client", mock), \
         patch("app.modules.subject_manager.redis_client", mock), \
         patch("app.routers.system.redis_client", mock):
        yield mock


class TestCreateSession:
    def test_returns_201(self, client):
        resp = client.post("/api/v1/sessions")
        assert resp.status_code == 201  # 创建成功返回 201

    def test_response_code_zero(self, client):
        body = client.post("/api/v1/sessions").json()
        assert body["code"] == 0  # 业务码为 0

    def test_returns_session_id(self, client):
        body = client.post("/api/v1/sessions").json()
        assert "session_id" in body["data"]  # 响应含 session_id

    def test_session_id_is_uuid(self, client):
        import uuid
        body = client.post("/api/v1/sessions").json()
        uuid.UUID(body["data"]["session_id"])  # 格式合法不抛异常

    def test_returns_created_at(self, client):
        body = client.post("/api/v1/sessions").json()
        assert "created_at" in body["data"]  # 响应含创建时间

    def test_two_sessions_have_different_ids(self, client):
        id1 = client.post("/api/v1/sessions").json()["data"]["session_id"]
        id2 = client.post("/api/v1/sessions").json()["data"]["session_id"]
        assert id1 != id2  # 每次创建 ID 唯一


class TestGetHistory:
    def test_returns_404_for_unknown_session(self, client):
        resp = client.get("/api/v1/sessions/00000000-0000-0000-0000-000000000000/history")
        assert resp.status_code == 404  # 不存在的会话返回 404

    def test_empty_history_for_new_session(self, client):
        sid = client.post("/api/v1/sessions").json()["data"]["session_id"]
        body = client.get(f"/api/v1/sessions/{sid}/history").json()
        assert body["data"]["total"] == 0      # 新会话无历史
        assert body["data"]["messages"] == []  # 消息列表为空

    def test_pagination_params_accepted(self, client):
        sid = client.post("/api/v1/sessions").json()["data"]["session_id"]
        resp = client.get(f"/api/v1/sessions/{sid}/history?page=1&page_size=10")
        assert resp.status_code == 200  # 分页参数合法

    def test_invalid_page_returns_422(self, client):
        sid = client.post("/api/v1/sessions").json()["data"]["session_id"]
        resp = client.get(f"/api/v1/sessions/{sid}/history?page=0")
        assert resp.status_code == 422  # page=0 不合法，返回 422


class TestClearHistory:
    def test_returns_404_for_unknown_session(self, client):
        resp = client.delete("/api/v1/sessions/00000000-0000-0000-0000-000000000000/history")
        assert resp.status_code == 404  # 不存在的会话返回 404

    def test_clear_returns_200(self, client):
        sid = client.post("/api/v1/sessions").json()["data"]["session_id"]
        resp = client.delete(f"/api/v1/sessions/{sid}/history")
        assert resp.status_code == 200  # 清空成功

    def test_clear_message_is_correct(self, client):
        sid = client.post("/api/v1/sessions").json()["data"]["session_id"]
        body = client.delete(f"/api/v1/sessions/{sid}/history").json()
        assert "清空" in body["message"]  # 响应消息含"清空"字样
