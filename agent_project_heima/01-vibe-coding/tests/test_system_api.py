"""系统接口集成测试（Mock 数据库连接）"""
from unittest.mock import patch, MagicMock  # Mock 工具

import pytest  # pytest 框架
from fastapi.testclient import TestClient  # 同步 HTTP 测试客户端


@pytest.fixture(scope="module")  # 模块内共享客户端，避免重复初始化
def client():
    """构建 TestClient，所有存储组件 ping 均 Mock 为成功"""
    with patch("app.database.mysql_client.MySQLClient._connect"), \
         patch("app.database.milvus_client.MilvusClient._get_client"):
        from app.main import app
        return TestClient(app)


@pytest.fixture(autouse=True)  # 每个测试前重置 Redis Mock
def mock_redis_for_system(client):
    """Mock Redis，避免真实连接"""
    store: dict = {}
    mock = MagicMock()
    mock.get.side_effect = lambda key: store.get(key)
    mock.set.side_effect = lambda key, value, ttl=None: store.__setitem__(key, value) or True
    mock.ping.return_value = True

    with patch("app.database.redis_client.redis_client", mock), \
         patch("app.modules.subject_manager.redis_client", mock), \
         patch("app.routers.system.redis_client", mock):
        yield mock


class TestHealthCheck:
    def test_returns_200(self, client):
        with patch("app.routers.system.mysql_client") as m_mysql, \
             patch("app.routers.system.redis_client") as m_redis, \
             patch("app.routers.system.milvus_client") as m_milvus:
            m_mysql.ping.return_value = True   # 模拟 MySQL 正常
            m_redis.ping.return_value = True   # 模拟 Redis 正常
            m_milvus.ping.return_value = True  # 模拟 Milvus 正常

            resp = client.get("/api/v1/health")
            assert resp.status_code == 200  # HTTP 状态码

    def test_response_code_is_zero(self, client):
        with patch("app.routers.system.mysql_client") as m, \
             patch("app.routers.system.redis_client") as r, \
             patch("app.routers.system.milvus_client") as mv:
            m.ping.return_value = True
            r.ping.return_value = True
            mv.ping.return_value = True

            body = client.get("/api/v1/health").json()
            assert body["code"] == 0  # 业务码为 0

    def test_status_healthy_when_all_up(self, client):
        with patch("app.routers.system.mysql_client") as m, \
             patch("app.routers.system.redis_client") as r, \
             patch("app.routers.system.milvus_client") as mv:
            m.ping.return_value = True
            r.ping.return_value = True
            mv.ping.return_value = True

            body = client.get("/api/v1/health").json()
            assert body["data"]["status"] == "healthy"  # 全部 UP 时为 healthy

    def test_status_degraded_when_one_down(self, client):
        with patch("app.routers.system.mysql_client") as m, \
             patch("app.routers.system.redis_client") as r, \
             patch("app.routers.system.milvus_client") as mv:
            m.ping.return_value = False  # MySQL 故障
            r.ping.return_value = True
            mv.ping.return_value = True

            body = client.get("/api/v1/health").json()
            assert body["data"]["status"] == "degraded"  # 有组件 DOWN 时为 degraded

    def test_components_contain_all_three(self, client):
        with patch("app.routers.system.mysql_client") as m, \
             patch("app.routers.system.redis_client") as r, \
             patch("app.routers.system.milvus_client") as mv:
            m.ping.return_value = True
            r.ping.return_value = True
            mv.ping.return_value = True

            body = client.get("/api/v1/health").json()
            components = body["data"]["components"]
            assert "mysql" in components   # 包含 MySQL 状态
            assert "redis" in components   # 包含 Redis 状态
            assert "milvus" in components  # 包含 Milvus 状态


class TestSubjectsList:
    def test_returns_200(self, client):
        resp = client.get("/api/v1/subjects")
        assert resp.status_code == 200

    def test_response_code_is_zero(self, client):
        body = client.get("/api/v1/subjects").json()
        assert body["code"] == 0

    def test_subjects_list_not_empty(self, client):
        body = client.get("/api/v1/subjects").json()
        assert len(body["data"]["subjects"]) > 0  # 至少有一个学科

    def test_subjects_contain_java(self, client):
        body = client.get("/api/v1/subjects").json()
        codes = [s["code"] for s in body["data"]["subjects"]]
        assert "java" in codes  # java 学科必须存在

    def test_each_subject_has_code_and_name(self, client):
        body = client.get("/api/v1/subjects").json()
        for subject in body["data"]["subjects"]:
            assert "code" in subject  # code 字段必须存在
            assert "name" in subject  # name 字段必须存在
