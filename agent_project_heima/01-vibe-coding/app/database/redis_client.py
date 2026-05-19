import json  # 序列化/反序列化
from typing import Any, Optional  # 类型注解

import redis  # Redis 客户端库
from redis import Redis  # 连接类型

from app import config  # 读取 Redis 连接配置
from app.utils.logger import get_logger  # 获取命名 Logger

logger = get_logger("database.redis")  # 模块专属日志


class RedisClient:
    """Redis 客户端封装，使用连接池提高并发性能"""

    def __init__(self):
        self._pool = redis.ConnectionPool(  # 初始化连接池
            host=config.redis.host,
            port=config.redis.port,
            password=config.redis.password,
            db=config.redis.db,
            max_connections=50,           # 最大连接数上限
            socket_timeout=5,             # 操作超时 5 秒
            socket_connect_timeout=5,     # 建立连接超时 5 秒
            decode_responses=True,        # 自动将字节解码为字符串
        )
        self._client: Redis = redis.Redis(connection_pool=self._pool)  # 从连接池获取客户端

    # ── 通用 KV 操作 ──────────────────────────────────────────────────────────

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """存储键值，value 自动 JSON 序列化，ttl 单位秒"""
        serialized = json.dumps(value, ensure_ascii=False)  # 中文不转义
        return bool(self._client.set(key, serialized, ex=ttl))

    def get(self, key: str) -> Optional[Any]:
        """读取键值，自动 JSON 反序列化，键不存在返回 None"""
        raw = self._client.get(key)
        return json.loads(raw) if raw is not None else None

    def delete(self, *keys: str) -> int:
        """删除一个或多个键，返回实际删除数量"""
        return self._client.delete(*keys)

    def exists(self, key: str) -> bool:
        """判断键是否存在"""
        return bool(self._client.exists(key))

    def expire(self, key: str, ttl: int) -> bool:
        """重置键的过期时间"""
        return bool(self._client.expire(key, ttl))

    def ttl(self, key: str) -> int:
        """查询键的剩余生存时间，-1 表示永不过期，-2 表示不存在"""
        return self._client.ttl(key)

    # ── Hash 操作（用于会话元数据）────────────────────────────────────────────

    def hset(self, key: str, mapping: dict) -> int:
        """批量写入 Hash 字段"""
        return self._client.hset(key, mapping=mapping)

    def hgetall(self, key: str) -> dict:
        """读取 Hash 所有字段"""
        return self._client.hgetall(key)

    # ── List 操作（用于历史消息队列）──────────────────────────────────────────

    def rpush(self, key: str, *values: Any) -> int:
        """追加到 List 右端，values 自动 JSON 序列化"""
        serialized = [json.dumps(v, ensure_ascii=False) for v in values]
        return self._client.rpush(key, *serialized)

    def lrange(self, key: str, start: int, end: int) -> list:
        """读取 List 范围，自动 JSON 反序列化"""
        raw_list = self._client.lrange(key, start, end)
        return [json.loads(item) for item in raw_list]

    def llen(self, key: str) -> int:
        """返回 List 长度"""
        return self._client.llen(key)

    def delete_list(self, key: str) -> int:
        """删除 List（清空历史消息）"""
        return self._client.delete(key)

    # ── 系统操作 ──────────────────────────────────────────────────────────────

    def ping(self) -> bool:
        """健康探测，PING 验证连接可用"""
        try:
            return self._client.ping()
        except Exception as e:
            logger.error(f"Redis ping 失败: {e}")
            return False

    def incr(self, key: str) -> int:
        """原子自增，用于限流计数"""
        return self._client.incr(key)


# 模块级单例
redis_client = RedisClient()
