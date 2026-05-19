import uuid  # 生成 UUID v4 会话 ID
from datetime import datetime, timezone  # 时间戳处理
from typing import Optional  # 类型注解

from app.database.redis_client import redis_client  # Redis 客户端单例
from app.utils.logger import get_logger  # 获取命名 Logger

logger = get_logger("modules.session")  # 模块专属日志

_SESSION_TTL = 86400          # 会话默认保留 24 小时（秒）
_MAX_HISTORY_DISPLAY = 200    # 单次最多展示的历史条数上限


def _meta_key(session_id: str) -> str:
    """生成会话元数据的 Redis Key"""
    return f"session:{session_id}:meta"


def _history_key(session_id: str) -> str:
    """生成会话历史的 Redis Key"""
    return f"session:{session_id}:history"


def _now_iso() -> str:
    """返回当前 UTC+8 时间的 ISO 8601 字符串"""
    return datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds")


# ── 公开接口 ──────────────────────────────────────────────────────────────────

def create_session() -> dict:
    """
    创建新会话，写入 Redis，返回元数据字典。
    包含: session_id, created_at
    """
    session_id = str(uuid.uuid4())  # 生成全局唯一会话 ID
    now = _now_iso()

    meta = {  # 会话元数据字段
        "session_id":    session_id,
        "created_at":    now,
        "last_active":   now,
        "subject":       "",   # 尚未选择学科
        "message_count": "0",  # Redis Hash 值均为字符串
    }

    redis_client.hset(_meta_key(session_id), meta)           # 写入元数据 Hash
    redis_client.expire(_meta_key(session_id), _SESSION_TTL) # 设置 TTL
    logger.info(f"会话已创建: {session_id}")
    return {"session_id": session_id, "created_at": now}


def get_session(session_id: str) -> Optional[dict]:
    """
    获取会话元数据，会话不存在或已过期返回 None。
    成功读取时重置 TTL（活跃续期）。
    """
    meta = redis_client.hgetall(_meta_key(session_id))  # 读取 Hash 所有字段
    if not meta:  # 键不存在或已过期
        return None
    redis_client.expire(_meta_key(session_id), _SESSION_TTL)  # 活跃续期
    return meta


def session_exists(session_id: str) -> bool:
    """判断会话是否存在"""
    return get_session(session_id) is not None


def append_message(session_id: str, role: str, content: str) -> bool:
    """
    追加一条消息到会话历史，同时更新 last_active 和 message_count。
    返回 True 表示追加成功，会话不存在返回 False。
    """
    if not session_exists(session_id):
        logger.warning(f"追加消息失败，会话不存在: {session_id}")
        return False

    message = {  # 消息结构体
        "role":       role,
        "content":    content,
        "created_at": _now_iso(),
    }
    history_key = _history_key(session_id)
    redis_client.rpush(history_key, message)              # 追加到列表右端
    redis_client.expire(history_key, _SESSION_TTL)        # 同步刷新历史 TTL

    meta_key = _meta_key(session_id)
    count = int(redis_client.hgetall(meta_key).get("message_count", "0")) + 1
    redis_client.hset(meta_key, {  # 更新元数据
        "last_active":   _now_iso(),
        "message_count": str(count),
    })
    redis_client.expire(meta_key, _SESSION_TTL)  # 刷新元数据 TTL
    return True


def get_history(session_id: str, page: int = 1, page_size: int = 20) -> dict:
    """
    分页获取会话历史（按时间正序）。
    返回: {total, page, page_size, messages}
    """
    history_key = _history_key(session_id)
    total = redis_client.llen(history_key)  # 总消息数

    page_size = min(page_size, _MAX_HISTORY_DISPLAY)  # 限制单页最大条数
    start = (page - 1) * page_size                    # List 起始下标（0-based）
    end = start + page_size - 1                       # List 结束下标（包含）

    messages = redis_client.lrange(history_key, start, end)  # 读取分页数据
    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "messages":  messages,
    }


def clear_history(session_id: str) -> bool:
    """
    清空会话历史，保留元数据（session 仍然有效）。
    返回 True 表示清空成功，会话不存在返回 False。
    """
    if not session_exists(session_id):
        return False
    redis_client.delete_list(_history_key(session_id))  # 删除历史 List
    redis_client.hset(_meta_key(session_id), {           # 重置消息计数
        "message_count": "0",
        "last_active":   _now_iso(),
    })
    logger.info(f"会话历史已清空: {session_id}")
    return True


def update_subject(session_id: str, subject: str) -> bool:
    """更新会话当前选择的学科"""
    if not session_exists(session_id):
        return False
    redis_client.hset(_meta_key(session_id), {"subject": subject})  # 更新学科字段
    return True
