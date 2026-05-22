"""
app/ingest 模块单元测试。

全部使用 Mock，不依赖真实数据库和 DashScope API。
"""

import os  # 临时文件路径
import tempfile  # 临时文件/目录
from unittest.mock import MagicMock, patch, call  # Mock 工具

import pytest  # 测试框架


# --------------------------------------------------------------------------- #
# file_parser
# --------------------------------------------------------------------------- #

class TestFileParser:
    """file_parser.parse_file 各格式分支测试。"""

    def test_unsupported_extension_returns_empty(self, tmp_path):
        """不支持的格式返回空串而不抛异常。"""
        from app.ingest.file_parser import parse_file
        f = tmp_path / "test.xyz"
        f.write_text("hello")  # 写入任意内容
        result = parse_file(str(f))
        assert result == ""  # 不支持格式返回空串

    def test_file_not_found_raises(self):
        """文件不存在时抛出 FileNotFoundError。"""
        from app.ingest.file_parser import parse_file
        with pytest.raises(FileNotFoundError):
            parse_file("/nonexistent/path/file.pdf")

    def test_parse_txt(self, tmp_path):
        """TXT 文件正确读取内容。"""
        from app.ingest.file_parser import parse_file
        f = tmp_path / "test.txt"
        f.write_text("你好世界\n测试内容", encoding="utf-8")
        result = parse_file(str(f))
        assert "你好世界" in result  # 内容完整读取
        assert "测试内容" in result

    def test_parse_md(self, tmp_path):
        """Markdown 文件正确读取内容。"""
        from app.ingest.file_parser import parse_file
        f = tmp_path / "test.md"
        f.write_text("# 标题\n\n段落内容", encoding="utf-8")
        result = parse_file(str(f))
        assert "标题" in result

    def test_parse_csv(self, tmp_path):
        """CSV 文件解析为管道符分隔文本。"""
        from app.ingest.file_parser import parse_file
        f = tmp_path / "data.csv"
        f.write_text("姓名,年龄\n张三,18\n李四,20", encoding="utf-8")
        result = parse_file(str(f))
        assert "姓名" in result  # 列头存在
        assert "张三" in result  # 数据行存在
        assert "|" in result  # 管道符分隔

    @patch("pypdf.PdfReader")
    def test_parse_pdf(self, mock_reader_cls, tmp_path):
        """PDF 解析调用 pypdf.PdfReader 并拼接页面文本。"""
        from app.ingest.file_parser import parse_file
        # 模拟两页
        page1 = MagicMock()
        page1.extract_text.return_value = "第一页内容"
        page2 = MagicMock()
        page2.extract_text.return_value = "第二页内容"
        mock_reader_cls.return_value.pages = [page1, page2]

        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF-1.4")  # 写入伪 PDF 头
        result = parse_file(str(f))

        assert "第一页内容" in result  # 两页都出现
        assert "第二页内容" in result

    def test_parse_xlsx(self, tmp_path):
        """Excel 文件解析，验证列头和数据行出现在输出中。"""
        import openpyxl  # noqa
        from app.ingest.file_parser import parse_file

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(["课程", "学时"])  # 列头
        ws.append(["Python基础", 40])  # 数据行
        path = str(tmp_path / "data.xlsx")
        wb.save(path)

        result = parse_file(path)
        assert "课程" in result
        assert "Python基础" in result

    @patch("docx.Document")
    def test_parse_docx(self, mock_doc_cls, tmp_path):
        """DOCX 解析调用 python-docx Document 并提取段落文本。"""
        from app.ingest.file_parser import parse_file
        from unittest.mock import PropertyMock
        from lxml import etree  # docx 依赖 lxml

        # 构造最小 body：一个 <w:p><w:r><w:t>测试段落</w:t></w:r></w:p>
        WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        body = etree.Element("body")
        p = etree.SubElement(body, f"{{{WORD_NS}}}p")
        r = etree.SubElement(p, f"{{{WORD_NS}}}r")
        t = etree.SubElement(r, f"{{{WORD_NS}}}t")
        t.text = "测试段落"

        mock_doc = MagicMock()
        mock_doc.element.body = body
        mock_doc_cls.return_value = mock_doc

        f = tmp_path / "test.docx"
        f.write_bytes(b"PK")  # 写入伪 docx 头（zip）
        result = parse_file(str(f))
        assert "测试段落" in result

    def test_supported_extensions_set(self):
        """SUPPORTED_EXTENSIONS 包含预期的所有格式。"""
        from app.ingest.file_parser import SUPPORTED_EXTENSIONS
        expected = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv",
                    ".pptx", ".txt", ".md", ".png", ".jpg", ".jpeg"}
        assert expected.issubset(SUPPORTED_EXTENSIONS)  # 预期格式都在支持列表中


