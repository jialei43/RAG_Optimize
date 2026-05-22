import os  # 读取 API Key 环境变量
import re  # 正则清洗用户输入
from typing import Optional  # 类型注解

from openai import OpenAI  # OpenAI 兼容客户端（DashScope 兼容模式）

from app import config  # 读取检索参数
from app.database.milvus_client import milvus_client  # 向量检索
from app.database.mysql_client import mysql_client    # 父块内容查询
from app.modules.subject_manager import get_subject_filter_expr  # 学科过滤表达式
from app.utils.logger import get_logger  # 获取命名 Logger

logger = get_logger("modules.rag")  # 模块专属日志

_EMBED_MODEL = "text-embedding-v3"  # 与入库侧保持一致
_EMBED_DIM = 1024  # 与 Milvus collection schema 对齐
_embed_client: Optional[OpenAI] = None  # 延迟初始化，避免导入时需要 API Key


def _get_embed_client() -> OpenAI:
    """惰性初始化 Embedding 客户端。"""
    global _embed_client
    if _embed_client is None:
        _embed_client = OpenAI(
            api_key=os.environ.get("DASHSCOPE_API_KEY", config.llm.api_key),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    return _embed_client


def _embed_query(text: str) -> list[float]:
    """
    调用 DashScope text-embedding-v3 将查询文本向量化（dim=1024，与入库侧一致）。
    失败时抛出异常，由上层处理降级逻辑。
    """
    client = _get_embed_client()
    resp = client.embeddings.create(
        model=_EMBED_MODEL,
        input=[text],  # 单条输入
        dimensions=_EMBED_DIM,
    )
    return resp.data[0].embedding  # 提取向量


def _fetch_parent_chunks(parent_ids: list[str]) -> list[dict]:
    """
    根据父块 ID 列表从 MySQL 查询父块原文内容。
    返回: [{"id": ..., "subject": ..., "content": ...}, ...]
    """
    if not parent_ids:
        return []
    placeholders = ", ".join(["%s"] * len(parent_ids))  # 动态生成占位符，防 SQL 注入
    sql = f"SELECT id, subject, content FROM parent_chunk WHERE id IN ({placeholders})"
    try:
        with mysql_client.cursor() as cur:
            cur.execute(sql, parent_ids)  # 参数化查询
            rows = cur.fetchall()
        logger.debug(f"查询到 {len(rows)} 个父块")
        return rows
    except Exception as e:
        logger.error(f"父块查询失败: {e}")
        return []


def retrieve(question: str, subject: Optional[str] = None) -> dict:
    """
    RAG 检索主入口：向量化 → 子块检索 → 父块回溯 → 上下文组装。

    Args:
        question: 用户问题原文
        subject:  学科过滤代码，None 表示全学科检索

    Returns:
        {
          "context": str,        组装好的上下文字符串（送入 LLM）
          "sources": [           参考来源列表（用于响应返回）
            {"parent_id": ..., "subject": ..., "excerpt": ...}
          ]
        }
    """
    # Step 1: 向量化用户问题
    try:
        query_vector = _embed_query(question)
    except Exception as e:
        logger.warning(f"Embedding 失败，返回空上下文: {e}")
        return {"context": "", "sources": []}

    # Step 2: Milvus 子块向量检索
    filter_expr = get_subject_filter_expr(subject)  # 生成学科过滤表达式或 None
    try:
        results = milvus_client.search(
            query_vectors=[query_vector],
            limit=config.retrieval.retrieval_k,    # 初检 Top-K
            output_fields=["parent_id", "source"],  # collection schema 只有这两个标量字段
            filter_expr=filter_expr,
        )
    except Exception as e:
        logger.warning(f"Milvus 检索失败，返回空上下文: {e}")
        return {"context": "", "sources": []}

    hits = results[0] if results else []  # 取第一个查询的结果列表
    logger.debug(f"子块检索返回 {len(hits)} 条结果")

    # Step 3: 去重父块 ID，取前 candidate_m 个
    seen_ids: list[int] = []  # parent_id 为 INT64
    for hit in hits:
        pid = hit.get("entity", {}).get("parent_id") or hit.get("parent_id")
        if pid is not None and pid not in seen_ids:  # 去重
            seen_ids.append(pid)
        if len(seen_ids) >= config.retrieval.candidate_m:  # 达到目标数量后停止
            break

    # Step 4: 从 MySQL 查询父块原文
    parent_rows = _fetch_parent_chunks(seen_ids)

    # Step 5: 组装上下文与来源列表
    context_parts: list[str] = []
    sources: list[dict] = []

    for row in parent_rows:
        content = row.get("content", "")
        context_parts.append(content)  # 拼接到上下文
        sources.append({
            "parent_id": row.get("id", ""),
            "subject":   row.get("subject", ""),
            "excerpt":   content[:100] + "..." if len(content) > 100 else content,  # 摘要截断
        })

    context = "\n\n---\n\n".join(context_parts)  # 用分隔符拼接多个父块
    logger.info(f"RAG 检索完成，context 长度: {len(context)} 字符，来源: {len(sources)} 个")
    return {"context": context, "sources": sources}
