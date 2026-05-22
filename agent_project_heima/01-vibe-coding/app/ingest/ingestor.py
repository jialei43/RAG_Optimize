"""
数据入库主流程。

执行顺序:
  1. 确保 MySQL 表结构存在（idempotent DDL）
  2. 确保 Milvus collection 存在（idempotent）
  3. 解析文件 → 父子分块 → 向量化子块
  4. 写 MySQL（subject / document / parent_chunk）
  5. 写 Milvus（子块向量 + parent_id + source 标量字段）
"""

from __future__ import annotations

import logging  # 日志
import os  # 路径拼接
from pathlib import Path  # 文件后缀判断
from typing import List, Optional  # 类型注解

from app.database.milvus_client import MilvusClient  # Milvus 客户端
from app.database.mysql_client import MySQLClient  # MySQL 客户端
from app.ingest.embedder import embed_texts  # 向量化接口
from app.ingest.file_parser import parse_file, SUPPORTED_EXTENSIONS  # 文件解析
from app.ingest.text_chunker import chunk_document, ParentChunk  # 分块

logger = logging.getLogger(__name__)  # 模块级 logger

# Milvus collection schema 参数
_MILVUS_DIM = 1024  # text-embedding-v3 有效维度（API 限制: 64/128/256/512/768/1024）
_MILVUS_INDEX_PARAMS = {  # IVF_FLAT + 内积，与 RAG 检索侧保持一致
    "index_type": "IVF_FLAT",
    "metric_type": "IP",
    "params": {"nlist": 128},
}

# --------------------------------------------------------------------------- #
# DDL 初始化
# --------------------------------------------------------------------------- #

_CREATE_SUBJECT_SQL = """
CREATE TABLE IF NOT EXISTS `subject` (
    `id`          INT AUTO_INCREMENT PRIMARY KEY,
    `code`        VARCHAR(50) NOT NULL UNIQUE COMMENT '学科代码，如 ai / java',
    `name`        VARCHAR(100) NOT NULL COMMENT '学科中文名称',
    `created_at`  DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学科信息表';
"""

_CREATE_DOCUMENT_SQL = """
CREATE TABLE IF NOT EXISTS `document` (
    `id`            INT AUTO_INCREMENT PRIMARY KEY,
    `subject_code`  VARCHAR(50) NOT NULL COMMENT '所属学科代码',
    `filename`      VARCHAR(255) NOT NULL COMMENT '原始文件名',
    `filepath`      VARCHAR(512) NOT NULL COMMENT '入库时文件绝对路径',
    `char_count`    INT DEFAULT 0 COMMENT '提取文本字符数',
    `chunk_count`   INT DEFAULT 0 COMMENT '父块数量',
    `created_at`    DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_filepath` (`filepath`(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='已入库文档表';
"""

_CREATE_PARENT_CHUNK_SQL = """
CREATE TABLE IF NOT EXISTS `parent_chunk` (
    `id`            INT AUTO_INCREMENT PRIMARY KEY,
    `document_id`   INT NOT NULL COMMENT '所属文档 ID',
    `subject`       VARCHAR(50) NOT NULL COMMENT '学科代码（冗余，加速检索）',
    `chunk_index`   INT NOT NULL COMMENT '在文档中的顺序编号（0-based）',
    `content`       MEDIUMTEXT NOT NULL COMMENT '父块全文（最大 16MB）',
    `created_at`    DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_document_id` (`document_id`),
    INDEX `idx_subject` (`subject`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='父块存储表';
"""


def _ensure_mysql_schema(client: MySQLClient) -> None:
    """幂等建表：表已存在则跳过，不会重复创建。"""
    with client.cursor() as cur:
        cur.execute(_CREATE_SUBJECT_SQL)  # 学科表
        cur.execute(_CREATE_DOCUMENT_SQL)  # 文档表
        cur.execute(_CREATE_PARENT_CHUNK_SQL)  # 父块表
    logger.info("MySQL 表结构已就绪")