# --------------------------------------------------------------------------- #
# text_chunker
# --------------------------------------------------------------------------- #

class TestTextChunker:
    """text_chunker.chunk_document 分块逻辑测试。"""

    def test_empty_text_returns_empty_list(self):
        """空文本返回空列表。"""
        from app.ingest.text_chunker import chunk_document
        assert chunk_document("") == []
        assert chunk_document("   ") == []

    def test_short_text_single_chunk(self):
        """短文本（< parent_chunk_size）生成 1 个父块。"""
        from app.ingest.text_chunker import chunk_document
        result = chunk_document("这是一段很短的文字。")
        assert len(result) == 1  # 只有一个父块
        assert result[0].index == 0  # 索引从 0 开始

    def test_long_text_multiple_chunks(self):
        """超过 parent_chunk_size 的文本生成多个父块。"""
        from app.ingest.text_chunker import chunk_document
        # 生成 3000 字的文本（parent_chunk_size = 1200）
        long_text = "这是测试内容。" * 500
        result = chunk_document(long_text)
        assert len(result) >= 2  # 至少产生 2 个父块

    def test_chunk_index_sequential(self):
        """父块 index 字段从 0 开始连续递增。"""
        from app.ingest.text_chunker import chunk_document
        long_text = "内容行。\n" * 300
        result = chunk_document(long_text)
        for i, chunk in enumerate(result):
            assert chunk.index == i  # index 与位置一致

    def test_parent_chunk_has_children(self):
        """每个父块至少有一个子块（短父块退化为 1 个子块）。"""
        from app.ingest.text_chunker import chunk_document
        result = chunk_document("测试文本。" * 50)
        for pc in result:
            assert len(pc.children) >= 1  # 子块非空

    def test_children_text_subset_of_parent(self):
        """子块文本是父块文本的子集（每个子块内容出现在父块中）。"""
        from app.ingest.text_chunker import chunk_document
        result = chunk_document("ABC DEF GHI。" * 200)
        for pc in result:
            for child in pc.children:
                # 子块去重叠后核心内容应包含在父块中
                core = child[:50]  # 取子块前 50 字符检查
                assert core in pc.text or len(core) == 0  # 核心内容在父块中


# --------------------------------------------------------------------------- #
# embedder
# --------------------------------------------------------------------------- #

class TestEmbedder:
    """embedder.embed_texts 测试（Mock DashScope API）。"""

    def test_empty_input_returns_empty(self):
        """空列表输入直接返回空列表，不调用 API。"""
        from app.ingest.embedder import embed_texts
        result = embed_texts([])
        assert result == []

    @patch("app.ingest.embedder._get_client")
    def test_returns_correct_length(self, mock_get_client):
        """返回向量数与输入文本数一致。"""
        from app.ingest.embedder import embed_texts

        # 构造 Mock 响应
        mock_embedding = MagicMock()
        mock_embedding.index = 0
        mock_embedding.embedding = [0.1] * 1536  # 1536 维向量

        mock_resp = MagicMock()
        mock_resp.data = [mock_embedding]

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_resp
        mock_get_client.return_value = mock_client

        texts = ["文本A"]
        result = embed_texts(texts)

        assert len(result) == 1  # 一条输入，一个向量
        assert len(result[0]) == 1536  # 向量维度正确

    @patch("app.ingest.embedder._get_client")
    def test_batches_large_input(self, mock_get_client):
        """超过单批上限（25）的输入被分批调用。"""
        from app.ingest.embedder import embed_texts, _BATCH_SIZE

        def make_resp(texts_batch):
            """为每批构造 Mock 响应。"""
            data = []
            for i in range(len(texts_batch)):
                e = MagicMock()
                e.index = i
                e.embedding = [0.0] * 1536
                data.append(e)
            resp = MagicMock()
            resp.data = data
            return resp

        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = lambda **kw: make_resp(kw["input"])
        mock_get_client.return_value = mock_client

        texts = [f"文本{i}" for i in range(60)]  # 60 条，超过单批 25 条上限
        result = embed_texts(texts)

        assert len(result) == 60  # 所有文本都处理了
        # 应调用 3 次（25 + 25 + 10）
        assert mock_client.embeddings.create.call_count == 3

    @patch("app.ingest.embedder._get_client")
    def test_raises_after_max_retries(self, mock_get_client):
        """API 持续失败超过重试次数后抛出 RuntimeError。"""
        from app.ingest.embedder import embed_texts

        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = ConnectionError("网络错误")
        mock_get_client.return_value = mock_client

        with pytest.raises(RuntimeError, match="向量化连续"):
            embed_texts(["测试文本"])


