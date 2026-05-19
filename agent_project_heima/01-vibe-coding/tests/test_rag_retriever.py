"""RAG 检索模块单元测试（Mock Embedding / Milvus / MySQL）"""
from unittest.mock import MagicMock, patch  # Mock 工具

import pytest  # pytest 框架


# ── 辅助工厂函数 ──────────────────────────────────────────────────────────────

def _make_milvus_hit(parent_id: str, subject: str = "java", content: str = "sample") -> dict:
    """构造模拟的 Milvus 搜索命中结果"""
    return {"entity": {"parent_id": parent_id, "subject": subject, "content": content}}


def _make_parent_row(pid: str, subject: str = "java", content: str = "parent content") -> dict:
    """构造模拟的 MySQL 父块记录"""
    return {"id": pid, "subject": subject, "content": content}


# ── Embedding 单元测试 ────────────────────────────────────────────────────────

class TestEmbedQuery:
    @patch("app.modules.rag_retriever.TextEmbedding.call")
    def test_returns_vector_on_success(self, mock_call):
        mock_call.return_value = MagicMock(
            status_code=200,
            output={"embeddings": [{"embedding": [0.1] * 1536}]},
        )
        from app.modules.rag_retriever import _embed_query
        result = _embed_query("test question")
        assert len(result) == 1536  # 向量维度应为 1536

    @patch("app.modules.rag_retriever.TextEmbedding.call")
    def test_raises_on_api_failure(self, mock_call):
        mock_call.return_value = MagicMock(status_code=401, message="Unauthorized")
        from app.modules.rag_retriever import _embed_query
        with pytest.raises(RuntimeError):  # API 失败时应抛出 RuntimeError
            _embed_query("test")


# ── 父块查询单元测试 ──────────────────────────────────────────────────────────

class TestFetchParentChunks:
    def test_returns_empty_for_empty_ids(self):
        from app.modules.rag_retriever import _fetch_parent_chunks
        result = _fetch_parent_chunks([])
        assert result == []  # 空 ID 列表返回空结果

    @patch("app.modules.rag_retriever.mysql_client")
    def test_queries_correct_ids(self, mock_mysql):
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [_make_parent_row("p1")]
        mock_mysql.cursor.return_value = mock_cursor

        from app.modules.rag_retriever import _fetch_parent_chunks
        result = _fetch_parent_chunks(["p1"])
        assert len(result) == 1         # 查到 1 条
        assert result[0]["id"] == "p1"  # ID 一致

    @patch("app.modules.rag_retriever.mysql_client")
    def test_returns_empty_on_exception(self, mock_mysql):
        mock_mysql.cursor.side_effect = Exception("db error")
        from app.modules.rag_retriever import _fetch_parent_chunks
        result = _fetch_parent_chunks(["p1"])
        assert result == []  # 异常时返回空列表（不崩溃）


# ── 检索主流程测试 ────────────────────────────────────────────────────────────

class TestRetrieve:
    @patch("app.modules.rag_retriever._fetch_parent_chunks")
    @patch("app.modules.rag_retriever.milvus_client")
    @patch("app.modules.rag_retriever._embed_query")
    def test_returns_context_and_sources(self, mock_embed, mock_milvus, mock_fetch):
        mock_embed.return_value = [0.1] * 1536
        mock_milvus.search.return_value = [[_make_milvus_hit("p1"), _make_milvus_hit("p2")]]
        mock_fetch.return_value = [
            _make_parent_row("p1", content="Java HashMap 内容"),
            _make_parent_row("p2", content="Java HashTable 内容"),
        ]

        from app.modules.rag_retriever import retrieve
        result = retrieve("HashMap 和 HashTable 区别", subject="java")

        assert "context" in result   # 必须包含 context 字段
        assert "sources" in result   # 必须包含 sources 字段
        assert "Java HashMap" in result["context"]  # 上下文包含父块内容
        assert len(result["sources"]) == 2  # 两个父块来源

    @patch("app.modules.rag_retriever._embed_query", side_effect=RuntimeError("embedding failed"))
    def test_returns_empty_when_embedding_fails(self, mock_embed):
        from app.modules.rag_retriever import retrieve
        result = retrieve("test question")
        assert result["context"] == ""  # Embedding 失败时上下文为空
        assert result["sources"] == []  # 来源列表为空

    @patch("app.modules.rag_retriever._fetch_parent_chunks")
    @patch("app.modules.rag_retriever.milvus_client")
    @patch("app.modules.rag_retriever._embed_query")
    def test_deduplicates_parent_ids(self, mock_embed, mock_milvus, mock_fetch):
        mock_embed.return_value = [0.1] * 1536
        # 三个命中都指向同一父块 p1
        mock_milvus.search.return_value = [[
            _make_milvus_hit("p1"), _make_milvus_hit("p1"), _make_milvus_hit("p1"),
        ]]
        mock_fetch.return_value = [_make_parent_row("p1")]

        from app.modules.rag_retriever import retrieve
        retrieve("test")
        called_ids = mock_fetch.call_args[0][0]  # 取第一个位置参数（ID 列表）
        assert called_ids.count("p1") == 1  # 重复 ID 应被去重

    @patch("app.modules.rag_retriever._fetch_parent_chunks")
    @patch("app.modules.rag_retriever.milvus_client")
    @patch("app.modules.rag_retriever._embed_query")
    def test_respects_candidate_m_limit(self, mock_embed, mock_milvus, mock_fetch):
        from app import config
        mock_embed.return_value = [0.1] * 1536
        # 构造超过 candidate_m 数量的命中
        many_hits = [_make_milvus_hit(f"p{i}") for i in range(20)]
        mock_milvus.search.return_value = [many_hits]
        mock_fetch.return_value = []

        from app.modules.rag_retriever import retrieve
        retrieve("test")
        called_ids = mock_fetch.call_args[0][0]
        assert len(called_ids) <= config.retrieval.candidate_m  # 不超过 candidate_m

    @patch("app.modules.rag_retriever._fetch_parent_chunks")
    @patch("app.modules.rag_retriever.milvus_client")
    @patch("app.modules.rag_retriever._embed_query")
    def test_subject_filter_passed_to_milvus(self, mock_embed, mock_milvus, mock_fetch):
        mock_embed.return_value = [0.1] * 1536
        mock_milvus.search.return_value = [[]]
        mock_fetch.return_value = []

        from app.modules.rag_retriever import retrieve
        retrieve("test", subject="java")
        call_kwargs = mock_milvus.search.call_args[1]
        assert call_kwargs["filter_expr"] == "source == 'java'"  # 学科过滤正确传递

    @patch("app.modules.rag_retriever._fetch_parent_chunks")
    @patch("app.modules.rag_retriever.milvus_client")
    @patch("app.modules.rag_retriever._embed_query")
    def test_excerpt_truncated_to_100_chars(self, mock_embed, mock_milvus, mock_fetch):
        mock_embed.return_value = [0.1] * 1536
        mock_milvus.search.return_value = [[_make_milvus_hit("p1")]]
        long_content = "A" * 200  # 超过 100 字符的内容
        mock_fetch.return_value = [_make_parent_row("p1", content=long_content)]

        from app.modules.rag_retriever import retrieve
        result = retrieve("test")
        assert result["sources"][0]["excerpt"].endswith("...")  # 摘要以 ... 结尾
        assert len(result["sources"][0]["excerpt"]) <= 103      # 100 字符 + "..."
