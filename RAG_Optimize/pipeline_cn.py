# pipeline_cn.py
"""
完整流水线：国产模型 + Milvus + 混合检索 + 多租户 + 监控
"""
import asyncio, hashlib, time, logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from models.chinese_model import BGEEmbedder, BGEReranker, InternVLVision, PaddleOCREngine
from stroge.milvus_store import MilvusMultiTenantStore
from search.hybrid_engine import HybridSearchEngine
from tenant.manager import TenantManager
from monitoring.metrics import rag_metrics, start_metrics_server

logger = logging.getLogger(__name__)


class ChinesePDFRAGPipeline:
    """
    国产开源全栈 RAG 流水线
    - Embedding: BGE-M3（BAAI，MIT License）
    - Reranker:  BGE-Reranker-v2-m3（BAAI）
    - Vision:    InternVL2 / Qwen2-VL（本地 Ollama）
    - OCR:       PaddleOCR 3.x（百度，Apache 2.0）
    - VectorDB:  Milvus 2.4+（Zilliz，Apache 2.0）
    - BM25:      Milvus 内置 + 结巴分词
    """
    def __init__(self, config: dict):
        cfg = config
        # 模型初始化（可 GPU 加速）
        self.embedder = BGEEmbedder(
            model_path=cfg.get("bge_m3_path", "BAAI/bge-m3"),
            device=cfg.get("device", "cuda"),
        )
        self.reranker = BGEReranker(
            model_path=cfg.get("reranker_path", "BAAI/bge-reranker-v2-m3"),
            device=cfg.get("device", "cuda"),
        )
        self.vision = InternVLVision(
            ollama_url=cfg.get("ollama_url", "http://localhost:11434"),
            model=cfg.get("vision_model", "internvl2:8b"),
        )
        self.ocr = PaddleOCREngine(use_gpu=cfg.get("device", "cuda") == "cuda")

        # 存储层
        self.store = MilvusMultiTenantStore(
            host=cfg.get("milvus_host", "localhost"),
            port=cfg.get("milvus_port", 19530),
        )
        # 搜索引擎
        self.search_engine = HybridSearchEngine(
            embedder=self.embedder,
            reranker=self.reranker,
            store=self.store,
        )
        # 多租户管理
        self.tenant_mgr = TenantManager(
            redis_url=cfg.get("redis_url", "redis://localhost:6379/0"),
        )

        self.executor = ThreadPoolExecutor(max_workers=cfg.get("workers", 4))

        # 启动监控
        start_metrics_server(port=cfg.get("metrics_port", 8000))

    async def ingest_pdf(
        self,
        pdf_path: str,
        tenant_id: str,
        doc_metadata: dict = None,
    ) -> dict:
        """异步入库单个 PDF，带配额检查和监控"""
        # 配额检查
        if not self.tenant_mgr.check_doc_quota(tenant_id):
            raise PermissionError(f"租户 {tenant_id} 文档配额已满")

        t0 = time.perf_counter()
        doc_metadata = doc_metadata or {}
        doc_id = hashlib.md5(f"{tenant_id}:{pdf_path}".encode()).hexdigest()[:16]
        doc_metadata.update({
            "doc_id": doc_id,
            "doc_title": doc_metadata.get("title", Path(pdf_path).stem),
            "tenant_id": tenant_id,
        })

        try:
            # 1. 解析
            from document_analyzer import PDFAnalyzer
            analyzer = PDFAnalyzer(pdf_path)
            if not analyzer.is_text_extractable():
                # 扫描件：OCR 路径
                elements = await self._ocr_pipeline(pdf_path, doc_metadata)
            else:
                elements = analyzer.get_page_elements()

            # 2. 并发处理各元素
            all_chunks = await self._process_elements_async(
                elements, pdf_path, doc_metadata
            )

            # 3. 向量化（批量）
            texts = [c["content"] for c in all_chunks]
            embed_out = self.embedder.encode(texts, batch_size=32)
            dense_vecs = embed_out["dense"]

            # 4. BM25 fit（增量，首次需全量）
            self.store.fit_bm25(texts)

            # 5. 写入 Milvus（多租户 partition）
            inserted = self.store.upsert(all_chunks, dense_vecs, tenant_id)

            elapsed = time.perf_counter() - t0
            # 统计各类型 chunk 数量
            chunk_counts = {}
            for c in all_chunks:
                ct = c["chunk_type"]
                chunk_counts[ct] = chunk_counts.get(ct, 0) + 1

            rag_metrics.record_ingest(
                tenant_id=tenant_id,
                status="success",
                latency_s=elapsed,
                chunk_counts=chunk_counts,
            )
            self.tenant_mgr.increment_doc_count(tenant_id)

            return {
                "doc_id": doc_id,
                "tenant_id": tenant_id,
                "total_chunks": inserted,
                "chunk_counts": chunk_counts,
                "elapsed_s": round(elapsed, 2),
            }

        except Exception as e:
            rag_metrics.record_error(tenant_id, type(e).__name__)
            logger.error(f"入库失败 [{tenant_id}] {pdf_path}: {e}", exc_info=True)
            rag_metrics.record_ingest(
                tenant_id=tenant_id, status="error",
                latency_s=time.perf_counter()-t0, chunk_counts={},
            )
            raise

    def search(
        self,
        query: str,
        tenant_id: str,
        api_key: str,
        top_k: int = 5,
        rerank: bool = True,
    ) -> list[dict]:
        """带鉴权+限流的检索入口"""
        # 鉴权
        if not self.tenant_mgr.authenticate(tenant_id, api_key):
            raise PermissionError("API Key 无效")
        # 限流
        if not self.tenant_mgr.check_qps(tenant_id):
            raise RuntimeError(f"租户 {tenant_id} QPS 超限")

        results = self.search_engine.search(
            query=query,
            tenant_id=tenant_id,
            top_k=top_k,
            rerank=rerank,
        )
        return [
            {
                "content": r.content,
                "source": r.source_label,
                "doc_id": r.doc_id,
                "page_num": r.page_num,
                "chunk_type": r.chunk_type,
                "rerank_score": round(r.rerank_score, 4),
                "rrf_score": round(r.rrf_score, 6),
            }
            for r in results
        ]

    async def _process_elements_async(self, elements, pdf_path, meta):
        """并发处理文本/表格/图片元素"""
        from document_analyzer.document_analyzer import DocumentElement
        from document_analyzer.table_extractor import EnterpriseTableExtractor
        from document_analyzer.chunker import SemanticChunker

        table_ext = EnterpriseTableExtractor(vision_model=self.vision)
        chunker = SemanticChunker()
        tasks = []
        loop = asyncio.get_event_loop()

        for el in elements:
            m = {**meta, "page_num": el.page_num}
            if el.element_type == "text":
                tasks.append(loop.run_in_executor(
                    self.executor,
                    lambda e=el, mm=m: chunker.chunk_text(e.content, mm)
                ))
            elif el.element_type == "table":
                tasks.append(loop.run_in_executor(
                    self.executor,
                    lambda e=el, mm=m: self._handle_table(
                        table_ext, chunker, pdf_path, e, mm
                    )
                ))
            elif el.element_type == "image" and el.raw_data:
                tasks.append(loop.run_in_executor(
                    self.executor,
                    lambda e=el, mm=m: self._handle_image(chunker, e, mm)
                ))

        groups = await asyncio.gather(*tasks, return_exceptions=True)
        all_chunks = []
        for g in groups:
            if isinstance(g, list):
                all_chunks.extend(g)
        return all_chunks

    def _handle_table(self, table_ext, chunker, pdf_path, el, meta):
        import time
        results = table_ext.extract(pdf_path, el.page_num)
        chunks = []
        for i, t in enumerate(results):
            rag_metrics.record_table_method(meta["tenant_id"], t["method"])
            m = {**meta, "table_idx": i, "extraction_method": t["method"]}
            chunks.extend(chunker.chunk_table(t["markdown"], m))
        return chunks

    def _handle_image(self, chunker, el, meta):
        import base64, time
        try:
            img_bytes = base64.b64decode(el.raw_data) if isinstance(
                el.raw_data, str) else el.raw_data
            t0 = time.perf_counter()
            desc = self.vision.describe_image(img_bytes)
            rag_metrics.record_vision(
                model=self.vision.model,
                latency_s=time.perf_counter()-t0,
            )
            return chunker.chunk_image(desc, meta)
        except Exception as e:
            logger.warning(f"图片处理失败: {e}")
            return []


