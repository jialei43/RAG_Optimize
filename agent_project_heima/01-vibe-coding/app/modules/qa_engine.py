import time  # 计算响应耗时
from typing import Iterator, Optional  # 类型注解

from app.modules.llm_client import llm_client, is_greeting, get_greeting_reply  # LLM 调用与问候识别
from app.modules.rag_retriever import retrieve  # RAG 检索
from app.modules.session_manager import (  # 会话历史管理
    get_history, append_message, session_exists,
)
from app.modules.subject_manager import is_valid_subject  # 学科合法性校验
from app.utils.logger import get_logger  # 获取命名 Logger

logger = get_logger("modules.qa")  # 模块专属日志


def answer(session_id: str, question: str, subject: Optional[str] = None) -> dict:
    """
    即时问答主入口：RAG 检索 → LLM 推理 → 写入历史。

    Args:
        session_id: 会话 ID（必须已存在）
        question:   用户问题
        subject:    学科过滤代码，None 表示全学科

    Returns:
        {
          "answer": str,
          "sources": list,
          "response_time_ms": int
        }
    Raises:
        ValueError: session_id 不存在或学科代码非法
    """
    if not session_exists(session_id):  # 会话必须存在
        raise ValueError(f"会话不存在: {session_id}")

    if not is_valid_subject(subject):  # 学科代码必须合法
        raise ValueError(f"非法学科代码: {subject}")

    start = time.monotonic()  # 开始计时

    # 问候语快速识别，跳过 RAG 和 LLM
    if is_greeting(question):
        reply = get_greeting_reply()
        append_message(session_id, "user", question)       # 记录用户问候
        append_message(session_id, "assistant", reply)     # 记录系统回复
        elapsed = int((time.monotonic() - start) * 1000)
        logger.info(f"问候识别，快速返回，耗时 {elapsed}ms")
        return {"answer": reply, "sources": [], "response_time_ms": elapsed}

    # 读取会话历史（最近消息）
    history_data = get_history(session_id, page=1, page_size=6)  # 最多 6 条
    history = history_data.get("messages", [])

    # RAG 检索上下文
    rag_result = retrieve(question, subject=subject)
    context = rag_result.get("context", "")
    sources = rag_result.get("sources", [])

    # LLM 即时推理
    reply = llm_client.chat(context=context, history=history, question=question)

    # 写入会话历史
    append_message(session_id, "user", question)
    append_message(session_id, "assistant", reply)

    elapsed = int((time.monotonic() - start) * 1000)
    logger.info(f"即时问答完成，耗时 {elapsed}ms，来源: {len(sources)} 个")
    return {"answer": reply, "sources": sources, "response_time_ms": elapsed}


def answer_stream(
    session_id: str, question: str, subject: Optional[str] = None
) -> Iterator[dict]:
    """
    流式问答主入口：以生成器方式逐步 yield SSE 事件字典。

    事件类型:
      {"type": "start"}
      {"type": "token", "content": "..."}
      {"type": "sources", "sources": [...]}
      {"type": "end", "response_time_ms": ...}
      {"type": "error", "code": ..., "message": "..."}

    Raises:
        ValueError: session_id 不存在或学科代码非法（在第一个 yield 前抛出）
    """
    if not session_exists(session_id):
        raise ValueError(f"会话不存在: {session_id}")

    if not is_valid_subject(subject):
        raise ValueError(f"非法学科代码: {subject}")

    start = time.monotonic()
    yield {"type": "start"}  # 通知客户端流式开始

    # 问候语快速路径
    if is_greeting(question):
        reply = get_greeting_reply()
        yield {"type": "token", "content": reply}  # 整句作为单个 token 推送
        append_message(session_id, "user", question)
        append_message(session_id, "assistant", reply)
        elapsed = int((time.monotonic() - start) * 1000)
        yield {"type": "end", "response_time_ms": elapsed}
        return

    # 读取会话历史
    history_data = get_history(session_id, page=1, page_size=6)
    history = history_data.get("messages", [])

    # RAG 检索
    rag_result = retrieve(question, subject=subject)
    context = rag_result.get("context", "")
    sources = rag_result.get("sources", [])

    # LLM 流式推理
    full_reply_parts: list[str] = []  # 收集所有 token 以便写入历史
    for token in llm_client.chat_stream(context=context, history=history, question=question):
        full_reply_parts.append(token)
        yield {"type": "token", "content": token}  # 逐 token 推送

    full_reply = "".join(full_reply_parts)  # 合并完整回复

    # 写入会话历史
    append_message(session_id, "user", question)
    append_message(session_id, "assistant", full_reply)

    yield {"type": "sources", "sources": sources}  # 推送参考来源

    elapsed = int((time.monotonic() - start) * 1000)
    logger.info(f"流式问答完成，耗时 {elapsed}ms，来源: {len(sources)} 个")
    yield {"type": "end", "response_time_ms": elapsed}
