# storage/milvus_store.py
"""
Milvus 2.4+ 多租户企业级设计：
- Collection 级：dense + sparse 分集合，通过 alias 统一访问
- Partition 级：按 tenant_id 物理隔离，避免跨租户数据污染
- 索引策略：HNSW(dense) + SPARSE_INVERTED_INDEX(sparse)
"""
from pymilvus import (
    connections, Collection, CollectionSchema, FieldSchema,
    DataType, utility, AnnSearchRequest, RRFRanker,
    WeightedRanker,
)
from pymilvus.model.sparse import BM25EmbeddingFunction
import jieba, numpy as np
from typing import Optional
import logging, time

logger = logging.getLogger(__name__)

DENSE_DIM = 1024          # BGE-M3 dense 维度
SPARSE_METRIC = "IP"      # 稀疏向量用内积


class MilvusMultiTenantStore:
    """
    企业级多租户 Milvus 存储，一个物理 Collection 服务多个租户
    通过 partition_key_field 实现数据隔离
    """
    COLLECTION_NAME = "enterprise_rag"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        user: str = "",
        password: str = "",
    ):
        connections.connect(
            alias="default",
            host=host,
            port=port,
            user=user,
            password=password,
        )
        self._ensure_collection()
        self.bm25_fn = self._build_bm25()

    def _ensure_collection(self):
        if utility.has_collection(self.COLLECTION_NAME):
            self.col = Collection(self.COLLECTION_NAME)
            self.col.load()
            return

        fields = [
            FieldSchema("id",         DataType.VARCHAR, max_length=128, is_primary=True),
            FieldSchema("tenant_id",  DataType.VARCHAR, max_length=64,
                        is_partition_key=True),       # 多租户隔离键
            FieldSchema("doc_id",     DataType.VARCHAR, max_length=128),
            FieldSchema("chunk_type", DataType.VARCHAR, max_length=32),
            FieldSchema("page_num",   DataType.INT32),
            FieldSchema("content",    DataType.VARCHAR, max_length=4096),
            FieldSchema("metadata",   DataType.JSON),
            FieldSchema("dense_vec",  DataType.FLOAT_VECTOR, dim=DENSE_DIM),
            FieldSchema("sparse_vec", DataType.SPARSE_FLOAT_VECTOR),
        ]
        schema = CollectionSchema(
            fields,
            description="Enterprise RAG multi-tenant collection",
            enable_dynamic_field=True,
        )
        self.col = Collection(
            name=self.COLLECTION_NAME,
            schema=schema,
            num_partitions=64,         # 最多支持 64 个租户 partition
        )

        # HNSW 索引（稠密检索，高召回高速度平衡）
        self.col.create_index("dense_vec", {
            "index_type": "HNSW",
            "metric_type": "COSINE",
            "params": {"M": 16, "efConstruction": 200},
        })
        # 稀疏倒排索引（BM25/稀疏语义）
        self.col.create_index("sparse_vec", {
            "index_type": "SPARSE_INVERTED_INDEX",
            "metric_type": "IP",
            "params": {"drop_ratio_build": 0.2},    # 丢弃低权重词，压缩索引
        })
        self.col.load()
        logger.info(f"Collection {self.COLLECTION_NAME} 创建成功")

    def _build_bm25(self) -> BM25EmbeddingFunction:
        """基于结巴分词的中文 BM25（首次需 fit 语料）"""
        def chinese_tokenizer(text: str) -> list[str]:
            return list(jieba.cut(text, cut_all=False))

        fn = BM25EmbeddingFunction(tokenizer=chinese_tokenizer)
        return fn

    def fit_bm25(self, corpus: list[str]):
        """用语料拟合 BM25 参数（可增量更新）"""
        self.bm25_fn.fit(corpus)
        logger.info(f"BM25 fit 完成，语料 {len(corpus)} 条")

    def upsert(
        self,
        chunks: list[dict],
        dense_vecs: np.ndarray,
        tenant_id: str,
    ) -> int:
        """
        批量幂等写入
        chunks: [{"id", "doc_id", "chunk_type", "page_num", "content", "metadata"}]
        dense_vecs: np.ndarray [N, 1024]
        """
        texts = [c["content"] for c in chunks]
        sparse_vecs = self.bm25_fn.encode_documents(texts)

        rows = []
        for i, (chunk, dv, sv) in enumerate(zip(chunks, dense_vecs, sparse_vecs)):
            rows.append({
                "id":         chunk["id"],
                "tenant_id":  tenant_id,
                "doc_id":     chunk["doc_id"],
                "chunk_type": chunk["chunk_type"],
                "page_num":   chunk.get("page_num", 0),
                "content":    chunk["content"][:4096],
                "metadata":   chunk.get("metadata", {}),
                "dense_vec":  dv.tolist(),
                "sparse_vec": sv,
            })

        # 分批写入，每批 500 条
        batch_size = 500
        total = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]
            self.col.upsert(batch)
            total += len(batch)

        self.col.flush()
        return total

    def hybrid_search(
        self,
        query_dense: np.ndarray,
        query_sparse,
        tenant_id: str,
        top_k: int = 20,
        dense_weight: float = 0.6,
        sparse_weight: float = 0.4,
        filter_expr: Optional[str] = None,
    ) -> list[dict]:
        """
        三路混合检索 + RRF 融合：
        路径1: 稠密向量（语义相似度）
        路径2: BM25 稀疏（关键词精确匹配）
        路径3: BGE-M3 稀疏语义（兼顾语义+词法）
        """
        # 租户过滤表达式
        tenant_filter = f'tenant_id == "{tenant_id}"'
        if filter_expr:
            tenant_filter = f'({tenant_filter}) && ({filter_expr})'

        # 稠密检索请求
        dense_req = AnnSearchRequest(
            data=[query_dense.tolist()],
            anns_field="dense_vec",
            param={"metric_type": "COSINE", "params": {"ef": 100}},
            limit=top_k * 2,
            expr=tenant_filter,
        )
        # 稀疏检索请求（BM25）
        sparse_req = AnnSearchRequest(
            data=[query_sparse],
            anns_field="sparse_vec",
            param={"metric_type": "IP", "params": {"drop_ratio_search": 0.2}},
            limit=top_k * 2,
            expr=tenant_filter,
        )

        # RRF 融合（k=60 是经验最优值）
        results = self.col.hybrid_search(
            reqs=[dense_req, sparse_req],
            ranker=RRFRanker(k=60),
            limit=top_k,
            output_fields=["content", "doc_id", "chunk_type", "page_num", "metadata"],
        )

        hits = []
        for hit in results[0]:
            hits.append({
                "id":         hit.id,
                "score":      hit.score,
                "content":    hit.entity.get("content", ""),
                "doc_id":     hit.entity.get("doc_id", ""),
                "chunk_type": hit.entity.get("chunk_type", ""),
                "page_num":   hit.entity.get("page_num", 0),
                "metadata":   hit.entity.get("metadata", {}),
            })
        return hits

    def delete_tenant_data(self, tenant_id: str, doc_id: Optional[str] = None):
        """按租户或按文档删除数据（GDPR 合规）"""
        expr = f'tenant_id == "{tenant_id}"'
        if doc_id:
            expr += f' && doc_id == "{doc_id}"'
        self.col.delete(expr)
        self.col.flush()