# --------------------------------------------------------------------------- #
# ingestor
# --------------------------------------------------------------------------- #

class TestIngestor:
    """ingestor.ingest_file 流程测试（Mock 所有外部依赖）。"""

    def _make_mysql(self):
        """构造 Mock MySQL 客户端。"""
        mock = MagicMock()
        # cursor() 是上下文管理器，返回 mock cursor
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 1  # 模拟自增 ID
        mock_cursor.fetchone.return_value = None  # 文档不存在（幂等检查通过）
        mock.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock.cursor.return_value.__exit__ = MagicMock(return_value=False)
        return mock

    def _make_milvus(self):
        """构造 Mock Milvus 客户端。"""
        mock = MagicMock()
        mock.collection_name = "edurag_bj29"
        mock_sdk = MagicMock()
        mock_sdk.list_collections.return_value = ["edurag_bj29"]  # collection 已存在
        mock._get_client.return_value = mock_sdk
        return mock

    @patch("app.ingest.ingestor.embed_texts")
    @patch("app.ingest.ingestor.parse_file")
    def test_ingest_file_success(self, mock_parse, mock_embed, tmp_path):
        """正常流程：解析 → 分块 → 向量化 → 写 MySQL → 写 Milvus 全部被调用。"""
        from app.ingest.ingestor import ingest_file

        mock_parse.return_value = "这是测试文档内容。" * 100  # 足够长触发分块
        # side_effect 根据实际子块数量返回等量向量（避免 index out of range）
        mock_embed.side_effect = lambda texts: [[0.1] * 1536 for _ in texts]

        mysql = self._make_mysql()
        milvus = self._make_milvus()

        f = tmp_path / "test.txt"
        f.write_text("dummy")  # 实际内容被 mock_parse 替换
        result = ingest_file(str(f), "ai", "人工智能", mysql, milvus)

        assert result["status"] == "ok"  # 入库成功
        assert result["parent_count"] > 0  # 有父块
        mock_embed.assert_called_once()  # 向量化被调用

    @patch("app.ingest.ingestor.parse_file")
    def test_ingest_file_empty_content_skipped(self, mock_parse, tmp_path):
        """解析后内容为空时状态为 skipped。"""
        from app.ingest.ingestor import ingest_file

        mock_parse.return_value = "   "  # 空内容
        mysql = self._make_mysql()
        milvus = self._make_milvus()

        f = tmp_path / "empty.txt"
        f.write_text("dummy")
        result = ingest_file(str(f), "ai", "人工智能", mysql, milvus)

        assert result["status"] == "skipped"

    def test_ingest_file_unsupported_format(self, tmp_path):
        """不支持的文件格式状态为 skipped，不调用 DB。"""
        from app.ingest.ingestor import ingest_file

        f = tmp_path / "data.zip"
        f.write_bytes(b"PK")
        mysql = self._make_mysql()
        milvus = self._make_milvus()
        result = ingest_file(str(f), "ai", "人工智能", mysql, milvus)

        assert result["status"] == "skipped"
        assert "不支持" in result["message"]

    @patch("app.ingest.ingestor.embed_texts")
    @patch("app.ingest.ingestor.parse_file")
    def test_ingest_file_already_exists_skipped(self, mock_parse, mock_embed, tmp_path):
        """MySQL 中已有同路径记录时状态为 skipped（幂等）。"""
        from app.ingest.ingestor import ingest_file

        mock_parse.return_value = "内容" * 100
        mock_embed.return_value = [[0.0] * 1536]

        mysql = self._make_mysql()
        # 模拟 fetchone 返回已有记录
        mock_cursor = mysql.cursor.return_value.__enter__.return_value
        mock_cursor.fetchone.return_value = {"id": 99}  # 已存在

        milvus = self._make_milvus()

        f = tmp_path / "exists.txt"
        f.write_text("dummy")
        result = ingest_file(str(f), "ai", "人工智能", mysql, milvus)

        assert result["status"] == "skipped"
        assert "幂等" in result["message"]

    @patch("app.ingest.ingestor.embed_texts")
    @patch("app.ingest.ingestor.parse_file")
    def test_ingest_file_embed_error_returns_error(self, mock_parse, mock_embed, tmp_path):
        """向量化失败时状态为 error，不写 MySQL 父块。"""
        from app.ingest.ingestor import ingest_file

        mock_parse.return_value = "内容" * 100
        mock_embed.side_effect = RuntimeError("API 调用失败")

        mysql = self._make_mysql()
        milvus = self._make_milvus()

        f = tmp_path / "fail.txt"
        f.write_text("dummy")
        result = ingest_file(str(f), "ai", "人工智能", mysql, milvus)

        assert result["status"] == "error"
        assert "API" in result["message"] or "失败" in result["message"]
