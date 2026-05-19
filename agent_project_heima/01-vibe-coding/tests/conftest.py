import pytest  # pytest 测试框架
from fastapi.testclient import TestClient  # FastAPI 同步测试客户端
from unittest.mock import MagicMock, patch  # Mock 工具


@pytest.fixture(scope="session")  # 整个测试会话共享一个 app 实例
def app():
    """返回 FastAPI 应用实例，数据库连接全部 Mock"""
    with patch("app.database.mysql_client.MySQLClient.ping", return_value=True), \
         patch("app.database.redis_client.RedisClient.ping", return_value=True), \
         patch("app.database.milvus_client.MilvusClient.ping", return_value=True):
        from app.main import app as _app  # 延迟导入避免副作用
        yield _app


@pytest.fixture(scope="session")  # 整个测试会话共享一个 HTTP 客户端
def client(app):
    """返回同步 TestClient，供集成测试调用接口"""
    return TestClient(app)
