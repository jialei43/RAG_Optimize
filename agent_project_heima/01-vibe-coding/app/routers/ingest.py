"""
文件上传与入库路由。

端点:
  POST /ingest/upload    上传并入库（支持批量文件 / 文件夹）
  GET  /ingest/subjects  获取可用学科列表
  GET  /ingest/documents 查询已入库文档列表
"""

import os  # 路径操作
import tempfile  # 临时目录保存上传文件
import shutil  # 清理临时目录
import logging  # 日志

from fastapi import APIRouter, File, Form, HTTPException, UploadFile  # FastAPI 组件
from fastapi.responses import JSONResponse  # JSON 响应
from typing import List, Optional  # 类型注解

from app.config import app_cfg  # 合法学科列表
from app.database.mysql_client import MySQLClient  # MySQL 客户端
from app.database.milvus_client import MilvusClient  # Milvus 客户端
from app.ingest.ingestor import ingest_file, _ensure_mysql_schema, _ensure_milvus_collection  # 入库核心
from app.ingest.file_parser import SUPPORTED_EXTENSIONS  # 支持的格式集合

router = APIRouter()  # 路由实例
logger = logging.getLogger(__name__)  # 模块级 logger

# 模块级数据库客户端（复用连接）
_mysql = MySQLClient()
_milvus = MilvusClient()

# 上传文件大小限制：100 MB（防止内存溢出）
_MAX_FILE_SIZE = 100 * 1024 * 1024


def _validate_subject(subject: str) -> None:
    """校验学科代码是否在白名单内，非法时抛 422。"""
    if subject not in app_cfg.valid_sources:
        raise HTTPException(
            status_code=422,
            detail=f"学科代码 '{subject}' 无效，可选值: {app_cfg.valid_sources}",
        )


def _check_api_key() -> None:
    """检查 DASHSCOPE_API_KEY 是否配置，未配置时返回 503。"""
    if not os.environ.get("DASHSCOPE_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="服务端未配置 DASHSCOPE_API_KEY，无法进行向量化，请联系管理员",
        )


# --------------------------------------------------------------------------- #
# 上传入库接口
# --------------------------------------------------------------------------- #

@router.post("/ingest/upload", summary="上传文件并入库（支持批量）")
async def upload_and_ingest(
    files: List[UploadFile] = File(..., description="支持同时上传多个文件"),
    subject: str = Form(..., description="学科代码，如 ai / java / test / ops / bigdata"),
    subject_name: Optional[str] = Form(None, description="学科中文名，不填则与 subject 相同"),
):
    """
    上传一个或多个文件，自动解析后写入 MySQL 和 Milvus。

    - **files**: 文件列表（multipart/form-data），支持多选或整文件夹
    - **subject**: 学科代码（必填）
    - **subject_name**: 学科中文名（选填）

    返回每个文件的入库结果。
    """
    _check_api_key()  # 优先检查 API Key
    _validate_subject(subject)  # 校验学科代码

    if not files:
        raise HTTPException(status_code=400, detail="未接收到任何文件")

    name = subject_name or subject  # 未填中文名时使用代码

    # 过滤掉空文件（浏览器有时会上传 0 字节占位符）
    valid_files = [f for f in files if f.filename]
    if not valid_files:
        raise HTTPException(status_code=400, detail="所有上传文件均无效")

    # 检查格式——提前拦截不支持的文件，避免写入临时目录后才报错
    unsupported = [
        f.filename for f in valid_files
        if os.path.splitext(f.filename)[1].lower() not in SUPPORTED_EXTENSIONS
    ]
    if unsupported:
        raise HTTPException(
            status_code=415,
            detail=f"以下文件格式不支持: {unsupported}。"
                   f"支持格式: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    # 初始化数据库结构（幂等）
    try:
        _ensure_mysql_schema(_mysql)
        _ensure_milvus_collection(_milvus)
    except Exception as exc:
        logger.error("数据库初始化失败: %s", exc)
        raise HTTPException(status_code=503, detail=f"数据库初始化失败: {exc}")

    results = []
    tmpdir = tempfile.mkdtemp(prefix="rag_upload_")  # 创建隔离临时目录

    try:
        for upload in valid_files:
            # 保留原始文件名（去掉路径前缀，兼容文件夹上传）
            safe_name = os.path.basename(upload.filename)
            tmp_path = os.path.join(tmpdir, safe_name)

            # 写临时文件（流式读取避免 OOM）
            total_bytes = 0
            with open(tmp_path, "wb") as f:
                while chunk := await upload.read(1024 * 1024):  # 每次读 1MB
                    total_bytes += len(chunk)
                    if total_bytes > _MAX_FILE_SIZE:
                        f.close()
                        os.unlink(tmp_path)
                        results.append({
                            "file": safe_name,
                            "status": "error",
                            "parent_count": 0,
                            "child_count": 0,
                            "message": f"文件超过 100MB 限制（{total_bytes // 1048576}MB）",
                        })
                        break
                    f.write(chunk)
                else:
                    # 文件写完，执行入库
                    result = ingest_file(
                        filepath=tmp_path,
                        subject_code=subject,
                        subject_name=name,
                        mysql=_mysql,
                        milvus=_milvus,
                    )
                    result["file"] = safe_name  # 展示原始文件名（非临时路径）
                    results.append(result)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)  # 无论成功失败都清理临时目录

    # 统计汇总
    ok_count = sum(1 for r in results if r["status"] == "ok")
    skip_count = sum(1 for r in results if r["status"] == "skipped")
    error_count = sum(1 for r in results if r["status"] == "error")

    return {
        "summary": {
            "total": len(results),
            "ok": ok_count,
            "skipped": skip_count,
            "error": error_count,
        },
        "results": results,
    }


