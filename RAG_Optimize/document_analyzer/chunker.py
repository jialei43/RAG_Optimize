"""
语义分块策略 —— 中文适配版

改动说明（相对原版）：
1. SemanticChunker → ChineseSemanticChunker
   - 分隔符顺序调整：中文标点（。！？；，、）优先于英文点和空格
   - 新增 _split_by_headings：先按中文标题边界大块切分，再递归细分
   - 新增 _merge_short_chunks：相邻过短 chunk 合并，避免碎片化
   - _add_context：新增 section_path（层级标题路径）、年份、标签字段
   - _generate_table_summary：完整中文模板，含列名、行数、来源、样本数据
   - 新增 _extract_keywords：jieba TextRank 提取关键词，增强 BM25 权重
   - 新增 _normalize_text：全角字符规范化、零宽字符清除、连续空行压缩
   - chunk_text 支持传入 section_path（由 document_analyzer 提供）
   - chunk_table / chunk_image 增加 section_path 和 keywords 字段
2. Chunk dataclass 新增：section_path / keywords / char_count 字段
3. chunk_id 改为内容哈希，保证幂等性
"""

import re
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ─── 可选依赖：jieba（中文分词 + 关键词提取）────────────────────────────────
try:
    import jieba
    import jieba.analyse
    _JIEBA_AVAILABLE = True
except ImportError:
    _JIEBA_AVAILABLE = False
    logger.warning("jieba 未安装，关键词提取功能不可用。pip install jieba")

# ─── 中文标题正则（与 document_analyzer 保持一致）────────────────────────────
_HEADING_RE = re.compile(
    r'^('
    r'第\s*[一二三四五六七八九十百千\d]+\s*[章节篇条款部分]'
    r'|[一二三四五六七八九十]+[、．.]'
    r'|\d+[．.、]'
    r'|\d+(\.\d+)+'
    r'|[（(][一二三四五六七八九十\d]+[）)]'
    r')\s*.{1,50}$'
)


@dataclass
class Chunk:
    """文档块数据类（中文适配版）"""
    content: str
    chunk_type: str             # text / title / table / table_summary / image
    metadata: dict
    doc_id: str
    chunk_id: str               # 基于内容哈希，保证幂等
    # ── 新增字段 ──────────────────────────────────────────────────────────────
    section_path: list[str] = field(default_factory=list)  # 所属章节路径
    keywords: list[str] = field(default_factory=list)      # jieba 关键词
    char_count: int = 0                                    # 字符数（中文≈token）


