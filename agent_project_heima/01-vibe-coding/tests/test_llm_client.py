"""LLM 客户端单元测试（Mock OpenAI 调用）"""
from unittest.mock import MagicMock, patch  # Mock 工具

import pytest  # pytest 框架


# ── 问候识别测试 ──────────────────────────────────────────────────────────────

class TestIsGreeting:
    def test_nihao_is_greeting(self):
        from app.modules.llm_client import is_greeting
        assert is_greeting("你好") is True

    def test_hello_is_greeting(self):
        from app.modules.llm_client import is_greeting
        assert is_greeting("hello") is True

    def test_greeting_with_punctuation(self):
        from app.modules.llm_client import is_greeting
        assert is_greeting("你好！") is True  # 带感叹号也算问候

    def test_technical_question_not_greeting(self):
        from app.modules.llm_client import is_greeting
        assert is_greeting("Java 中 HashMap 是线程安全的吗？") is False

    def test_empty_string_not_greeting(self):
        from app.modules.llm_client import is_greeting
        assert is_greeting("") is False

    def test_mixed_content_not_greeting(self):
        from app.modules.llm_client import is_greeting
        assert is_greeting("你好，请问什么是多态") is False  # 含技术内容不算纯问候

    def test_case_insensitive_hi(self):
        from app.modules.llm_client import is_greeting
        assert is_greeting("HI") is True  # 大写 HI 也算问候


# ── 问候回复测试 ──────────────────────────────────────────────────────────────

class TestGetGreetingReply:
    def test_reply_is_string(self):
        from app.modules.llm_client import get_greeting_reply
        assert isinstance(get_greeting_reply(), str)

    def test_reply_not_empty(self):
        from app.modules.llm_client import get_greeting_reply
        assert get_greeting_reply()  # 不为空字符串


# ── 即时问答测试 ──────────────────────────────────────────────────────────────

class TestChat:
    def _mock_client(self, answer: str = "这是答案"):
        """构造返回固定答案的 Mock OpenAI 客户端"""
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = answer
        mock_inner = MagicMock()
        mock_inner.chat.completions.create.return_value = mock_resp
        return mock_inner

    def test_returns_answer_string(self):
        from app.modules.llm_client import LLMClient
        client = LLMClient()
        client._client = self._mock_client("HashMap 是非线程安全的")
        result = client.chat("context", [], "HashMap 和 HashTable 区别")
        assert isinstance(result, str)                    # 返回字符串
        assert "HashMap" in result                        # 包含答案内容

    def test_returns_fallback_on_exception(self):
        from app.modules.llm_client import LLMClient, _FALLBACK_MESSAGE
        client = LLMClient()
        client._client = MagicMock()
        client._client.chat.completions.create.side_effect = Exception("timeout")
        result = client.chat("", [], "test")
        assert result == _FALLBACK_MESSAGE  # 超时时返回兜底文本

    def test_history_limited_to_six_messages(self):
        from app.modules.llm_client import LLMClient
        client = LLMClient()
        mock_inner = MagicMock()
        mock_inner.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok"))]
        )
        client._client = mock_inner

        long_history = [  # 构造 10 条历史消息
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"}
            for i in range(10)
        ]
        client.chat("ctx", long_history, "question")
        call_messages = mock_inner.chat.completions.create.call_args[1]["messages"]
        # 1 个 system + 最多 6 条历史 + 1 个 user = 最多 8 条
        assert len(call_messages) <= 8  # 消息数不超过上限


# ── 流式问答测试 ──────────────────────────────────────────────────────────────

class TestChatStream:
    def test_yields_tokens(self):
        from app.modules.llm_client import LLMClient
        client = LLMClient()

        chunks = ["Java", " 的", " 多态"]
        mock_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content=c))]) for c in chunks
        ]
        client._client = MagicMock()
        client._client.chat.completions.create.return_value = iter(mock_chunks)

        tokens = list(client.chat_stream("ctx", [], "什么是多态"))
        assert tokens == chunks  # 应原样 yield 每个 token

    def test_yields_fallback_on_exception(self):
        from app.modules.llm_client import LLMClient, _FALLBACK_MESSAGE
        client = LLMClient()
        client._client = MagicMock()
        client._client.chat.completions.create.side_effect = Exception("network error")

        tokens = list(client.chat_stream("", [], "test"))
        assert tokens == [_FALLBACK_MESSAGE]  # 异常时 yield 兜底文本

    def test_skips_empty_delta(self):
        from app.modules.llm_client import LLMClient
        client = LLMClient()

        chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="hello"))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content=""))]),  # 空 delta
            MagicMock(choices=[MagicMock(delta=MagicMock(content=None))]),  # None delta
            MagicMock(choices=[MagicMock(delta=MagicMock(content=" world"))]),
        ]
        client._client = MagicMock()
        client._client.chat.completions.create.return_value = iter(chunks)

        tokens = list(client.chat_stream("ctx", [], "test"))
        assert "" not in tokens   # 空字符串不应被 yield
        assert None not in tokens  # None 不应被 yield
        assert tokens == ["hello", " world"]  # 只保留有效 token
