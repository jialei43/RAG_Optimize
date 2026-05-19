import time  # 计算探测延迟
from datetime import datetime, timezone  # 时间戳生成

from fastapi import APIRouter  # 路由注册

from app.database.mysql_client import mysql_client    # MySQL 健康探测
from app.database.redis_client import redis_client    # Redis 健康探测
from app.database.milvus_client import milvus_client  # Milvus 健康探测
from app.modules.subject_manager import get_subjects  # 学科列表查询
from app.models.schemas import ApiResponse, ComponentHealth, HealthData  # 响应 Schema
from app.utils.logger import get_logger  # 获取命名 Logger

router = APIRouter()  # 系统管理路由组
logger = get_logger("routers.system")  # 模块专属日志


def _probe(fn) -> ComponentHealth:
    """执行健康探测函数，返回状态和延迟，探测失败时返回 down 状态"""
    start = time.monotonic()  # 使用单调时钟测量耗时
    try:
        ok = fn()
        latency = int((time.monotonic() - start) * 1000)  # 转换为毫秒
        return ComponentHealth(status="up" if ok else "down", latency_ms=latency)
    except Exception as e:
        logger.warning(f"健康探测异常: {e}")
        return ComponentHealth(status="down", latency_ms=None)


@router.get("/health", response_model=ApiResponse, summary="系统健康检查")
def health_check():
    """
    探测 MySQL / Redis / Milvus 三个存储组件状态。
    全部 UP → HTTP 200, status=healthy；
    任一 DOWN → HTTP 200, status=degraded（业务层降级处理）。
    """
    components = {
        "mysql":  _probe(mysql_client.ping),   # 探测 MySQL
        "redis":  _probe(redis_client.ping),   # 探测 Redis
        "milvus": _probe(milvus_client.ping),  # 探测 Milvus
    }
    overall = "healthy" if all(c.status == "up" for c in components.values()) else "degraded"
    timestamp = datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds")

    data = HealthData(status=overall, timestamp=timestamp, components=components)
    logger.info(f"健康检查完成: {overall}")
    return ApiResponse.ok(data=data.model_dump())


@router.get("/subjects", response_model=ApiResponse, summary="获取支持的学科列表")
def list_subjects():
    """返回系统当前支持的全部学科，数据来自 Redis 缓存（TTL=1h）"""
    subjects = get_subjects()
    return ApiResponse.ok(data={"subjects": subjects})
