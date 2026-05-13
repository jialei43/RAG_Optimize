# search/hybrid_engine.py
"""
混合检索引擎：
1. BGE-M3 稠密向量检索
2. Milvus 内置 BM25 稀疏检索
3. RRF (Reciprocal Rank Fusion) 融合
4. BGE-Reranker-v2-m3 精排
5. 结果溯源与置信度评估
"""
import time, logging
from dataclasses import dataclass
from models.chinese_models import BGEEmbedder, BGEReranker
from storage.milvus_store import MilvusMultiTenantStore
from monitoring.metrics import rag_metrics   # 见监控模块

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    content: str
    doc_id: str
    chunk_type: str
    page_num: int
    rerank_score: float
    rrf_score: float
    metadata: dict
    source_label: str  # 溯源标签


class HybridSearchEngine:
    def __init__(
        self,
        embedder: BGEEmbedder,
        reranker: BGEReranker,
        store: MilvusMultiTenantStore,
        candidate_k: int = 50,   # 混合检索候选数
        rerank_k: int = 5,       # 重排后保留数
    ):
        self.embedder = embedder
        self.reranker = reranker
        self.store = store
        self.candidate_k = candidate_k
        self.rerank_k = rerank_k

    def search(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 5,
        chunk_type_filter: list[str] = None,
        rerank: bool = True,
    ) -> list[SearchResult]:
        t0 = time.perf_counter()

        # Step 1: 编码查询（稠密 + 稀疏双路）
        embed_out = self.embedder.encode([query], return_sparse=True)
        query_dense = embed_out["dense"][0]
        query_sparse = embed_out["sparse"][0] if embed_out["sparse"] else {}

        # BM25 稀疏向量
        bm25_sparse = self.store.bm25_fn.encode_queries([query])[0]

        embed_ms = (time.perf_counter() - t0) * 1000

        # Step 2: 混合检索（三路 RRF）
        t1 = time.perf_counter()
        filter_expr = None
        if chunk_type_filter:
            types_str = ", ".join(f'"{t}"' for t in chunk_type_filter)
            filter_expr = f"chunk_type in [{types_str}]"

        candidates = self.store.hybrid_search(
            query_dense=query_dense,
            query_sparse=bm25_sparse,
            tenant_id=tenant_id,
            top_k=self.candidate_k,
            filter_expr=filter_expr,
        )
        search_ms = (time.perf_counter() - t1) * 1000

        if not candidates:
            return []

        # Step 3: Reranker 精排
        t2 = time.perf_counter()
        rerank_results = []
        if rerank and len(candidates) > 1:
            passages = [c["content"] for c in candidates]
            ranked = self.reranker.rerank(query, passages, top_k=top_k)
            for r in ranked:
                cand = candidates[r["idx"]]
                rerank_results.append(SearchResult(
                    content=cand["content"],
                    doc_id=cand["doc_id"],
                    chunk_type=cand["chunk_type"],
                    page_num=cand["page_num"],
                    rerank_score=r["score"],
                    rrf_score=cand["score"],
                    metadata=cand["metadata"],
                    source_label=self._build_source_label(cand),
                ))
        else:
            for cand in candidates[:top_k]:
                rerank_results.append(SearchResult(
                    content=cand["content"],
                    doc_id=cand["doc_id"],
                    chunk_type=cand["chunk_type"],
                    page_num=cand["page_num"],
                    rerank_score=cand["score"],
                    rrf_score=cand["score"],
                    metadata=cand["metadata"],
                    source_label=self._build_source_label(cand),
                ))
        rerank_ms = (time.perf_counter() - t2) * 1000

        # 上报监控指标
        rag_metrics.record_search(
            tenant_id=tenant_id,
            embed_ms=embed_ms,
            search_ms=search_ms,
            rerank_ms=rerank_ms,
            candidate_count=len(candidates),
            result_count=len(rerank_results),
        )
        logger.info(
            f"[{tenant_id}] 检索完成: embed={embed_ms:.1f}ms "
            f"search={search_ms:.1f}ms rerank={rerank_ms:.1f}ms "
            f"candidates={len(candidates)} results={len(rerank_results)}"
        )
        return rerank_results

    @staticmethod
    def _build_source_label(cand: dict) -> str:
        meta = cand.get("metadata", {})
        parts = []
        if meta.get("doc_title"):
            parts.append(meta["doc_title"])
        if cand.get("page_num"):
            parts.append(f"第{cand['page_num']}页")
        chunk_type = cand.get("chunk_type", "")
        if chunk_type == "table":
            parts.append("[表格]")
        elif chunk_type == "image":
            parts.append("[图片]")
        return " · ".join(parts) if parts else cand["doc_id"]