def _ensure_milvus_collection(client: MilvusClient) -> None:
    """幂等建 collection：若已存在则跳过。"""
    sdk = client._get_client()  # 获取底层 SDK 实例
    col = client.collection_name

    if col in sdk.list_collections():  # 已存在则不重建
        logger.info("Milvus collection '%s' 已存在，跳过创建", col)
        return

    from pymilvus import DataType  # noqa: PLC0415  # 惰性导入
    schema = sdk.create_schema(
        auto_id=True,  # id 自增
        enable_dynamic_field=False,
    )
    schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)  # 主键
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=_MILVUS_DIM)  # 子块向量
    schema.add_field("parent_id", DataType.INT64)  # 对应 MySQL parent_chunk.id
    schema.add_field("source", DataType.VARCHAR, max_length=50)  # 学科代码，用于过滤

    index_params = sdk.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        index_type=_MILVUS_INDEX_PARAMS["index_type"],
        metric_type=_MILVUS_INDEX_PARAMS["metric_type"],
        params=_MILVUS_INDEX_PARAMS["params"],
    )

    sdk.create_collection(
        collection_name=col,
        schema=schema,
        index_params=index_params,
    )
    logger.info("Milvus collection '%s' 创建成功（dim=%d）", col, _MILVUS_DIM)


# --------------------------------------------------------------------------- #
# 核心入库逻辑
# --------------------------------------------------------------------------- #

def _upsert_subject(client: MySQLClient, code: str, name: str) -> None:
    """INSERT IGNORE 写入学科记录（已存在则忽略）。"""
    with client.cursor() as cur:
        cur.execute(
            "INSERT IGNORE INTO `subject` (code, name) VALUES (%s, %s)",
            (code, name),
        )


