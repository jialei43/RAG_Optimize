from typing import Optional  # 类型注解

from app import config  # 读取 valid_sources 和缓存配置
from app.database.redis_client import redis_client  # Redis 缓存客户端
from app.utils.logger import get_logger  # 获取命名 Logger

logger = get_logger("modules.subject")  # 模块专属日志

_SUBJECT_CACHE_KEY = "subject:list"  # 学科列表 Redis 缓存 Key
_SUBJECT_CACHE_TTL = 3600            # 缓存 TTL：1 小时

# 学科代码 → 中文名映射，与 valid_sources 保持同步
_SOURCE_LABELS: dict[str, str] = {
    "ai":      "人工智能",
    "java":    "Java 开发",
    "test":    "软件测试",
    "ops":     "运维与云计算",
    "bigdata": "大数据",
}


def get_subjects() -> list[dict]:
    """
    返回所有支持的学科列表，优先从 Redis 缓存读取。
    格式: [{"code": "java", "name": "Java 开发"}, ...]
    """
    cached = redis_client.get(_SUBJECT_CACHE_KEY)  # 先查缓存
    if cached is not None:
        logger.debug("学科列表命中缓存")
        return cached

    subjects = [  # 从配置构建学科列表
        {"code": code, "name": _SOURCE_LABELS.get(code, code)}
        for code in config.app_cfg.valid_sources
    ]
    redis_client.set(_SUBJECT_CACHE_KEY, subjects, ttl=_SUBJECT_CACHE_TTL)  # 写入缓存
    logger.debug(f"学科列表已缓存: {len(subjects)} 个学科")
    return subjects


def is_valid_subject(subject: Optional[str]) -> bool:
    """
    校验学科代码是否合法。
    None 或空字符串视为"不限学科"，返回 True。
    """
    if not subject:  # None 或空字符串均视为合法（全学科检索）
        return True
    return subject in config.app_cfg.valid_sources


def get_subject_filter_expr(subject: Optional[str]) -> Optional[str]:
    """
    生成 Milvus 标量过滤表达式。
    subject 为空时返回 None（不过滤），否则返回 "source == 'java'" 形式的表达式。
    """
    if not subject:
        return None
    return f"source == '{subject}'"  # Milvus DSL 过滤表达式
