# monitoring/metrics.py
"""
Prometheus 监控埋点，覆盖：
- 入库吞吐量与延迟（P50/P95/P99）
- 混合检索 QPS 与耗时分布
- Reranker 精排延迟
- 多租户维度的所有指标
- 模型推理耗时（Embedding / Vision）
- 错误率与失败类型分布
"""
from prometheus_client import (
    Counter, Histogram, Gauge, Summary,
    start_http_server, REGISTRY,
)
import functools, time, logging

logger = logging.getLogger(__name__)

# ─── 定义所有指标 ─────────────────────────────────────────────────────────────

# 入库指标
INGEST_TOTAL = Counter(
    "rag_ingest_docs_total",
    "入库文档总数",
    ["tenant_id", "status"],
)
INGEST_CHUNKS = Counter(
    "rag_ingest_chunks_total",
    "入库 Chunk 总数",
    ["tenant_id", "chunk_type"],
)
INGEST_LATENCY = Histogram(
    "rag_ingest_latency_seconds",
    "单文档入库耗时",
    ["tenant_id"],
    buckets=[1, 5, 10, 30, 60, 120, 300],
)

# 检索指标
SEARCH_QPS = Counter(
    "rag_search_requests_total",
    "检索请求总数",
    ["tenant_id", "rerank_enabled"],
)
SEARCH_LATENCY = Histogram(
    "rag_search_latency_ms",
    "混合检索总耗时(ms)",
    ["tenant_id"],
    buckets=[10, 50, 100, 200, 500, 1000, 2000],
)
EMBED_LATENCY = Histogram(
    "rag_embed_latency_ms",
    "Embedding 推理耗时(ms)",
    ["tenant_id"],
    buckets=[5, 20, 50, 100, 200, 500],
)
RERANK_LATENCY = Histogram(
    "rag_rerank_latency_ms",
    "Reranker 精排耗时(ms)",
    ["tenant_id"],
    buckets=[10, 50, 100, 200, 500, 1000],
)
CANDIDATE_COUNT = Histogram(
    "rag_candidate_count",
    "混合检索候选集大小",
    ["tenant_id"],
    buckets=[1, 5, 10, 20, 50, 100],
)

# 模型推理指标
VISION_LATENCY = Histogram(
    "rag_vision_latency_seconds",
    "Vision 模型推理耗时",
    ["model"],
    buckets=[1, 3, 5, 10, 20, 60],
)
TABLE_EXTRACT_METHOD = Counter(
    "rag_table_extract_method_total",
    "表格提取方法统计",
    ["method", "tenant_id"],
)

# 系统健康
MILVUS_ENTITY_COUNT = Gauge(
    "rag_milvus_entity_count",
    "Milvus 实体总数",
    ["tenant_id"],
)
ERROR_TOTAL = Counter(
    "rag_errors_total",
    "错误总数",
    ["tenant_id", "error_type"],
)


# ─── 指标记录接口 ──────────────────────────────────────────────────────────────

class RAGMetrics:
    def record_ingest(
        self,
        tenant_id: str,
        status: str,
        latency_s: float,
        chunk_counts: dict,
    ):
        INGEST_TOTAL.labels(tenant_id=tenant_id, status=status).inc()
        INGEST_LATENCY.labels(tenant_id=tenant_id).observe(latency_s)
        for chunk_type, count in chunk_counts.items():
            INGEST_CHUNKS.labels(
                tenant_id=tenant_id, chunk_type=chunk_type
            ).inc(count)

    def record_search(
        self,
        tenant_id: str,
        embed_ms: float,
        search_ms: float,
        rerank_ms: float,
        candidate_count: int,
        result_count: int,
        rerank_enabled: bool = True,
    ):
        SEARCH_QPS.labels(
            tenant_id=tenant_id,
            rerank_enabled=str(rerank_enabled),
        ).inc()
        SEARCH_LATENCY.labels(tenant_id=tenant_id).observe(
            embed_ms + search_ms + rerank_ms
        )
        EMBED_LATENCY.labels(tenant_id=tenant_id).observe(embed_ms)
        RERANK_LATENCY.labels(tenant_id=tenant_id).observe(rerank_ms)
        CANDIDATE_COUNT.labels(tenant_id=tenant_id).observe(candidate_count)

    def record_error(self, tenant_id: str, error_type: str):
        ERROR_TOTAL.labels(tenant_id=tenant_id, error_type=error_type).inc()

    def record_table_method(self, tenant_id: str, method: str):
        TABLE_EXTRACT_METHOD.labels(method=method, tenant_id=tenant_id).inc()

    def record_vision(self, model: str, latency_s: float):
        VISION_LATENCY.labels(model=model).observe(latency_s)


rag_metrics = RAGMetrics()


def start_metrics_server(port: int = 8000):
    """启动 Prometheus metrics HTTP server"""
    start_http_server(port)
    logger.info(f"Prometheus metrics 已启动: http://localhost:{port}/metrics")


# ─── 装饰器（方便函数级别自动埋点）──────────────────────────────────────────

def track_latency(histogram: Histogram, tenant_id_arg: str = "tenant_id"):
    """自动记录函数耗时的装饰器"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tid = kwargs.get(tenant_id_arg, "unknown")
            t0 = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                rag_metrics.record_error(tid, type(e).__name__)
                raise
            finally:
                elapsed = (time.perf_counter() - t0) * 1000
                histogram.labels(tenant_id=tid).observe(elapsed)
        return wrapper
    return decorator