def _insert_document(
    client: MySQLClient,
    subject_code: str,
    filename: str,
    filepath: str,
    char_count: int,
    chunk_count: int,
) -> Optional[int]:
    """
    插入文档记录。若该 filepath 已入库则返回 None（幂等跳过）。

    Returns:
        新插入的 document.id，或 None（已存在则跳过）。
    """
    with client.cursor() as cur:
        # 检查是否已入库
        cur.execute("SELECT id FROM `document` WHERE filepath = %s", (filepath,))
        row = cur.fetchone()
        if row:
            logger.warning("文件已入库（document.id=%s），跳过: %s", row["id"], filepath)
            return None

        cur.execute(
            """
            INSERT INTO `document`
                (subject_code, filename, filepath, char_count, chunk_count)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (subject_code, filename, filepath, char_count, chunk_count),
        )
        doc_id = cur.lastrowid  # 获取自增主键
    logger.info("文档记录写入成功 document.id=%d: %s", doc_id, filename)
    return doc_id


def _insert_parent_chunks(
    client: MySQLClient,
    doc_id: int,
    subject: str,
    chunks: List[ParentChunk],
) -> List[int]:
    """
    批量写入父块，返回各行自增 ID 列表（顺序与 chunks 一致）。
    """
    ids: List[int] = []
    with client.cursor() as cur:
        for chunk in chunks:
            cur.execute(
                """
                INSERT INTO `parent_chunk`
                    (document_id, subject, chunk_index, content)
                VALUES (%s, %s, %s, %s)
                """,
                (doc_id, subject, chunk.index, chunk.text),
            )
            ids.append(cur.lastrowid)  # 记录自增 ID
    logger.info("父块写入完成，共 %d 块", len(ids))
    return ids


def _insert_child_vectors(
    client: MilvusClient,
    parent_ids: List[int],
    children_texts_per_parent: List[List[str]],
    vectors_flat: List[List[float]],
    source: str,
) -> None:
    """
    将子块向量批量写入 Milvus。

    Args:
        parent_ids: 父块 MySQL ID 列表
        children_texts_per_parent: 每个父块对应的子块文本列表
        vectors_flat: 所有子块向量（扁平列表，与子块文本顺序一致）
        source: 学科代码（标量过滤字段）
    """
    sdk = client._get_client()
    col = client.collection_name

    vector_idx = 0  # 全局子块向量游标
    rows: List[dict] = []

    for parent_id, children in zip(parent_ids, children_texts_per_parent):
        for _ in children:  # 每个子块生成一条 Milvus 记录
            rows.append({
                "vector": vectors_flat[vector_idx],  # 子块向量
                "parent_id": parent_id,  # 回查 MySQL 父块的 ID
                "source": source,  # 用于学科过滤
            })
            vector_idx += 1

    if rows:
        sdk.insert(collection_name=col, data=rows)  # 批量写入
        logger.info("Milvus 子块向量写入完成，共 %d 条", len(rows))


# --------------------------------------------------------------------------- #
# 公共入口
# --------------------------------------------------------------------------- #

def ingest_file(
    filepath: str,
    subject_code: str,
    subject_name: str,
    mysql: MySQLClient,
    milvus: MilvusClient,
) -> dict:
    """
    对单个文件执行完整的入库流程。

    Args:
        filepath:     文件绝对路径
        subject_code: 学科代码（如 "ai"）
        subject_name: 学科中文名（如 "人工智能"）
        mysql:        MySQL 客户端
        milvus:       Milvus 客户端

    Returns:
        {
            "file": str,       # 文件名
            "status": str,     # "ok" | "skipped" | "error"
            "parent_count": int,
            "child_count": int,
            "message": str,
        }
    """
    filename = os.path.basename(filepath)  # 仅文件名
    abs_path = os.path.abspath(filepath)  # 规范化绝对路径（幂等判重用）

    # 不支持格式直接跳过
    ext = Path(filepath).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return {
            "file": filename, "status": "skipped",
            "parent_count": 0, "child_count": 0,
            "message": f"不支持的文件格式: {ext}",
        }

    try:
        # 1. 解析文件文本
        logger.info(">>> 开始处理: %s", filename)
        raw_text = parse_file(abs_path)
        if not raw_text.strip():
            return {
                "file": filename, "status": "skipped",
                "parent_count": 0, "child_count": 0,
                "message": "文件内容为空",
            }

        # 2. 父子分块
        parent_chunks = chunk_document(raw_text)
        if not parent_chunks:
            return {
                "file": filename, "status": "skipped",
                "parent_count": 0, "child_count": 0,
                "message": "分块结果为空",
            }

        # 3. 收集所有子块文本并向量化
        all_children: List[str] = [c for pc in parent_chunks for c in pc.children]
        logger.info("向量化 %d 个子块...", len(all_children))
        vectors = embed_texts(all_children)  # 调用 DashScope API

        # 4. 写 MySQL
        _upsert_subject(mysql, subject_code, subject_name)  # 幂等写学科
        doc_id = _insert_document(
            mysql,
            subject_code=subject_code,
            filename=filename,
            filepath=abs_path,
            char_count=len(raw_text),
            chunk_count=len(parent_chunks),
        )
        if doc_id is None:  # 已入库，跳过
            return {
                "file": filename, "status": "skipped",
                "parent_count": 0, "child_count": 0,
                "message": "该文件已入库，幂等跳过",
            }

        parent_ids = _insert_parent_chunks(mysql, doc_id, subject_code, parent_chunks)

        # 5. 写 Milvus
        children_per_parent = [pc.children for pc in parent_chunks]
        _insert_child_vectors(milvus, parent_ids, children_per_parent, vectors, subject_code)

        total_children = sum(len(pc.children) for pc in parent_chunks)
        logger.info("<<< 入库完成: %s（父块 %d，子块 %d）", filename, len(parent_chunks), total_children)
        return {
            "file": filename, "status": "ok",
            "parent_count": len(parent_chunks),
            "child_count": total_children,
            "message": "入库成功",
        }

    except Exception as exc:
        logger.exception("文件入库失败 [%s]: %s", filename, exc)
        return {
            "file": filename, "status": "error",
            "parent_count": 0, "child_count": 0,
            "message": str(exc),
        }


def ingest_directory(
    directory: str,
    subject_code: str,
    subject_name: str,
    mysql: MySQLClient,
    milvus: MilvusClient,
) -> List[dict]:
    """
    递归处理目录下所有支持格式的文件。

    Args:
        directory:    目录路径
        subject_code: 学科代码
        subject_name: 学科中文名
        mysql / milvus: 数据库客户端

    Returns:
        每个文件的入库结果列表。
    """
    # 初始化表结构（幂等）
    _ensure_mysql_schema(mysql)
    _ensure_milvus_collection(milvus)

    results: List[dict] = []
    for root, _, files in os.walk(directory):  # 递归遍历
        for fname in sorted(files):  # 排序保证处理顺序稳定
            ext = Path(fname).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:  # 跳过不支持格式
                continue
            if fname.startswith("."):  # 跳过隐藏文件
                continue
            full_path = os.path.join(root, fname)
            result = ingest_file(full_path, subject_code, subject_name, mysql, milvus)
            results.append(result)

    return results