# --------------------------------------------------------------------------- #
# 辅助查询接口
# --------------------------------------------------------------------------- #

@router.get("/ingest/subjects", summary="获取可用学科列表")
def get_ingest_subjects():
    """返回系统支持的学科代码和中文名映射。"""
    # 预定义中文名映射（学科代码 → 展示名）
    name_map = {
        "ai":      "人工智能",
        "java":    "Java 开发",
        "test":    "软件测试",
        "ops":     "运维",
        "bigdata": "大数据",
    }
    subjects = [
        {"code": code, "name": name_map.get(code, code)}
        for code in app_cfg.valid_sources
    ]
    return {"subjects": subjects, "supported_formats": sorted(SUPPORTED_EXTENSIONS)}


@router.get("/ingest/documents", summary="查询已入库文档")
def list_documents(
    subject: Optional[str] = None,  # 按学科筛选（不填返回全部）
    page: int = 1,
    page_size: int = 20,
):
    """列出已入库的文档，支持按学科筛选和分页。"""
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=422, detail="page >= 1，page_size 范围 1-100")

    try:
        offset = (page - 1) * page_size
        with _mysql.cursor() as cur:
            if subject:
                cur.execute(
                    """
                    SELECT id, subject_code, filename, char_count, chunk_count, created_at
                    FROM `document`
                    WHERE subject_code = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (subject, page_size, offset),
                )
            else:
                cur.execute(
                    """
                    SELECT id, subject_code, filename, char_count, chunk_count, created_at
                    FROM `document`
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (page_size, offset),
                )
            rows = cur.fetchall()

            # 查总数
            if subject:
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM `document` WHERE subject_code = %s",
                    (subject,),
                )
            else:
                cur.execute("SELECT COUNT(*) AS cnt FROM `document`")
            total = cur.fetchone()["cnt"]

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "documents": [
                {
                    "id": r["id"],
                    "subject": r["subject_code"],
                    "filename": r["filename"],
                    "char_count": r["char_count"],
                    "chunk_count": r["chunk_count"],
                    "created_at": str(r["created_at"]),
                }
                for r in rows
            ],
        }
    except Exception as exc:
        logger.error("查询文档列表失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"查询失败: {exc}")
