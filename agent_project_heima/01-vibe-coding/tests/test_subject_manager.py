"""学科管理模块单元测试（Mock Redis）"""
from unittest.mock import MagicMock, patch  # Mock 工具

import pytest  # pytest 框架


@pytest.fixture(autouse=True)  # 每个测试前重置 Mock
def mock_redis():
    """用内存 KV 模拟 Redis，隔离缓存副作用"""
    store: dict = {}

    mock = MagicMock()
    mock.get.side_effect = lambda key: store.get(key)
    mock.set.side_effect = lambda key, value, ttl=None: store.__setitem__(key, value) or True

    with patch("app.modules.subject_manager.redis_client", mock):
        yield mock


class TestGetSubjects:
    def test_returns_list_of_dicts(self):
        from app.modules.subject_manager import get_subjects
        result = get_subjects()
        assert isinstance(result, list)              # 返回列表
        assert all(isinstance(s, dict) for s in result)  # 每项是字典

    def test_contains_all_valid_sources(self):
        from app.modules.subject_manager import get_subjects
        from app import config
        result = get_subjects()
        codes = {s["code"] for s in result}
        assert codes == set(config.app_cfg.valid_sources)  # 包含所有学科代码

    def test_each_subject_has_code_and_name(self):
        from app.modules.subject_manager import get_subjects
        for subject in get_subjects():
            assert "code" in subject  # 必须有 code 字段
            assert "name" in subject  # 必须有 name 字段
            assert subject["name"]    # name 不能为空

    def test_uses_cache_on_second_call(self, mock_redis):
        from app.modules.subject_manager import get_subjects
        get_subjects()  # 第一次调用写入缓存
        mock_redis.get.side_effect = lambda key: [{"code": "cached", "name": "缓存值"}]  # 下次从缓存返回
        result = get_subjects()
        assert result[0]["code"] == "cached"  # 第二次命中缓存


class TestIsValidSubject:
    def test_none_is_valid(self):
        from app.modules.subject_manager import is_valid_subject
        assert is_valid_subject(None) is True  # None 表示不限学科

    def test_empty_string_is_valid(self):
        from app.modules.subject_manager import is_valid_subject
        assert is_valid_subject("") is True  # 空字符串同样视为合法

    def test_known_subjects_are_valid(self):
        from app.modules.subject_manager import is_valid_subject
        for code in ["ai", "java", "test", "ops", "bigdata"]:
            assert is_valid_subject(code) is True  # 已知学科全部合法

    def test_unknown_subject_is_invalid(self):
        from app.modules.subject_manager import is_valid_subject
        assert is_valid_subject("cooking") is False  # 未知学科不合法

    def test_case_sensitive(self):
        from app.modules.subject_manager import is_valid_subject
        assert is_valid_subject("Java") is False  # 大小写敏感，"Java" 不合法


class TestGetSubjectFilterExpr:
    def test_none_returns_none(self):
        from app.modules.subject_manager import get_subject_filter_expr
        assert get_subject_filter_expr(None) is None  # 不限学科时无过滤

    def test_empty_returns_none(self):
        from app.modules.subject_manager import get_subject_filter_expr
        assert get_subject_filter_expr("") is None

    def test_java_returns_correct_expr(self):
        from app.modules.subject_manager import get_subject_filter_expr
        expr = get_subject_filter_expr("java")
        assert expr == "source == 'java'"  # 表达式格式正确

    def test_all_sources_produce_valid_expr(self):
        from app.modules.subject_manager import get_subject_filter_expr
        from app import config
        for code in config.app_cfg.valid_sources:
            expr = get_subject_filter_expr(code)
            assert code in expr  # 表达式中包含学科代码
