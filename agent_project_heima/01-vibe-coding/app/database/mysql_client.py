import pymysql  # MySQL 驱动
from pymysql.cursors import DictCursor  # 结果以字典返回
from pymysql import connections  # 连接类型提示
from contextlib import contextmanager  # 上下文管理器装饰器
from typing import Generator  # 类型注解

from app import config  # 读取 MySQL 连接配置
from app.utils.logger import get_logger  # 获取命名 Logger

logger = get_logger("database.mysql")  # 模块专属日志


class MySQLClient:
    """MySQL 连接管理，按需创建连接，使用 autocommit=True 简化事务控制"""

    def __init__(self):
        self._conn: connections.Connection | None = None  # 延迟初始化连接

    def _connect(self) -> connections.Connection:
        """建立新连接，连接失败时记录日志并上抛"""
        try:
            conn = pymysql.connect(
                host=config.mysql.host,
                user=config.mysql.user,
                password=config.mysql.password,
                database=config.mysql.database,
                charset="utf8mb4",
                cursorclass=DictCursor,  # 查询结果返回字典而非元组
                autocommit=True,         # 自动提交，写操作立即生效
                connect_timeout=5,       # 连接超时 5 秒
            )
            logger.debug("MySQL 连接成功")
            return conn
        except pymysql.Error as e:
            logger.error(f"MySQL 连接失败: {e}")
            raise

    @contextmanager
    def cursor(self) -> Generator[pymysql.cursors.DictCursor, None, None]:
        """提供游标上下文，自动处理连接断开重连"""
        if self._conn is None or not self._conn.open:  # 连接不存在或已断开则重连
            self._conn = self._connect()
        try:
            with self._conn.cursor() as cur:  # 使用 with 确保游标关闭
                yield cur
        except pymysql.OperationalError as e:
            logger.warning(f"MySQL 操作错误，尝试重连: {e}")
            self._conn = self._connect()  # 断线重连
            with self._conn.cursor() as cur:
                yield cur

    def ping(self) -> bool:
        """健康探测，SELECT 1 验证连接可用"""
        try:
            with self.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"MySQL ping 失败: {e}")
            return False

    def close(self):
        """显式关闭连接"""
        if self._conn and self._conn.open:
            self._conn.close()
            logger.debug("MySQL 连接已关闭")


# 模块级单例
mysql_client = MySQLClient()
