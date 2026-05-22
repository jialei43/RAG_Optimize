from fastapi import FastAPI  # FastAPI 框架核心
from fastapi.middleware.cors import CORSMiddleware  # 跨域中间件
from fastapi.staticfiles import StaticFiles  # 静态文件服务
import os  # 操作系统路径工具

from app.routers import sessions, chat, system, ingest  # 业务路由模块

app = FastAPI(  # 创建应用实例
    title="黑马程序员智能问答系统",
    description="基于 RAG + Qwen 的 IT 培训智能答疑平台",
    version="1.0.0",
)

app.add_middleware(  # 配置 CORS，允许前端跨域访问
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境替换为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router, prefix="/api/v1", tags=["系统管理"])   # 挂载系统路由
app.include_router(sessions.router, prefix="/api/v1", tags=["会话管理"]) # 挂载会话路由
app.include_router(chat.router, prefix="/api/v1", tags=["智能问答"])     # 挂载问答路由
app.include_router(ingest.router, prefix="/api/v1", tags=["知识库管理"]) # 挂载入库路由

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")  # 前端目录绝对路径
if os.path.isdir(frontend_dir):  # 前端目录存在时才挂载静态文件
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
