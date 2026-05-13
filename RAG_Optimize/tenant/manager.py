# tenant/manager.py
"""
多租户隔离策略：
- Milvus partition_key 物理隔离数据
- 配额管理（文档数、存储量、QPS）
- 鉴权中间件
- 租户级别的 BM25 词典独立维护
"""
import hashlib, time, json
from dataclasses import dataclass, field, asdict
from typing import Optional
import redis   # 配额计数器用 Redis

@dataclass
class TenantConfig:
    tenant_id: str
    name: str
    max_docs: int = 10_000
    max_storage_mb: int = 5_000
    max_qps: int = 20
    api_key_hash: str = ""
    created_at: float = field(default_factory=time.time)
    extra: dict = field(default_factory=dict)


class TenantManager:
    """
    租户生命周期管理 + 配额控制 + 鉴权
    配额数据存 Redis，元数据存 JSON（生产建议 PostgreSQL）
    """
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        config_path: str = "tenants.json",
    ):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.config_path = config_path
        self._tenants: dict[str, TenantConfig] = self._load_configs()

    def _load_configs(self) -> dict:
        try:
            with open(self.config_path) as f:
                data = json.load(f)
            return {k: TenantConfig(**v) for k, v in data.items()}
        except FileNotFoundError:
            return {}

    def _save_configs(self):
        with open(self.config_path, "w") as f:
            json.dump(
                {k: asdict(v) for k, v in self._tenants.items()},
                f, ensure_ascii=False, indent=2,
            )

    def create_tenant(
        self,
        tenant_id: str,
        name: str,
        api_key: str,
        **kwargs,
    ) -> TenantConfig:
        if tenant_id in self._tenants:
            raise ValueError(f"租户 {tenant_id} 已存在")
        cfg = TenantConfig(
            tenant_id=tenant_id,
            name=name,
            api_key_hash=hashlib.sha256(api_key.encode()).hexdigest(),
            **kwargs,
        )
        self._tenants[tenant_id] = cfg
        self._save_configs()
        return cfg

    def authenticate(self, tenant_id: str, api_key: str) -> bool:
        """API Key 鉴权"""
        cfg = self._tenants.get(tenant_id)
        if not cfg:
            return False
        return cfg.api_key_hash == hashlib.sha256(api_key.encode()).hexdigest()

    def check_qps(self, tenant_id: str) -> bool:
        """滑动窗口 QPS 限流（Redis 实现）"""
        cfg = self._tenants.get(tenant_id)
        if not cfg:
            return False
        key = f"qps:{tenant_id}:{int(time.time())}"
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 2)    # 1秒窗口，2秒过期防泄漏
        count, _ = pipe.execute()
        return count <= cfg.max_qps

    def check_doc_quota(self, tenant_id: str, add_count: int = 1) -> bool:
        """文档数配额检查"""
        cfg = self._tenants.get(tenant_id)
        if not cfg:
            return False
        key = f"doc_count:{tenant_id}"
        current = int(self.redis.get(key) or 0)
        return current + add_count <= cfg.max_docs

    def increment_doc_count(self, tenant_id: str, count: int = 1):
        self.redis.incrby(f"doc_count:{tenant_id}", count)

    def get_tenant_stats(self, tenant_id: str) -> dict:
        """租户用量统计"""
        return {
            "doc_count": int(self.redis.get(f"doc_count:{tenant_id}") or 0),
            "search_today": int(self.redis.get(f"search:{tenant_id}:{self._today()}") or 0),
            "config": asdict(self._tenants.get(tenant_id, TenantConfig("", ""))),
        }

    @staticmethod
    def _today() -> str:
        import datetime
        return datetime.date.today().isoformat()