"""问答引擎单元测试（Mock RAG / LLM / 会话）"""
from unittest.mock import MagicMock, patch  # Mock 工具

import pytest  # pytest 框架


# ── 测试辅助 fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_session():
    """Mock 会话管理，默认会话存在，历史为空"""
    with patch("app.modules.qa_engine.session_exists", return_value=True), \
         patch("app.modules.qa_engine.get_history", return_value={"messages": []}), \
         patch("app.modules.qa_engine.append_message", return_value=True):
        yield


@pytest.fixture()
def mock_rag():
    """Mock RAG 检索返回固定结果"""
    rag_result = {
        "context": "Java HashMap 是非线程安全的哈希表实现...",
        "sources": [{"parent_id": "p1", "subject": "java", "excerpt": "HashMap..."}],
    }
    with patch("app.modules.qa_engine.retrieve", return_value=rag_result) as m:
        yield m


@pytest.fixture()
def mock_llm_chat():
    """Mock LLM 即时回答"""
    with patch("app.modules.qa_engine.llm_client") as m:
        m.chat.return_value = "HashMap 是非线程安全的，HashTable 是线程安全的"
        yield m


@pytest.fixture()
def mock_llm_stream():
    """Mock LLM 流式回答"""
    with patch("app.modules.qa_engine.llm_client") as m:
        m.chat_stream.return_value = iter(["HashMap", " 是", " 非线程安全的"])
        yield m


# ── 即时问答测试 ──────────────────────────────────────────────────────────────

class TestAnswer:
    def test_raises_for_nonexistent_session(self):
        with patch("app.modules.qa_engine.session_exists", return_value=False):
            from app.modules.qa_engine import answer
            with pytest.raises(ValueError, match="会话不存在"):
                answer("bad-id", "test question")

    def test_raises_for_invalid_subject(self):
        from app.modules.qa_engine import answer
        with pytest.raises(ValueError, match="非法学科代码"):
            answer("valid-id", "test", subject="invalid_subject")

    def test_returns_greeting_without_rag(self, mock_rag):
        from app.modules.qa_engine import answer
        with patch("app.modules.qa_engine.is_greeting", return_value=True), \
             patch("app.modules.qa_engine.get_greeting_reply", return_value="你好！"):
            result = answer("sid", "你好")
        assert result["answer"] == "你好！"       # 返回问候语
        assert result["sources"] == []            # 问候语无 RAG 来源
        mock_rag.assert_not_called()              # 不应调用 RAG

    def test_returns_answer_with_sources(self, mock_rag, mock_llm_chat):
        from app.modules.qa_engine import answer
        result = answer("sid", "HashMap 和 HashTable 区别", subject="java")
        assert "HashMap" in result["answer"]      # 答案包含内容
        assert len(result["sources"]) == 1        # 一个参考来源
        assert "response_time_ms" in result       # 包含耗时字段

    def test_response_time_is_positive(self, mock_rag, mock_llm_chat):
        from app.modules.qa_engine import answer
        result = answer("sid", "test")
        assert result["response_time_ms"] >= 0  # 耗时非负

    def test_appends_messages_to_history(self, mock_rag, mock_llm_chat):
        from app.modules.qa_engine import answer
        with patch("app.modules.qa_engine.append_message") as mock_append:
            answer("sid", "test question")
        assert mock_append.call_count == 2  # 用户消息 + 助手消息各写一次

    def test_passes_subject_to_rag(self, mock_rag, mock_llm_chat):
        from app.modules.qa_engine import answer
        answer("sid", "question", subject="java")
        mock_rag.assert_called_once_with("question", subject="java")  # 学科参数透传


# ── 流式问答测试 ──────────────────────────────────────────────────────────────

class TestAnswerStream:
    def test_raises_for_nonexistent_session(self):
        with patch("app.modules.qa_engine.session_exists", return_value=False):
            from app.modules.qa_engine import answer_stream
            with pytest.raises(ValueError, match="会话不存在"):
                list(answer_stream("bad-id", "test"))

    def test_first_event_is_start(self, mock_rag, mock_llm_stream):
        from app.modules.qa_engine import answer_stream
        events = list(answer_stream("sid", "test"))
        assert events[0]["type"] == "start"  # 第一个事件必须是 start

    def test_last_event_is_end(self, mock_rag, mock_llm_stream):
        from app.modules.qa_engine import answer_stream
        events = list(answer_stream("sid", "test"))
        assert events[-1]["type"] == "end"  # 最后一个事件必须是 end

    def test_contains_token_events(self, mock_rag, mock_llm_stream):
        from app.modules.qa_engine import answer_stream
        events = list(answer_stream("sid", "test"))
        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) == 3  # Mock 返回 3 个 token

    def test_contains_sources_event(self, mock_rag, mock_llm_stream):
        from app.modules.qa_engine import answer_stream
        events = list(answer_stream("sid", "test"))
        source_events = [e for e in events if e["type"] == "sources"]
        assert len(source_events) == 1        # 恰好一个 sources 事件
        assert source_events[0]["sources"]    # sources 列表非空

    def test_greeting_stream_skips_rag(self, mock_rag):
        from app.modules.qa_engine import answer_stream
        with patch("app.modules.qa_engine.is_greeting", return_value=True), \
             patch("app.modules.qa_engine.get_greeting_reply", return_value="你好！"):
            events = list(answer_stream("sid", "你好"))
        mock_rag.assert_not_called()  # 问候语不触发 RAG
        token_events = [e for e in events if e["type"] == "token"]
        assert token_events[0]["content"] == "你好！"  # 问候回复正确推送

    def test_end_event_has_response_time(self, mock_rag, mock_llm_stream):
        from app.modules.qa_engine import answer_stream
        events = list(answer_stream("sid", "test"))
        end_event = next(e for e in events if e["type"] == "end")
        assert "response_time_ms" in end_event           # end 事件含耗时
        assert end_event["response_time_ms"] >= 0        # 耗时非负
