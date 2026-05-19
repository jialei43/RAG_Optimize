import logging  # 标准库日志模块
import os  # 目录创建
from logging.handlers import RotatingFileHandler  # 按大小滚动的文件处理器

from app import config  # 读取日志文件路径配置

# 本地日志目录（兜底，避免路径不存在时崩溃）
_DEFAULT_LOG_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "logs", "app.log"
)
def _resolve_log_file() -> str:
    """尝试使用 config.ini 中的路径，创建目录失败时回退到本地 logs/ 目录"""
    candidate = config.logger_cfg.log_file or _DEFAULT_LOG_FILE
    try:
        os.makedirs(os.path.dirname(os.path.abspath(candidate)), exist_ok=True)
        return candidate
    except (PermissionError, OSError):  # 路径不可写（如其他机器的绝对路径）时回退
        os.makedirs(os.path.dirname(os.path.abspath(_DEFAULT_LOG_FILE)), exist_ok=True)
        return _DEFAULT_LOG_FILE


_LOG_FILE = _resolve_log_file()  # 解析最终有效的日志文件路径

_FORMATTER = logging.Formatter(  # 统一日志格式，含时间戳、级别、模块名
    fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


def get_logger(name: str) -> logging.Logger:
    """
    返回命名 Logger，第一次调用时添加 Console 和 RotatingFile 两个 Handler。
    同一 name 多次调用返回同一实例，不重复添加 Handler。
    """
    logger = logging.getLogger(name)

    if logger.handlers:  # 已配置过，直接返回，避免重复 Handler
        return logger

    logger.setLevel(logging.DEBUG)  # 捕获所有级别，由 Handler 各自过滤

    console_handler = logging.StreamHandler()  # 控制台输出
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(_FORMATTER)

    file_handler = RotatingFileHandler(  # 文件输出，单文件最大 100MB，保留 30 个备份
        filename=_LOG_FILE,
        maxBytes=100 * 1024 * 1024,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_FORMATTER)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.propagate = False  # 禁止向 root logger 传播，避免重复打印

    return logger
