"""数据库客户端单元测试（全部 Mock，不依赖真实服务）"""
import json  # 序列化辅助
from unittest.mock import MagicMock, patch, PropertyMock  # Mock 工具

import pytest  # pytest 框架


# ── MySQL 客户端测试 ─────────────────────────────────────────────────────────

class TestMySQLClient:
    @patch("app.database.mysql_client.pymysql.connect")  # Mock 底层连接
    def test_ping_returns_true_on_success(self, mock_connect):
        mock_conn = MagicMock()  # 模拟连接对象
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.open = True
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        from app.database.mysql_client import MySQLClient
        client = MySQLClient()
        assert client.ping() is True  # 正常连接时 ping 返回 True

    @patch("app.database.mysql_client.pymysql.connect", side_effect=Exception("connection refused"))
    def test_ping_returns_false_on_failure(self, mock_connect):
        from app.database.mysql_client import MySQLClient
        client = MySQLClient()
        assert client.ping() is False  # 连接失败时 ping 返回 False


# ── Redis 客户端测试 ─────────────────────────────────────────────────────────

class TestRedisClient:
    @patch("app.database.redis_client.redis.ConnectionPool")  # Mock 连接池
    @patch("app.database.redis_client.redis.Redis")           # Mock Redis 客户端
    def _make_client(self, mock_redis_cls, mock_pool_cls):
        from app.database.redis_client import RedisClient
        client = RedisClient()
        client._client = mock_redis_cls.return_value  # 替换内部客户端为 Mock
        return client, mock_redis_cls.return_value

    def test_set_serializes_to_json(self):
        from app.database.redis_client import RedisClient
        client = RedisClient()
        mock_inner = MagicMock()
        mock_inner.set.return_value = True
        client._client = mock_inner

        client.set("k", {"foo": "bar"}, ttl=60)
        call_args = mock_inner.set.call_args
        assert call_args[0][0] == "k"                           # key 正确
        assert json.loads(call_args[0][1]) == {"foo": "bar"}    # 值已 JSON 序列化
        assert call_args[1]["ex"] == 60                         # TTL 传入正确

    def test_get_deserializes_json(self):
        from app.database.redis_client import RedisClient
        client = RedisClient()
        mock_inner = MagicMock()
        mock_inner.get.return_value = '{"a": 1}'  # 模拟 Redis 返回 JSON 字符串
        client._client = mock_inner

        result = client.get("k")
        assert result == {"a": 1}  # 正确反序列化

    def test_get_returns_none_for_missing_key(self):
        from app.database.redis_client import RedisClient
        client = RedisClient()
        mock_inner = MagicMock()
        mock_inner.get.return_value = None  # 键不存在
        client._client = mock_inner

        assert client.get("missing") is None  # 不存在时返回 None

    def test_rpush_serializes_each_value(self):
        from app.database.redis_client import RedisClient
        client = RedisClient()
        mock_inner = MagicMock()
        client._client = mock_inner

        client.rpush("history", {"role": "user", "content": "hello"})
        call_args = mock_inner.rpush.call_args[0]
        assert call_args[0] == "history"                      # key 正确
        assert json.loads(call_args[1]) == {"role": "user", "content": "hello"}  # 值序列化

    def test_lrange_deserializes_list(self):
        from app.database.redis_client import RedisClient
        client = RedisClient()
        mock_inner = MagicMock()
        mock_inner.lrange.return_value = ['{"role":"user"}', '{"role":"assistant"}']
        client._client = mock_inner

        result = client.lrange("history", 0, -1)
        assert result == [{"role": "user"}, {"role": "assistant"}]  # 列表正确反序列化

    def test_ping_returns_true(self):
        from app.database.redis_client import RedisClient
        client = RedisClient()
        mock_inner = MagicMock()
        mock_inner.ping.return_value = True
        client._client = mock_inner

        assert client.ping() is True

    def test_ping_returns_false_on_exception(self):
        from app.database.redis_client import RedisClient
        client = RedisClient()
        mock_inner = MagicMock()
        mock_inner.ping.side_effect = Exception("timeout")
        client._client = mock_inner

        assert client.ping() is False


# ── Milvus 客户端测试 ────────────────────────────────────────────────────────

class TestMilvusClient:
    def _make_client_with_mock(self):
        from app.database.milvus_client import MilvusClient
        client = MilvusClient()
        client._client = MagicMock()  # 注入 Mock，跳过真实连接
        return client

    def test_ping_returns_true(self):
        client = self._make_client_with_mock()
        client._client.list_collections.return_value = []
        assert client.ping() is True

    def test_ping_returns_false_on_exception(self):
        client = self._make_client_with_mock()
        client._client.list_collections.side_effect = Exception("unreachable")
        assert client.ping() is False

    def test_search_passes_filter_expr(self):
        client = self._make_client_with_mock()
        client._client.search.return_value = [[]]  # 模拟空结果

        client.search(
            query_vectors=[[0.1] * 1536],
            limit=10,
            output_fields=["parent_id", "content"],
            filter_expr="source == 'java'",
        )
        call_kwargs = client._client.search.call_args[1]
        assert call_kwargs["filter"] == "source == 'java'"  # 过滤条件正确传递

    def test_search_no_filter_passes_empty_string(self):
        client = self._make_client_with_mock()
        client._client.search.return_value = [[]]

        client.search(query_vectors=[[0.0] * 1536], limit=5, output_fields=["parent_id"])
        call_kwargs = client._client.search.call_args[1]
        assert call_kwargs["filter"] == ""  # 无过滤时传空字符串

    def test_collection_name_property(self):
        client = self._make_client_with_mock()
        from app import config
        assert client.collection_name == config.milvus.collection_name  # 属性返回配置中的集合名