# ─── 使用示例 ──────────────────────────────────────────────────────────────────

async def main():
    config = {
        "bge_m3_path":    "BAAI/bge-m3",
        "reranker_path":  "BAAI/bge-reranker-v2-m3",
        "vision_model":   "internvl2:8b",
        "ollama_url":     "http://localhost:11434",
        "milvus_host":    "localhost",
        "milvus_port":    19530,
        "redis_url":      "redis://localhost:6379/0",
        "device":         "cpu",
        "workers":        4,
        "metrics_port":   8000,
    }

    pipeline = ChinesePDFRAGPipeline(config)

    # 创建租户
    pipeline.tenant_mgr.create_tenant(
        tenant_id="company_a",
        name="A 公司",
        api_key="secret-key-a",
        max_docs=50_000,
        max_qps=50,
    )

    # 入库
    result = await pipeline.ingest_pdf(
        "annual_report_2024.pdf",
        tenant_id="company_a",
        doc_metadata={"title": "2024年度报告", "year": 2024},
    )
    print(f"入库完成: {result}")

    # 混合检索（自动鉴权+限流+混合检索+重排序）
    hits = pipeline.search(
        query="2024年营业收入同比增长了多少",
        tenant_id="company_a",
        api_key="secret-key-a",
        top_k=5,
        rerank=True,
    )
    for h in hits:
        print(f"[{h['rerank_score']:.3f}] {h['source']} - {h['content'][:80]}...")


if __name__ == "__main__":
    asyncio.run(main())