"""
父子分块策略实现。

父块（parent chunk）：大粒度，存 MySQL，送入 LLM 做上下文。
子块（child chunk）：小粒度，向量化后存 Milvus，用于语义检索。

分块参数从 config.py 读取（parent_chunk_size / child_chunk_size / chunk_overlap）。
"""

from __future__ import annotations  # 延迟注解（兼容 3.10 以下）

import re  # 中文句子边界检测
from dataclasses import dataclass  # 轻量数据容器
from typing import List  # 类型注解

from app.config import retrieval  # 统一读取配置，避免硬编码


@dataclass
class ParentChunk:
    """一个父块及其对应的子块列表。"""
    text: str  # 父块全文
    children: List[str]  # 子块文本列表（向量化对象）
    index: int  # 在文档中的顺序编号（0-based）


def _split_by_size(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    按字符数滑动窗口分块，尽量在中文句末（。！？\n）切割。

    Args:
        text:       待分块的全文
        chunk_size: 每块目标字符数
        overlap:    相邻块的重叠字符数
    """
    if not text.strip():
        return []

    # 中文标点 + 换行作为优先切分点（贪心：优先在句末切）
    sentence_end = re.compile(r"(?<=[。！？\n])")
    sentences = sentence_end.split(text)  # 按句末分割为句子列表

    chunks: List[str] = []
    buf = ""  # 当前积累缓冲
    for sent in sentences:
        if len(buf) + len(sent) <= chunk_size:
            buf += sent  # 继续积累
        else:
            if buf:
                chunks.append(buf.strip())  # 提交当前块
            # overlap: 取上一块末尾 overlap 字符作为新块开头
            overlap_text = buf[-overlap:] if overlap > 0 and buf else ""
            buf = overlap_text + sent  # 新块带重叠开头

    if buf.strip():
        chunks.append(buf.strip())  # 提交最后一块

    return chunks


def chunk_document(text: str) -> List[ParentChunk]:
    """
    对文档全文执行父子两级分块。

    父块尺寸: retrieval.parent_chunk_size（默认 1200）
    子块尺寸: retrieval.child_chunk_size（默认 300）
    重叠字符: retrieval.chunk_overlap（默认 50）

    Returns:
        ParentChunk 列表，每个 ParentChunk 含其自身文本及子块列表。
    """
    parent_chunks = _split_by_size(
        text,
        chunk_size=retrieval.parent_chunk_size,
        overlap=retrieval.chunk_overlap,
    )

    result: List[ParentChunk] = []
    for idx, parent_text in enumerate(parent_chunks):
        children = _split_by_size(
            parent_text,
            chunk_size=retrieval.child_chunk_size,
            overlap=retrieval.chunk_overlap,
        )
        result.append(ParentChunk(text=parent_text, children=children, index=idx))

    return result
