from fastapi import APIRouter, HTTPException, Query  # 路由、HTTP 异常、查询参数

from app.modules import session_manager  # 会话管理业务逻辑
from app.models.schemas import ApiResponse  # 统一响应结构
from app.utils.logger import get_logger  # 获取命名 Logger

router = APIRouter()  # 会话管理路由组
logger = get_logger("routers.sessions")  # 模块专属日志


@router.post("/sessions", response_model=ApiResponse, summary="创建新会话", status_code=201)
def create_session():
    """创建新会话，返回 session_id 和创建时间"""
    data = session_manager.create_session()  # 写入 Redis 并生成 session_id
    return ApiResponse.ok(data=data)


@router.get("/sessions/{session_id}/history", response_model=ApiResponse, summary="获取对话历史")
def get_history(
    session_id: str,
    page:      int = Query(1,  ge=1,   description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数，最大 100"),
):
    """分页获取指定会话的对话历史记录"""
    if not session_manager.session_exists(session_id):  # 会话不存在则 404
        raise HTTPException(status_code=404, detail={"code": 2001, "message": "会话不存在或已过期"})
    data = session_manager.get_history(session_id, page=page, page_size=page_size)
    return ApiResponse.ok(data=data)


@router.delete("/sessions/{session_id}/history", response_model=ApiResponse, summary="清空对话历史")
def clear_history(session_id: str):
    """清空指定会话的历史记录，保留会话本身"""
    if not session_manager.clear_history(session_id):  # 会话不存在则 404
        raise HTTPException(status_code=404, detail={"code": 2001, "message": "会话不存在或已过期"})
    return ApiResponse.ok(message="历史记录已清空")