class ChineseSemanticChunker:
    """
    中文企业级语义分块器

    分割优先级（从粗到细）：
        段落（\\n\\n） > 中文句号/叹号/问号 > 分号 > 逗号/顿号 > 空格 > 字符

    与原版 SemanticChunker 的主要差异：
    - 分隔符表中文优先，英文点号降权
    - 先按标题边界大块切分，再对每段递归细化
    - 短块合并策略防止碎片
    - 上下文前缀注入中文层级路径
    - 表格摘要使用中文自然语言模板
    - jieba 关键词提取增强 BM25
    """

    # 分隔符优先级：中文标点 > 英文标点 > 空白 > 字符
    _SEPARATORS = [
        "\n\n",   # 空行（段落边界，最强）
        "\n",     # 换行
        "。",     # 中文句号
        "！",     # 中文叹号
        "？",     # 中文问号
        "；",     # 中文分号
        "，",     # 中文逗号
        "、",     # 顿号
        "…",      # 省略号
        ".",      # 英文句号
        " ",      # 空格（英文混排）
        "",       # 字符级兜底
    ]

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        min_chunk_size: int = 50,        # 中文文档更紧凑，降低最小阈值
        max_chunk_size: int = 1024,      # 硬上限，防止超长块
        extract_keywords: bool = True,
        keyword_topk: int = 8,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.extract_keywords = extract_keywords and _JIEBA_AVAILABLE
        self.keyword_topk = keyword_topk

    # ─── 公共入口 ──────────────────────────────────────────────────────────────

    def chunk_text(
        self,
        text: str,
        metadata: dict,
        section_path: Optional[list[str]] = None,
    ) -> list[Chunk]:
        """
        文本 → Chunk 列表（中文语义递归分块）

        参数：
            text:         原始文本
            metadata:     文档元数据（doc_id / doc_title / page_num 等）
            section_path: 所属章节路径（由 document_analyzer 提供）
        """
        if not text or not text.strip():
            return []

        text = self._normalize_text(text)
        section_path = section_path or []

        # Step1：按中文标题边界切分为若干大段
        sections = self._split_by_headings(text)
        all_chunks: list[Chunk] = []

        for sec_title, sec_text in sections:
            sec_path = section_path + ([sec_title] if sec_title else [])
            if not sec_text.strip():
                continue

            # Step2：递归细化分块
            raw_chunks = self._recursive_split(sec_text, self._SEPARATORS)

            # Step3：合并过短的相邻块
            merged = self._merge_short_chunks(raw_chunks)

            for i, chunk_text in enumerate(merged):
                chunk_text = chunk_text.strip()
                if len(chunk_text) < self.min_chunk_size:
                    continue

                chunk_meta = {**metadata, "section_path": sec_path}
                content_with_ctx = self._add_context(chunk_text, metadata, sec_path)
                keywords = self._extract_keywords(chunk_text)

                all_chunks.append(Chunk(
                    content=content_with_ctx,
                    chunk_type="text",
                    metadata=chunk_meta,
                    doc_id=metadata.get("doc_id", ""),
                    chunk_id=self._make_chunk_id(
                        metadata.get("doc_id", ""), metadata.get("page_num", 0), i, chunk_text
                    ),
                    section_path=sec_path,
                    keywords=keywords,
                    char_count=len(chunk_text),
                ))

        return all_chunks

    def chunk_table(
        self,
        table_markdown: str,
        metadata: dict,
        section_path: Optional[list[str]] = None,
    ) -> list[Chunk]:
        """
        表格 → [完整表格 Chunk + 中文摘要 Chunk]

        摘要 Chunk 使用自然语言描述，让用户用口语化问题也能命中表格内容
        """
        section_path = section_path or metadata.get("section_path", [])
        doc_id = metadata.get("doc_id", "")
        table_idx = metadata.get("table_idx", 0)
        page_num = metadata.get("page_num", 0)
        chunks: list[Chunk] = []

        # 主 Chunk：完整表格
        table_content = f"【表格】\n{table_markdown}"
        table_meta = {**metadata, "has_table": True, "section_path": section_path}
        chunks.append(Chunk(
            content=self._add_context(table_content, metadata, section_path),
            chunk_type="table",
            metadata=table_meta,
            doc_id=doc_id,
            chunk_id=self._make_chunk_id(doc_id, page_num, table_idx, table_markdown),
            section_path=section_path,
            keywords=self._extract_keywords(table_markdown),
            char_count=len(table_markdown),
        ))

        # 摘要 Chunk：中文自然语言描述
        summary = self._generate_table_summary(table_markdown, metadata)
        if summary:
            summary_meta = {**metadata, "is_summary": True, "section_path": section_path}
            chunks.append(Chunk(
                content=summary,
                chunk_type="table_summary",
                metadata=summary_meta,
                doc_id=doc_id,
                chunk_id=self._make_chunk_id(doc_id, page_num, table_idx, summary),
                section_path=section_path,
                keywords=self._extract_keywords(summary),
                char_count=len(summary),
            ))

        return chunks

    def chunk_image(
        self,
        description: str,
        metadata: dict,
        section_path: Optional[list[str]] = None,
    ) -> list[Chunk]:
        """图片 Vision 描述 → Chunk"""
        section_path = section_path or metadata.get("section_path", [])
        doc_id = metadata.get("doc_id", "")
        page_num = metadata.get("page_num", 0)

        content = f"【图片描述】\n{description}"
        return [Chunk(
            content=self._add_context(content, metadata, section_path),
            chunk_type="image",
            metadata={**metadata, "has_image": True, "section_path": section_path},
            doc_id=doc_id,
            chunk_id=self._make_chunk_id(doc_id, page_num, 0, description),
            section_path=section_path,
            keywords=self._extract_keywords(description),
            char_count=len(description),
        )]

    # ─── 文本规范化 ────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        中文文本规范化

        处理项：
        - 统一换行符（\\r\\n → \\n）
        - 去除行尾多余空格
        - 压缩连续空行（3行以上 → 2行）
        - 去除零宽字符（\\u200b 等）
        - 去除非打印控制字符（保留 \\n \\t）
        """
        # 统一换行
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # 去行尾空格
        text = "\n".join(line.rstrip() for line in text.split("\n"))
        # 压缩连续空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 去零宽字符
        text = re.sub(r'[\u200b\u200c\u200d\ufeff\u00ad]', '', text)
        # 去非打印控制字符（保留 \n \t）
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        return text.strip()

    # ─── 按标题边界预切分 ─────────────────────────────────────────────────────

    def _split_by_headings(self, text: str) -> list[tuple[str, str]]:
        """
        按中文标题边界将文本预切分为 (title, content) 列表

        未命中标题的段落归入 ("", content)
        """
        lines = text.split("\n")
        sections: list[tuple[str, list[str]]] = [("", [])]

        for line in lines:
            stripped = line.strip()
            if stripped and self._is_heading_line(stripped):
                sections.append((stripped, []))
            else:
                sections[-1][1].append(line)

        return [
            (title, "\n".join(body_lines).strip())
            for title, body_lines in sections
            if "\n".join(body_lines).strip()
        ]

    @staticmethod
    def _is_heading_line(text: str) -> bool:
        """判断单行是否为中文标题"""
        return len(text) <= 60 and bool(_HEADING_RE.match(text))

    # ─── 递归分块 ─────────────────────────────────────────────────────────────

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        """按优先级分隔符递归分割文本"""
        if not text.strip():
            return []
        if len(text) <= self.chunk_size:
            return [text]
        if not separators:
            # 字符级兜底：带 overlap 的滑动窗口
            return [
                text[i:i + self.chunk_size]
                for i in range(0, len(text), max(1, self.chunk_size - self.chunk_overlap))
            ]

        sep = separators[0]
        rest = separators[1:]

        # 空字符串分隔符 → 逐字符切
        if sep == "":
            return self._recursive_split(text, rest)

        parts = text.split(sep)
        if len(parts) == 1:
            # 当前分隔符不存在，尝试下一级
            return self._recursive_split(text, rest)

        chunks: list[str] = []
        current = ""

        for part in parts:
            # 拼接时恢复分隔符（语义完整性）
            candidate = current + part + sep if current else part + sep
            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current.strip():
                    if len(current) > self.max_chunk_size:
                        chunks.extend(self._recursive_split(current.strip(), rest))
                    else:
                        chunks.append(current.strip())
                # part 本身超长，继续递归
                if len(part) > self.chunk_size:
                    sub = self._recursive_split(part, rest)
                    if sub:
                        chunks.extend(sub[:-1])
                        # 保留末尾块作为新 current 的起点（overlap 效果）
                        tail = sub[-1]
                        current = tail[-self.chunk_overlap:] if len(tail) > self.chunk_overlap else tail
                    else:
                        current = ""
                else:
                    current = part + sep

        if current.strip():
            if len(current) > self.max_chunk_size:
                chunks.extend(self._recursive_split(current.strip(), rest))
            else:
                chunks.append(current.strip())

        return chunks

    # ─── 短块合并 ─────────────────────────────────────────────────────────────

    def _merge_short_chunks(self, chunks: list[str]) -> list[str]:
        """
        将相邻的过短块合并，防止碎片化

        策略：
        - 当前块 < min_chunk_size → 尝试追加到前块
        - 前块 < min_chunk_size   → 尝试与当前块合并
        - 合并后超过 max_chunk_size → 放弃合并，各自独立
        """
        if not chunks:
            return []

        merged = [chunks[0]]
        for chunk in chunks[1:]:
            last = merged[-1]
            if len(chunk.strip()) < self.min_chunk_size:
                candidate = last + "\n" + chunk
                if len(candidate) <= self.max_chunk_size:
                    merged[-1] = candidate
                    continue
            elif len(last.strip()) < self.min_chunk_size:
                candidate = last + "\n" + chunk
                if len(candidate) <= self.max_chunk_size:
                    merged[-1] = candidate
                    continue
            merged.append(chunk)

        return merged

    # ─── 上下文前缀注入 ───────────────────────────────────────────────────────

    @staticmethod
    def _add_context(
        chunk_text: str,
        metadata: dict,
        section_path: list[str],
    ) -> str:
        """
        在块头部注入结构化上下文前缀

        前缀会被一起向量化，使同文档相近章节的向量空间更聚集，
        跨页检索时语义边界更清晰。

        格式示例：
            文档：2024年度报告 | 章节：第二章 > 2.1 财务分析 | 页码：8

        相对原版新增字段：
        - section_path（层级路径，用 > 连接）
        - year（年份，用于时效性过滤）
        - tags（业务标签）
        - department（部门）
        """
        parts: list[str] = []

        if metadata.get("doc_title"):
            parts.append(f"文档：{metadata['doc_title']}")
        if metadata.get("department"):
            parts.append(f"部门：{metadata['department']}")
        if metadata.get("year"):
            parts.append(f"年份：{metadata['year']}")
        if section_path:
            parts.append(f"章节：{' > '.join(section_path)}")
        elif metadata.get("section_title"):
            parts.append(f"章节：{metadata['section_title']}")
        if metadata.get("page_num"):
            parts.append(f"页码：{metadata['page_num']}")
        if metadata.get("tags"):
            tags = metadata["tags"]
            tag_str = "、".join(tags) if isinstance(tags, list) else str(tags)
            parts.append(f"标签：{tag_str}")

        if not parts:
            return chunk_text

        prefix = " | ".join(parts)
        return f"{prefix}\n\n{chunk_text}"

    # ─── 中文表格摘要生成 ─────────────────────────────────────────────────────

    @staticmethod
    def _generate_table_summary(markdown: str, metadata: dict = None) -> str:
        """
        从 Markdown 表格生成中文自然语言摘要

        目标：用户用口语问题（"营收增长了多少"）也能命中表格内容

        相对原版改动：
        - 完整中文模板（原版只有列名+行数）
        - 新增来源信息（文档名、页码、年份）
        - 新增前3行样本数据展示
        - 过滤 Markdown 分隔行（| --- | --- |）
        """
        metadata = metadata or {}
        lines = [l.strip() for l in markdown.split("\n") if l.strip() and "|" in l]
        if not lines:
            return ""

        # 提取列名
        header_cells = [h.strip() for h in lines[0].split("|") if h.strip()]

        # 过滤分隔行（全是 -、: 的行）
        data_lines = [
            l for l in lines[1:]
            if not re.match(r'^[\s|:\-]+$', l)
        ]
        row_count = len(data_lines)

        # 取前3行样本数据
        sample_rows: list[str] = []
        for dl in data_lines[:3]:
            cells = [c.strip() for c in dl.split("|") if c.strip()]
            if cells:
                sample_rows.append("、".join(cells[:4]))

        # 来源描述
        source_parts: list[str] = []
        if metadata.get("doc_title"):
            source_parts.append(metadata["doc_title"])
        if metadata.get("year"):
            source_parts.append(f"{metadata['year']}年")
        if metadata.get("page_num"):
            source_parts.append(f"第{metadata['page_num']}页")
        source_str = "".join(source_parts)

        # 列名描述
        col_str = "、".join(header_cells[:6])
        if len(header_cells) > 6:
            col_str += "等"

        summary = (
            f"{source_str}表格，"
            f"包含{len(header_cells)}列：{col_str}，"
            f"共{row_count}行数据。"
        )
        if sample_rows:
            summary += f"示例数据：{sample_rows[0]}。"

        return summary

    # ─── 关键词提取 ───────────────────────────────────────────────────────────

    def _extract_keywords(self, text: str) -> list[str]:
        """
        jieba TextRank 提取关键词

        用途：
        1. BM25 权重增强（写入 Milvus 元数据，供稀疏检索参考）
        2. 过滤检索结果时的相关性辅助判断
        3. 调试可解释性

        jieba 不可用时静默返回空列表
        """
        if not self.extract_keywords or not text.strip():
            return []
        try:
            keywords = jieba.analyse.textrank(
                text,
                topK=self.keyword_topk,
                withWeight=False,
                allowPOS=('ns', 'n', 'vn', 'v', 'a', 'nr', 'nt', 'nz', 'eng'),
            )
            return list(keywords)
        except Exception as e:
            logger.debug(f"关键词提取失败: {e}")
            return []

    # ─── Chunk ID 生成 ────────────────────────────────────────────────────────

    @staticmethod
    def _make_chunk_id(doc_id: str, page_num: int, idx: int, text: str) -> str:
        """
        基于内容哈希生成 chunk_id，保证幂等性

        同一文档相同内容重复入库不会产生重复向量
        """
        content_hash = hashlib.md5(
            f"{doc_id}_{page_num}_{text}".encode("utf-8")
        ).hexdigest()[:12]
        return f"{doc_id}_p{page_num}_{idx}_{content_hash}"


# ─── 向后兼容别名 ─────────────────────────────────────────────────────────────
# 保持与原版 pipeline.py 中 `from chunker import SemanticChunker` 的兼容
SemanticChunker = ChineseSemanticChunker
