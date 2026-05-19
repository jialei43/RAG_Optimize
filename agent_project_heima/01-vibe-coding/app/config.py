import configparser  # 标准库 INI 配置解析器
import json  # 解析 valid_sources 列表字符串
import os  # 读取环境变量

# config.ini 相对于本文件的路径
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "documents", "config.ini")

_parser = configparser.ConfigParser()  # 全局解析器实例
_parser.read(_CONFIG_PATH, encoding="utf-8")  # 读取配置文件


class MySQLConfig:
    """MySQL 连接参数"""
    host: str = _parser.get("mysql", "host")
    user: str = _parser.get("mysql", "user")
    password: str = os.environ.get("MYSQL_PASSWORD", _parser.get("mysql", "password"))  # 优先取环境变量
    database: str = _parser.get("mysql", "database")


class RedisConfig:
    """Redis 连接参数"""
    host: str = _parser.get("redis", "host")
    port: int = _parser.getint("redis", "port")
    password: str | None = os.environ.get("REDIS_PASSWORD") or _parser.get("redis", "password", fallback=None)  # 无密码时为 None，跳过 AUTH
    db: int = _parser.getint("redis", "db")


class MilvusConfig:
    """Milvus 向量数据库连接参数"""
    host: str = _parser.get("milvus", "host")
    port: int = _parser.getint("milvus", "port")
    database_name: str = _parser.get("milvus", "database_name")
    collection_name: str = _parser.get("milvus", "collection_name")


class LLMConfig:
    """大语言模型配置"""
    model: str = _parser.get("llm", "model")
    base_url: str = _parser.get("llm", "dashscope_base_url")
    api_key: str = os.environ.get("DASHSCOPE_API_KEY", "")  # 必须由环境变量提供，不得硬编码


class RetrievalConfig:
    """RAG 检索参数"""
    parent_chunk_size: int = _parser.getint("retrieval", "parent_chunk_size")
    child_chunk_size: int = _parser.getint("retrieval", "child_chunk_size")
    chunk_overlap: int = _parser.getint("retrieval", "chunk_overlap")
    retrieval_k: int = _parser.getint("retrieval", "retrieval_k")   # 向量检索召回数
    candidate_m: int = _parser.getint("retrieval", "candidate_m")   # 最终送入 LLM 的父块数


class AppConfig:
    """应用级配置"""
    valid_sources: list = json.loads(_parser.get("app", "valid_sources"))  # 合法学科代码列表
    customer_service_phone: str = _parser.get("app", "customer_service_phone")  # 客服热线兜底


class LoggerConfig:
    """日志配置"""
    log_file: str = _parser.get("logger", "log_file")


# 模块级单例，其他模块直接导入使用
mysql = MySQLConfig()
redis = RedisConfig()
milvus = MilvusConfig()
llm = LLMConfig()
retrieval = RetrievalConfig()
app_cfg = AppConfig()
logger_cfg = LoggerConfig()
