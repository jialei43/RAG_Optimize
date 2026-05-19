import re  # 正则问候识别
import time  # 请求超时控制
from typing import Iterator, Optional  # 类型注解

from openai import OpenAI  # DashScope 兼容 OpenAI SDK

from app import config  # 读取 LLM 配置
from app.utils.logger import get_logger  # 获取命名 Logger

logger = get_logger("modules.llm")  # 模块专属日志

# 问候语正则模式（优先规则匹配，节省 LLM Token）
_GREETING_PATTERN = re.compile(
    r"^(你好|您好|hi|hello|嗨|哈喽|早上好|下午好|晚上好|good\s*morning|good\s*afternoon|good\s*evening)[\s，,。.！!？?]*$",
    re.IGNORECASE,
)

# 兜底回复文本
_FALLBACK_MESSAGE = (
    f"非常抱歉，系统繁忙，暂时无法处理您的请求。"
    f"如需帮助，请拨打客服热线 {config.app_cfg.customer_service_phone}。"
)

# 系统提示词模板
_SYSTEM_PROMPT_TEMPLATE = (
    "你是黑马程序员的专属学习助手，专注于 IT 技术答疑。\n"
    "请根据以下参考资料回答学生的问题，要求准确、简洁、易懂。\n"
    "若无法从参考资料中找到答案，请如实告知，并引导学生拨打客服热线 "
    f"{config.app_cfg.customer_service_phone}。\n\n"
    "【参考资料】\n{{context}}"  # {{context}} 在运行时替换
)


class LLMClient:
    """封装 DashScope Qwen-3.6 调用，支持即时和流式两种模式"""

    def __init__(self):
        self._client: OpenAI | None = None  # 延迟初始化，避免导入时要求 API Key
        self._model = config.llm.model  # qwen-3.6

    def _get_client(self) -> OpenAI:
        """首次调用时才创建 OpenAI 客户端，测试环境可直接替换 _client"""
        if self._client is None:
            self._client = OpenAI(  # 使用 DashScope OpenAI 兼容接口
                api_key=config.llm.api_key,
                base_url=config.llm.base_url,
            )
        return self._client

    def _build_messages(self, context: str, history: list[dict], question: str) -> list[dict]:
        """构建发送给 LLM 的消息列表（system + history + user）"""
        system_content = _SYSTEM_PROMPT_TEMPLATE.replace("{{context}}", context or "暂无参考资料")
        messages = [{"role": "system", "content": system_content}]  # 系统提示词

        for msg in history[-6:]:  # 最多携带最近 6 条历史（3 轮对话），控制 Token 用量
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": question})  # 当前用户问题
        return messages

    def chat(self, context: str, history: list[dict], question: str, timeout: int = 30) -> str:
        """
        即时问答：一次性返回完整答案字符串。
        超时或异常时返回兜底文本。
        """
        messages = self._build_messages(context, history, question)
        try:
            response = self._get_client().chat.completions.create(
                model=self._model,
                messages=messages,
                stream=False,          # 非流式
                timeout=timeout,       # 请求超时时间（秒）
            )
            answer = response.choices[0].message.content or ""  # 提取答案文本
            logger.debug(f"LLM 即时回答完成，长度: {len(answer)} 字符")
            return answer
        except Exception as e:
            logger.error(f"LLM 即时调用失败: {e}")
            return _FALLBACK_MESSAGE  # 降级返回兜底文本

    def chat_stream(
        self, context: str, history: list[dict], question: str, timeout: int = 60
    ) -> Iterator[str]:
        """
        流式问答：逐 token 以生成器方式 yield 文本片段。
        异常时 yield 兜底文本并结束。
        """
        messages = self._build_messages(context, history, question)
        try:
            stream = self._get_client().chat.completions.create(
                model=self._model,
                messages=messages,
                stream=True,           # 流式输出
                timeout=timeout,
            )
            for chunk in stream:  # 逐块读取
                delta = chunk.choices[0].delta.content
                if delta:  # 过滤空 delta
                    yield delta
            logger.debug("LLM 流式回答完成")
        except Exception as e:
            logger.error(f"LLM 流式调用失败: {e}")
            yield _FALLBACK_MESSAGE  # 异常时输出兜底文本


def is_greeting(text: str) -> bool:
    """
    判断输入是否为简单问候语。
    优先正则匹配（快速），未命中时可扩展为轻量 LLM 分类（此处暂用正则）。
    """
    return bool(_GREETING_PATTERN.match(text.strip()))  # 去除首尾空白后匹配


def get_greeting_reply() -> str:
    """返回标准问候回复"""
    return "你好！我是黑马程序员的智能学习助手，有任何 IT 技术问题都可以直接问我 😊"


# 模块级单例
llm_client = LLMClient()
