"""会话管理模块单元测试（Mock Redis，不依赖真实服务）"""
from unittest.mock import MagicMock, patch  # Mock 工具

import pytest  # pytest 框架


@pytest.fixture(autouse=True)  # 每个测试前重置 Redis Mock
def mock_redis():
    """用内存字典模拟 Redis，隔离测试副作用"""
    store: dict = {}  # 模拟 KV 存储
    lists: dict = {}  # 模拟 List 存储
    hashes: dict = {}  # 模拟 Hash 存储

    mock = MagicMock()

    def hset(key, mapping):
        hashes.setdefault(key, {}).update(mapping)  # 合并字段
        return len(mapping)

    def hgetall(key):
        return dict(hashes.get(key, {}))  # 返回副本，防止外部修改

    def rpush(key, *values):
        lists.setdefault(key, []).extend(values)
        return len(lists[key])

    def lrange(key, start, end):
        lst = lists.get(key, [])
        end = end if end != -1 else len(lst)  # -1 表示到末尾
        return lst[start:end + 1]

    def llen(key):
        return len(lists.get(key, []))

    def delete_list(key):
        lists.pop(key, None)
        return 1

    def expire(key, ttl):
        return True  # 不需要实际管理 TTL

    def exists(key):
        return key in hashes or key in lists

    mock.hset.side_effect = hset
    mock.hgetall.side_effect = hgetall
    mock.rpush.side_effect = rpush
    mock.lrange.side_effect = lrange
    mock.llen.side_effect = llen
    mock.delete_list.side_effect = delete_list
    mock.expire.side_effect = expire
    mock.exists.side_effect = exists

    with patch("app.modules.session_manager.redis_client", mock):
        yield mock


class TestCreateSession:
    def test_returns_session_id_and_created_at(self):
        from app.modules.session_manager import create_session
        result = create_session()
        assert "session_id" in result  # 必须包含 session_id
        assert "created_at" in result  # 必须包含创建时间

    def test_session_id_is_uuid(self):
        import uuid
        from app.modules.session_manager import create_session
        result = create_session()
        uuid.UUID(result["session_id"])  # 格式合法则不抛出异常

    def test_meta_written_to_redis(self, mock_redis):
        from app.modules.session_manager import create_session
        create_session()
        assert mock_redis.hset.called  # 必须写入 Redis Hash


class TestGetSession:
    def test_returns_none_for_nonexistent_session(self):
        from app.modules.session_manager import get_session
        result = get_session("nonexistent-id")
        assert result is None  # 不存在时返回 None

    def test_returns_meta_for_existing_session(self):
        from app.modules.session_manager import create_session, get_session
        created = create_session()
        meta = get_session(created["session_id"])
        assert meta is not None                         # 会话存在
        assert meta["session_id"] == created["session_id"]  # session_id 一致


class TestAppendMessage:
    def test_returns_false_for_nonexistent_session(self):
        from app.modules.session_manager import append_message
        result = append_message("bad-id", "user", "hello")
        assert result is False  # 不存在的会话追加失败

    def test_returns_true_for_valid_session(self):
        from app.modules.session_manager import create_session, append_message
        s = create_session()
        result = append_message(s["session_id"], "user", "hello")
        assert result is True  # 正常追加

    def test_message_count_increments(self):
        from app.modules.session_manager import create_session, append_message, get_session
        s = create_session()
        sid = s["session_id"]
        append_message(sid, "user", "q1")
        append_message(sid, "assistant", "a1")
        meta = get_session(sid)
        assert meta["message_count"] == "2"  # 两条消息后计数为 2


class TestGetHistory:
    def test_empty_history(self):
        from app.modules.session_manager import create_session, get_history
        s = create_session()
        result = get_history(s["session_id"])
        assert result["total"] == 0        # 新会话无历史
        assert result["messages"] == []   # 消息列表为空

    def test_pagination(self):
        from app.modules.session_manager import create_session, append_message, get_history
        s = create_session()
        sid = s["session_id"]
        for i in range(5):  # 写入 5 条消息
            append_message(sid, "user", f"msg {i}")

        page1 = get_history(sid, page=1, page_size=3)
        assert len(page1["messages"]) == 3  # 第 1 页 3 条

        page2 = get_history(sid, page=2, page_size=3)
        assert len(page2["messages"]) == 2  # 第 2 页 2 条（剩余）

    def test_page_size_capped_at_max(self):
        from app.modules.session_manager import get_history, _MAX_HISTORY_DISPLAY, create_session
        s = create_session()
        result = get_history(s["session_id"], page=1, page_size=9999)
        assert result["page_size"] <= _MAX_HISTORY_DISPLAY  # 不超过上限


class TestClearHistory:
    def test_returns_false_for_nonexistent_session(self):
        from app.modules.session_manager import clear_history
        assert clear_history("bad-id") is False

    def test_clears_messages(self):
        from app.modules.session_manager import create_session, append_message, clear_history, get_history
        s = create_session()
        sid = s["session_id"]
        append_message(sid, "user", "hello")
        clear_history(sid)
        result = get_history(sid)
        assert result["total"] == 0  # 清空后无消息

    def test_resets_message_count(self):
        from app.modules.session_manager import create_session, append_message, clear_history, get_session
        s = create_session()
        sid = s["session_id"]
        append_message(sid, "user", "hello")
        clear_history(sid)
        meta = get_session(sid)
        assert meta["message_count"] == "0"  # 计数重置为 0
