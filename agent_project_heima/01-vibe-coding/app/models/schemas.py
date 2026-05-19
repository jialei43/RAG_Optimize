from typing import Any, Optional  # 类型注解
from pydantic import BaseModel, Field  # 数据模型与字段约束


# ── 统一响应包装 ───────────────────────────────────────────────────────────────

class ApiResponse(BaseModel):
    """所有接口的统一响应结构"""
    code:    int          = Field(0, description="0=成功，非0=业务错误码")
    message: str          = Field("success", description="描述信息")
    data:    Optional[Any] = Field(None, description="业务数据")

    @classmethod
    def ok(cls, data: Any = None, message: str = "success") -> "ApiResponse":
        """构造成功响应"""
        return cls(code=0, message=message, data=data)

    @classmethod
    def error(cls, code: int, message: str) -> "ApiResponse":
        """构造业务错误响应"""
        return cls(code=code, message=message, data=None)


# ── 系统相关 Schema ────────────────────────────────────────────────────────────

class ComponentHealth(BaseModel):
    """单个组件健康状态"""
    status:     str            # "up" | "down"
    latency_ms: Optional[int]  # 探测延迟（毫秒）


class HealthData(BaseModel):
    """健康检查响应数据"""
    status:     str                          # "healthy" | "degraded"
    timestamp:  str                          # ISO 8601 时间戳
    components: dict[str, ComponentHealth]  # 各组件状态


# ── 会话相关 Schema ────────────────────────────────────────────────────────────

class SessionCreateData(BaseModel):
    """创建会话响应数据"""
    session_id: str  # UUID v4
    created_at: str  # ISO 8601 时间戳


class MessageItem(BaseModel):
    """单条消息结构"""
    role:       str  # "user" | "assistant"
    content:    str  # 消息内容
    created_at: str  # ISO 8601 时间戳


class HistoryData(BaseModel):
    """历史记录响应数据"""
    total:     int              # 总消息条数
    page:      int              # 当前页码
    page_size: int              # 每页条数
    messages:  list[MessageItem]  # 消息列表


# ── 问答相关 Schema ────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """即时/流式问答请求体"""
    session_id: str            = Field(..., pattern=r"^[0-9a-f\-]{36}$",  # UUID v4 格式校验
                                       description="会话 ID")
    question:   str            = Field(..., min_length=1, max_length=500,  # 长度限制
                                       description="用户问题")
    subject:    Optional[str]  = Field(None, description="学科代码，如 java/ai/test")


class SourceItem(BaseModel):
    """RAG 召回的参考来源"""
    parent_id: str  # 父块 ID
    subject:   str  # 学科代码
    excerpt:   str  # 内容摘要


class ChatData(BaseModel):
    """即时问答响应数据"""
    answer:          str              # LLM 生成的答案
    sources:         list[SourceItem] # RAG 参考来源列表
    response_time_ms: int             # 总耗时（毫秒）
