"""日志工具单元测试"""
import logging  # 标准库日志
import os  # 文件系统操作

import pytest  # pytest 框架
from app.utils.logger import get_logger  # 被测函数


class TestGetLogger:
    def test_returns_logger_instance(self):
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)  # 返回类型正确

    def test_same_name_returns_same_instance(self):
        a = get_logger("test.singleton")
        b = get_logger("test.singleton")
        assert a is b  # 同名 Logger 必须是同一对象（单例）

    def test_different_names_are_different(self):
        a = get_logger("test.alpha")
        b = get_logger("test.beta")
        assert a is not b  # 不同名 Logger 是独立实例

    def test_has_two_handlers(self):
        logger = get_logger("test.handlers")
        assert len(logger.handlers) == 2  # 必须同时有 Console + File 两个 Handler

    def test_no_duplicate_handlers_on_repeated_call(self):
        get_logger("test.dup")
        get_logger("test.dup")
        logger = get_logger("test.dup")
        assert len(logger.handlers) == 2  # 多次获取不应累积 Handler

    def test_log_level_is_debug(self):
        logger = get_logger("test.level")
        assert logger.level == logging.DEBUG  # Logger 本身捕获 DEBUG 及以上

    def test_propagate_is_false(self):
        logger = get_logger("test.propagate")
        assert logger.propagate is False  # 禁止向 root 传播

    def test_log_file_created(self):
        logger = get_logger("test.file_create")
        logger.info("log file creation test")  # 写入一条日志触发文件创建
        from app.utils.logger import _LOG_FILE
        assert os.path.exists(_LOG_FILE)  # 日志文件必须存在
