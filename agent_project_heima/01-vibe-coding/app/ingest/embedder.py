"""
向量化模块，调用 DashScope text-embedding-v3 批量生成子块向量。

批次大小限制为 25 条（DashScope API 单次上限），超出则自动分批请求。
"""

from __future__ import annotations

import logging  # 日志
import os  # 读取 API Key 环境变量
import time  # 失败重试间隔
from typing import List  # 类型注解

logger = logging.getLogger(__name__)  # 模块级 logger

_EMBED_MODEL = "text-embedding-v3"  # DashScope 向量模型
_EMBED_DIM = 1024  # text-embedding-v3 有效维度之一: 64/128/256/512/768/1024
_BATCH_SIZE = 10   # DashScope text-embedding-v3 单次最多 10 条
_RETRY_TIMES = 3  # 失败重试次数
_RETRY_DELAY = 2  # 每次重试等待秒数


def _get_client():
    """惰性初始化 OpenAI 兼容客户端（避免导入时要求 API Key）。"""
    from openai import OpenAI  # noqa: PLC0415  # 惰性导入
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "环境变量 DASHSCOPE_API_KEY 未设置，无法调用向量化接口"
        )
    return OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    对文本列表批量生成向量。

    Args:
        texts: 待向量化的文本列表（子块）

    Returns:
        与输入等长的向量列表，每个向量为长度 1536 的 float 列表。

    Raises:
        RuntimeError: API Key 未设置或多次重试后仍失败。
    """
    if not texts:
        return []  # 空输入直接返回

    client = _get_client()
    all_vectors: List[List[float]] = []

    # 按批次处理，避免超过 API 单次上限
    for batch_start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[batch_start: batch_start + _BATCH_SIZE]

        for attempt in range(_RETRY_TIMES):  # 失败重试
            try:
                resp = client.embeddings.create(
                    model=_EMBED_MODEL,
                    input=batch,
                    dimensions=_EMBED_DIM,  # 指定输出维度
                )
                # 按原始顺序排序后提取向量（API 返回顺序与输入一致，双重保险）
                sorted_data = sorted(resp.data, key=lambda d: d.index)
                all_vectors.extend(d.embedding for d in sorted_data)
                break  # 成功，跳出重试循环

            except Exception as exc:
                logger.warning(
                    "向量化第 %d 批失败 (attempt %d/%d): %s",
                    batch_start // _BATCH_SIZE + 1,
                    attempt + 1,
                    _RETRY_TIMES,
                    exc,
                )
                if attempt < _RETRY_TIMES - 1:
                    time.sleep(_RETRY_DELAY)  # 等待后重试
                else:
                    raise RuntimeError(
                        f"向量化连续 {_RETRY_TIMES} 次失败，终止入库"
                    ) from exc

    return all_vectors
