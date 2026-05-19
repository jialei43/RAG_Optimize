from typing import Optional  # 类型注解

from pymilvus import MilvusClient as _MilvusSDK  # Milvus 官方 SDK 客户端

from app import config  # 读取 Milvus 连接配置
from app.utils.logger import get_logger  # 获取命名 Logger

logger = get_logger("database.milvus")  # 模块专属日志


class MilvusClient:
    """Milvus 向量数据库客户端封装"""

    def __init__(self):
        uri = f"http://{config.milvus.host}:{config.milvus.port}"  # 构造连接 URI
        self._client: Optional[_MilvusSDK] = None  # 延迟初始化，避免启动时阻塞
        self._uri = uri
        self._db = config.milvus.database_name
        self._collection = config.milvus.collection_name

    def _get_client(self) -> _MilvusSDK:
        """延迟初始化客户端，首次调用时建立连接"""
        if self._client is None:
            try:
                self._client = _MilvusSDK(uri=self._uri, db_name=self._db)  # 连接指定 database
                logger.debug(f"Milvus 连接成功: {self._uri}/{self._db}")
            except Exception as e:
                logger.error(f"Milvus 连接失败: {e}")
                raise
        return self._client

    def search(
        self,
        query_vectors: list[list[float]],  # 查询向量列表
        limit: int,                        # 返回最近邻数量
        output_fields: list[str],          # 需要返回的字段
        filter_expr: Optional[str] = None, # 标量过滤表达式，如 "source == 'java'"
    ) -> list[list[dict]]:
        """向量相似度搜索，返回每个查询的 Top-K 结果"""
        client = self._get_client()
        search_params = {"metric_type": "IP", "params": {"nprobe": 16}}  # 内积相似度，扫描 16 个聚类
        results = client.search(
            collection_name=self._collection,
            data=query_vectors,
            limit=limit,
            output_fields=output_fields,
            search_params=search_params,
            filter=filter_expr or "",  # 空字符串表示不过滤
        )
        return results

    def ping(self) -> bool:
        """健康探测，列出集合验证连接可用"""
        try:
            client = self._get_client()
            client.list_collections()  # 列出集合作为连通性检查
            return True
        except Exception as e:
            logger.error(f"Milvus ping 失败: {e}")
            return False

    @property
    def collection_name(self) -> str:
        """返回当前使用的集合名称"""
        return self._collection


# 模块级单例
milvus_client = MilvusClient()
