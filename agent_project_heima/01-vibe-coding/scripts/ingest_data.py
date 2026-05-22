"""
数据入库 CLI 脚本。

用法:
    conda activate vibe_coding
    export DASHSCOPE_API_KEY=sk-xxxx

    # 入库单个目录
    python scripts/ingest_data.py --dir documents/data/ai_data --subject ai --name 人工智能

    # 入库单个文件
    python scripts/ingest_data.py --file documents/data/ai_data/LLM基础知识.pdf --subject ai --name 人工智能
"""

import argparse  # 命令行参数解析
import logging  # 日志
import sys  # 退出码
import os  # 路径处理

# 将项目根目录加入 sys.path，使 app.* 可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database.mysql_client import MySQLClient  # MySQL 客户端
from app.database.milvus_client import MilvusClient  # Milvus 客户端
from app.ingest.ingestor import ingest_file, ingest_directory  # 入库接口
from app.config import milvus as milvus_cfg  # Milvus 配置

# 简单的控制台日志配置（脚本模式不用 RotatingFile）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest_data")  # 脚本专属 logger


def _print_summary(results: list[dict]) -> None:
    """打印入库汇总表格。"""
    ok = [r for r in results if r["status"] == "ok"]
    skipped = [r for r in results if r["status"] == "skipped"]
    error = [r for r in results if r["status"] == "error"]

    print("\n" + "=" * 60)
    print(f"入库汇总  总计: {len(results)}  成功: {len(ok)}  跳过: {len(skipped)}  失败: {len(error)}")
    print("=" * 60)

    for r in results:
        icon = {"ok": "✓", "skipped": "~", "error": "✗"}.get(r["status"], "?")
        print(
            f"  {icon} [{r['status']:7}] {r['file']:40}  "
            f"父块:{r['parent_count']:4}  子块:{r['child_count']:5}  {r['message']}"
        )

    if error:
        print(f"\n注意: {len(error)} 个文件入库失败，详见上方日志。")
        sys.exit(1)  # 有失败文件时非零退出


def main() -> None:
    """解析命令行参数，执行入库。"""
    parser = argparse.ArgumentParser(
        description="将文件入库到 MySQL + Milvus RAG 系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # 入库目标：--file 或 --dir 二选一
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", metavar="FILE", help="入库单个文件")
    group.add_argument("--dir", metavar="DIR", help="递归入库目录下所有支持文件")

    # 学科信息
    parser.add_argument(
        "--subject", required=True, metavar="CODE",
        help="学科代码（如 ai / java / test / ops / bigdata）",
    )
    parser.add_argument(
        "--name", default=None, metavar="NAME",
        help="学科中文名（默认与 --subject 相同）",
    )

    # 覆盖入库（忽略幂等判重）
    parser.add_argument(
        "--force", action="store_true",
        help="强制重新入库（暂未实现，预留）",
    )

    args = parser.parse_args()
    subject_name = args.name or args.subject  # 未指定中文名时用代码代替

    # 检查 API Key
    if not os.environ.get("DASHSCOPE_API_KEY"):
        logger.error("请先设置环境变量: export DASHSCOPE_API_KEY=sk-xxxx")
        sys.exit(1)

    # 初始化数据库客户端
    mysql = MySQLClient()
    milvus = MilvusClient()

    # 连接健康检查
    if not mysql.ping():
        logger.error("MySQL 连接失败，请检查 documents/config.ini 中的连接配置")
        sys.exit(1)
    if not milvus.ping():
        logger.error("Milvus 连接失败，请检查 documents/config.ini 中的 Milvus 配置")
        sys.exit(1)

    logger.info("数据库连接正常，开始入库...")
    logger.info("Milvus database: %s  collection: %s", milvus_cfg.database_name, milvus_cfg.collection_name)

    # 执行入库
    if args.file:
        result = ingest_file(
            filepath=args.file,
            subject_code=args.subject,
            subject_name=subject_name,
            mysql=mysql,
            milvus=milvus,
        )
        _print_summary([result])
    else:
        results = ingest_directory(
            directory=args.dir,
            subject_code=args.subject,
            subject_name=subject_name,
            mysql=mysql,
            milvus=milvus,
        )
        if not results:
            logger.warning("目录 %s 下未找到任何支持的文件", args.dir)
        else:
            _print_summary(results)


if __name__ == "__main__":
    main()
