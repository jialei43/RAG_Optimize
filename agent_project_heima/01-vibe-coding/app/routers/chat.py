import json  # SSE 事件序列化

from fastapi import APIRouter, HTTPException  # 路由与 HTTP 异常
from fastapi.responses import StreamingResponse  # SSE 流式响应

from app.models.schemas import ApiResponse, ChatRequest  # 请求/响应 Schema
from app.modules import qa_engine  # 问答引擎
from app.modules.subject_manager import is_valid_subject  # 学科合法性校验
from app.utils.logger import get_logger  # 获取命名 Logger

router = APIRouter()  # 问答路由组
logger = get_logger("routers.chat")  # 模块专属日志


def _validate_request(req: ChatRequest):
    """统一校验问答请求，非法时抛出 HTTPException"""
    if req.subject and not is_valid_subject(req.subject):  # 学科代码合法性
        raise HTTPException(
            status_code=400,
            detail={"code": 1003, "message": f"学科代码不合法: {req.subject}"}
        )


@router.post("/chat", response_model=ApiResponse, summary="即时问答")
def chat(req: ChatRequest):
    """一次性返回完整答案，适用于简单问题"""
    _validate_request(req)
    try:
        result = qa_engine.answer(
            session_id=req.session_id,
            question=req.question,
            subject=req.subject,
        )
        return ApiResponse.ok(data=result)
    except ValueError as e:  # 会话不存在或学科非法
        logger.warning(f"问答请求参数错误: {e}")
        raise HTTPException(status_code=404, detail={"code": 2001, "message": str(e)})
    except Exception as e:
        logger.error(f"即时问答异常: {e}")
        raise HTTPException(status_code=503, detail={"code": 5001, "message": "问答服务暂时不可用"})


@router.post("/chat/stream", summary="流式问答 (SSE)")
def chat_stream(req: ChatRequest):
    """
    以 Server-Sent Events 格式逐 token 推送答案。
    Content-Type: text/event-stream
    """
    _validate_request(req)

    def _event_generator():
        """将 qa_engine.answer_stream 的事件字典序列化为 SSE 格式"""
        try:
            for event in qa_engine.answer_stream(
                session_id=req.session_id,
                question=req.question,
                subject=req.subject,
            ):
                data = json.dumps(event, ensure_ascii=False)  # 中文不转义
                yield f"data: {data}\n\n"  # SSE 标准格式
        except ValueError as e:
            error_event = {"type": "error", "code": 2001, "message": str(e)}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"流式问答异常: {e}")
            error_event = {"type": "error", "code": 5001, "message": "流式服务异常"}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

    return StreamingResponse(  # 返回 SSE 流式响应
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",           # 禁止缓存
            "X-Accel-Buffering": "no",             # 关闭 Nginx 缓冲，保证实时推送
        },
    )
