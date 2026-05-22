# 黑马程序员智能问答系统 — 项目执行手册

**版本**: v1.1.0  
**日期**: 2026-05-19  
**适用对象**: 新人入职、运维人员、测试工程师  
**关联文档**:
[产品需求文档](./product_requirement_document.md) ·
[技术设计文档](./technical_design_document.md)

---

## 目录

1. [项目概览](#1-项目概览)
2. [环境依赖清单](#2-环境依赖清单)
3. [新人快速上手（首次运行）](#3-新人快速上手首次运行)
4. [配置说明](#4-配置说明)
5. [启动与停止](#5-启动与停止)
6. [运行测试](#6-运行测试)
7. [接口验证](#7-接口验证)
8. [日常运维操作](#8-日常运维操作)
9. [日志查看与分析](#9-日志查看与分析)
10. [常见问题排查](#10-常见问题排查)
11. [数据库初始化](#11-数据库初始化)
12. [目录结构速查](#12-目录结构速查)

---

## 1. 项目概览

黑马程序员智能问答系统是一套基于 **RAG（检索增强生成）+ Qwen 大语言模型** 的 IT 培训答疑平台，为学员提供 7×24 小时在线技术答疑服务。

| 维度 | 说明 |
|------|------|
| **后端框架** | FastAPI 0.136 + Uvicorn |
| **大语言模型** | Qwen-3.6（阿里云 DashScope） |
| **向量数据库** | Milvus 2.4（RAG 检索） |
| **关系数据库** | MySQL 8.0（知识图谱、父块存储） |
| **缓存/会话** | Redis 7.0（会话管理、学科缓存） |
| **前端** | 原生 HTML + CSS + JS（无需打包） |
| **Python 版本** | 3.11 |
| **测试用例** | 168 个，100% 通过 |
| **知识库管理** | 文件上传入库（PDF/DOCX/XLSX/CSV/PPTX/TXT/MD/图片） |

**支持学科**：人工智能 / Java 开发 / 软件测试 / 运维与云计算 / 大数据

---

## 2. 环境依赖清单

在开始前，确保以下服务已安装并可运行：

| 依赖 | 版本要求 | 说明 |
|------|----------|------|
| Python | ≥ 3.11 | 建议通过 Miniconda 管理 |
| conda | ≥ 23.x | 虚拟环境管理 |
| MySQL | ≥ 8.0 | 本地或远程均可 |
| Redis | ≥ 7.0 | 本地或远程均可 |
| Milvus | ≥ 2.4 | 建议 Docker 部署 |
| Git | 任意版本 | 拉取代码 |

**DashScope API Key**：需在阿里云百炼平台申请，用于 LLM 推理和文本向量化。
申请地址：`https://dashscope.aliyun.com`

---

## 3. 新人快速上手（首次运行）

> 按步骤执行，约 10 分钟完成首次启动。

### Step 1 — 拉取代码

```bash
git clone <仓库地址>
cd agent_project_heima/01-vibe-coding
```

### Step 2 — 启动基础服务（MySQL / Redis / Milvus）

**方式 A：Docker Compose 一键启动（推荐）**

```bash
# 在项目根目录创建 docker-compose.yml（若不存在）
docker-compose up -d mysql redis milvus
```

**方式 B：本地已安装，手动确认运行状态**

```bash
# 检查 MySQL
mysql -u root -p -e "SELECT 1;"

# 检查 Redis（无密码模式）
redis-cli ping      # 预期返回：PONG

# 检查 Milvus
curl http://localhost:19530/healthz   # 预期返回：{"status":"ok"}
```

### Step 3 — 创建 conda 虚拟环境

```bash
conda create -n vibe_coding python=3.11 -y
conda activate vibe_coding
```

### Step 4 — 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### Step 5 — 配置环境变量

```bash
# 复制示例文件
cp .env.example .env

# 编辑 .env，填写真实值
# 必填：DASHSCOPE_API_KEY
# 可选：MYSQL_PASSWORD（若 config.ini 中已填写则可跳过）
```

`.env` 文件内容示例：

```ini
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MYSQL_PASSWORD=123456
```

### Step 6 — 修改 config.ini（按实际环境调整）

```bash
vim documents/config.ini
```

重点检查以下字段：

```ini
[mysql]
host = localhost        # MySQL 地址
user = root             # 数据库用户名（或自定义有权限的用户）
password = 123456       # 密码（也可通过环境变量 MYSQL_PASSWORD 覆盖）
database = subjects_kg  # 数据库名

[redis]
host = localhost
port = 6379
# password = xxxx       # 有密码时取消注释并填写；无密码保持注释

[milvus]
host = localhost
port = 19530

[logger]
log_file = /your/path/logs/app.log   # 改为本机有写权限的路径
```

### Step 7 — 初始化数据库

```bash
# 创建 MySQL 数据库（使用 root 或有权限的用户执行）
mysql -u root -p << 'EOF'
CREATE DATABASE IF NOT EXISTS subjects_kg DEFAULT CHARSET utf8mb4;
FLUSH PRIVILEGES;
EOF
```

> **说明**：应用表结构（`subject` / `document` / `parent_chunk`）由入库模块在首次运行时**自动幂等创建**，无需手动建表。详见 §11。

### Step 8 — 启动应用

```bash
conda activate vibe_coding

# 开发模式（热重载）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 生产模式（多 Worker）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Step 9 — 验证启动

```bash
# 健康检查
curl http://localhost:8000/api/v1/health

# 访问前端问答页面
open http://localhost:8000

# 访问知识库管理页面
open http://localhost:8000/upload.html
```

预期健康检查响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "healthy",
    "components": {
      "mysql":  {"status": "up"},
      "redis":  {"status": "up"},
      "milvus": {"status": "up"}
    }
  }
}
```

### Step 10 — 数据入库（可选，首次使用知识库）

**方式 A：前端页面上传（推荐新人使用）**

1. 浏览器访问 `http://localhost:8000/upload.html`
2. 点击学科 Chip 选择目标学科
3. 点击「选择多个文件」或「选择整个文件夹」，或直接拖拽文件到上传区
4. 点击「上传并入库」

**方式 B：CLI 命令行**

```bash
conda activate vibe_coding
cd /path/to/01-vibe-coding

# 入库整个目录
python scripts/ingest_data.py \
  --dir documents/data/ai_data \
  --subject ai \
  --name 人工智能

# 入库单个文件
python scripts/ingest_data.py \
  --file /path/to/file.pdf \
  --subject java \
  --name "Java开发"
```

**前提**：`DASHSCOPE_API_KEY` 环境变量必须已设置（用于向量化）。

建表语句见本文 [§11 数据库初始化](#11-数据库初始化)。

---

## 4. 配置说明

### 4.1 配置文件位置

```
documents/config.ini     # 主配置文件（提交至 Git，不含敏感密码）
.env                     # 敏感信息（不提交至 Git，本地维护）
.env.example             # 示例模板（可提交，用于新人参考）
```

### 4.2 完整配置项说明

```ini
# ── MySQL ────────────────────────────────────────
[mysql]
host     = localhost       # 数据库主机，远程填 IP
user     = root            # 数据库用户名（需有 subjects_kg 的 ALL 权限）
password = 123456          # 密码（环境变量 MYSQL_PASSWORD 优先级更高）
database = subjects_kg     # 数据库名

# ── Redis ────────────────────────────────────────
[redis]
host     = localhost
port     = 6379
# password = xxxx          # 无密码部署时保持注释；有密码时取消注释
db       = 0               # 使用 db0

# ── Milvus ───────────────────────────────────────
[milvus]
host            = localhost
port            = 19530
database_name   = itcast          # Milvus database 名称
collection_name = edurag_bj29     # 向量集合名称

# ── 大语言模型 ────────────────────────────────────
[llm]
model              = qwen-3.6
dashscope_base_url = https://dashscope.aliyuncs.com/compatible-mode/v1
# API Key 通过环境变量 DASHSCOPE_API_KEY 配置，禁止写入此文件

# ── RAG 检索参数 ──────────────────────────────────
[retrieval]
parent_chunk_size = 1200   # 父块 token 上限（影响上下文完整度）
child_chunk_size  = 300    # 子块 token 上限（影响检索精度）
chunk_overlap     = 50     # 块间重叠 token 数（避免边界信息丢失）
retrieval_k       = 10     # 向量初检数量（越大召回越全但越慢）
candidate_m       = 3      # 送入 LLM 的父块数（越大上下文越丰富但消耗 token 更多）

# ── 应用 ─────────────────────────────────────────
[app]
valid_sources          = ["ai", "java", "test", "ops", "bigdata"]  # 支持的学科代码
customer_service_phone = 10086   # LLM 无法回答时引导用户拨打的客服热线

# ── 日志 ─────────────────────────────────────────
[logger]
log_file = /your/path/logs/app.log   # 必须是本机有写权限的绝对路径
                                     # 路径不存在会自动创建目录
                                     # 路径无权限时自动回退到 logs/app.log
```

### 4.3 环境变量优先级

```
环境变量（.env / Shell export）  >  config.ini 中的值
```

| 环境变量 | 对应配置项 | 必填 |
|----------|-----------|------|
| `DASHSCOPE_API_KEY` | LLM API Key | **必填** |
| `MYSQL_PASSWORD` | mysql.password | 可选 |
| `REDIS_PASSWORD` | redis.password | 可选 |

---

## 5. 启动与停止

### 5.1 开发环境（热重载）

```bash
conda activate vibe_coding
cd /path/to/01-vibe-coding

# 加载 .env 并启动
export $(cat .env | grep -v ^# | xargs)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5.2 生产环境（推荐 systemd 托管）

**创建 systemd 服务文件** `/etc/systemd/system/vibe-coding.service`：

```ini
[Unit]
Description=黑马智能问答系统
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/vibe-coding/01-vibe-coding
EnvironmentFile=/opt/vibe-coding/01-vibe-coding/.env
ExecStart=/opt/miniconda3/envs/vibe_coding/bin/uvicorn \
    app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# 安装并启动服务
sudo systemctl daemon-reload
sudo systemctl enable vibe-coding
sudo systemctl start vibe-coding

# 查看状态
sudo systemctl status vibe-coding
```

### 5.3 常用操作命令

```bash
# 启动
sudo systemctl start vibe-coding

# 停止
sudo systemctl stop vibe-coding

# 重启（配置变更后执行）
sudo systemctl restart vibe-coding

# 实时查看日志
sudo journalctl -u vibe-coding -f
```

### 5.4 Nginx 反向代理配置（生产）

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # HTTP 重定向到 HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate     /etc/ssl/your-domain.crt;
    ssl_certificate_key /etc/ssl/your-domain.key;

    # 静态资源缓存
    location ~* \.(css|js|html)$ {
        proxy_pass http://127.0.0.1:8000;
        proxy_cache_valid 200 1h;
    }

    # SSE 流式接口：关闭缓冲
    location /api/v1/chat/stream {
        proxy_pass http://127.0.0.1:8000;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 120s;
    }

    # 普通接口
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 6. 运行测试

### 6.1 运行全套测试

```bash
conda activate vibe_coding
cd /path/to/01-vibe-coding

python -m pytest tests/ -v
```

预期输出末尾：

```
144 passed in 1.2s
```

### 6.2 按模块运行测试

```bash
# 仅测试配置模块
python -m pytest tests/test_config.py -v

# 仅测试会话管理
python -m pytest tests/test_session_manager.py -v

# 仅测试问答 API
python -m pytest tests/test_chat_api.py -v
```

### 6.3 测试文件与覆盖模块对应表

| 测试文件 | 覆盖模块 | 用例数 |
|----------|----------|--------|
| `test_config.py` | `app/config.py` | 18 |
| `test_logger.py` | `app/utils/logger.py` | 8 |
| `test_db_clients.py` | `app/database/` 三端客户端 | 14 |
| `test_session_manager.py` | `app/modules/session_manager.py` | 14 |
| `test_subject_manager.py` | `app/modules/subject_manager.py` | 13 |
| `test_rag_retriever.py` | `app/modules/rag_retriever.py` | 11 |
| `test_llm_client.py` | `app/modules/llm_client.py` | 15 |
| `test_qa_engine.py` | `app/modules/qa_engine.py` | 14 |
| `test_system_api.py` | `app/routers/system.py` | 10 |
| `test_sessions_api.py` | `app/routers/sessions.py` | 13 |
| `test_chat_api.py` | `app/routers/chat.py` | 14 |
| `test_ingest.py` | `app/ingest/` 文件解析/分块/向量化/入库 | 24 |
| **合计** | | **168** |

> 所有测试均使用 Mock，**不依赖真实数据库连接**，可在任何环境执行。

---

## 7. 接口验证

服务启动后，可通过以下方式验证各接口。

### 7.1 Swagger 自动文档

浏览器访问：`http://localhost:8000/docs`

### 7.2 命令行快速验证

```bash
BASE="http://localhost:8000/api/v1"

# 1. 健康检查
curl -s $BASE/health | python3 -m json.tool

# 2. 获取学科列表
curl -s $BASE/subjects | python3 -m json.tool

# 3. 创建会话
SESSION=$(curl -s -X POST $BASE/sessions | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['session_id'])")
echo "会话 ID: $SESSION"

# 4. 即时问答（需要 DashScope API Key 有效）
curl -s -X POST $BASE/chat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"question\": \"你好\", \"subject\": \"java\"}" \
  | python3 -m json.tool

# 5. 查看历史记录
curl -s "$BASE/sessions/$SESSION/history" | python3 -m json.tool

# 6. 清空历史
curl -s -X DELETE "$BASE/sessions/$SESSION/history" | python3 -m json.tool

# 7. 流式问答（SSE）
curl -s -X POST $BASE/chat/stream \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"question\": \"什么是多态？\", \"subject\": \"java\"}"
```

### 7.3 API 速查表

**问答与会话**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 系统健康检查 |
| GET | `/api/v1/subjects` | 获取学科列表（带 Redis 缓存） |
| POST | `/api/v1/sessions` | 创建新会话 |
| GET | `/api/v1/sessions/{id}/history` | 获取对话历史（分页） |
| DELETE | `/api/v1/sessions/{id}/history` | 清空对话历史 |
| POST | `/api/v1/chat` | 即时问答 |
| POST | `/api/v1/chat/stream` | 流式问答（SSE） |

**知识库管理（v1.1 新增）**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/ingest/upload` | 上传文件并入库（multipart/form-data，支持批量） |
| GET | `/api/v1/ingest/subjects` | 获取学科列表及支持的文件格式 |
| GET | `/api/v1/ingest/documents` | 查询已入库文档（支持学科筛选+分页） |

**前端页面**

| URL | 说明 |
|-----|------|
| `http://localhost:8000/` | 学生问答主页 |
| `http://localhost:8000/upload.html` | 知识库管理页面（上传入库） |
| `http://localhost:8000/docs` | Swagger API 文档 |

---

## 8. 日常运维操作

### 8.1 检查服务状态

```bash
# 查看进程
ps aux | grep uvicorn

# 检查端口
lsof -i :8000

# 健康检查
curl -s http://localhost:8000/api/v1/health | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d['data']['status'])"
```

### 8.2 更新代码并重启

```bash
cd /path/to/01-vibe-coding

git pull origin main                    # 拉取最新代码
pip install -r requirements.txt -q      # 更新依赖（有变更时）
sudo systemctl restart vibe-coding      # 重启服务
sudo systemctl status vibe-coding       # 确认服务正常
```

### 8.3 Redis 运维

```bash
# 连接 Redis（无密码）
redis-cli -h localhost -p 6379

# 查看当前活跃会话数量
redis-cli KEYS "session:*:meta" | wc -l

# 查看单个会话详情
redis-cli HGETALL "session:<session_id>:meta"

# 查看单个会话历史消息数
redis-cli LLEN "session:<session_id>:history"

# 手动清除学科缓存（配置变更后执行）
redis-cli DEL "subject:list"

# 查看内存使用
redis-cli INFO memory | grep used_memory_human
```

### 8.4 MySQL 运维

```bash
# 连接数据库
mysql -u root -p subjects_kg

# 查看各学科入库文档数量
SELECT subject_code, COUNT(*) AS doc_count FROM document GROUP BY subject_code;

# 查看各学科父块数量
SELECT subject, COUNT(*) AS chunk_count FROM parent_chunk GROUP BY subject;

# 查看最近入库的 10 个文档
SELECT id, subject_code, filename, chunk_count, created_at
FROM document ORDER BY created_at DESC LIMIT 10;

# 清除某学科所有数据（谨慎操作！）
-- DELETE FROM parent_chunk WHERE subject = 'ai';
-- DELETE FROM document WHERE subject_code = 'ai';
```

### 8.7 知识库入库运维

```bash
# CLI 批量入库（需 DASHSCOPE_API_KEY 已配置）
conda activate vibe_coding
export DASHSCOPE_API_KEY=sk-xxxx

python scripts/ingest_data.py \
  --dir /path/to/data \
  --subject ai \
  --name 人工智能

# 查看支持的文件格式
python -c "from app.ingest.file_parser import SUPPORTED_EXTENSIONS; print(sorted(SUPPORTED_EXTENSIONS))"

# 检查 Milvus 向量总数
python3 -c "
from pymilvus import MilvusClient
c = MilvusClient(uri='http://localhost:19530', db_name='itcast')
stats = c.get_collection_stats('edurag_bj29')
print('向量总数:', stats)
"

# 若需重建 Milvus 集合（谨慎：会丢失所有向量！）
python3 -c "
from pymilvus import MilvusClient
c = MilvusClient(uri='http://localhost:19530', db_name='itcast')
c.drop_collection('edurag_bj29')
print('已删除集合，下次入库时将自动重建（dim=1024）')
"
```

### 8.5 Milvus 运维

```bash
# 通过 Python 检查集合状态
python3 -c "
from pymilvus import MilvusClient
client = MilvusClient(uri='http://localhost:19530', db_name='itcast')
stats = client.get_collection_stats('edurag_bj29')
print('向量总数:', stats)
"

# 查看集合列表
python3 -c "
from pymilvus import MilvusClient
client = MilvusClient(uri='http://localhost:19530', db_name='itcast')
print(client.list_collections())
"
```

### 8.6 日志轮转维护

日志文件按大小自动轮转（单文件最大 100MB，保留 30 个备份）。

```bash
# 查看日志文件大小
ls -lh /path/to/logs/

# 手动清理超过 30 天的日志
find /path/to/logs/ -name "app.log.*" -mtime +30 -delete
```

---

## 9. 日志查看与分析

### 9.1 日志位置

| 环境 | 日志路径 |
|------|----------|
| 开发 | `./logs/app.log`（项目根目录自动创建） |
| 生产 | `config.ini [logger] log_file` 指定的路径 |
| systemd | `journalctl -u vibe-coding` |

### 9.2 日志格式

```
2026-05-19T10:01:02 | INFO     | modules.qa | 即时问答完成，耗时 1240ms，来源: 3 个
2026-05-19T10:01:05 | WARNING  | modules.rag | Milvus 检索失败，返回空上下文: timeout
2026-05-19T10:01:06 | ERROR    | modules.llm | LLM 即时调用失败: ReadTimeout
```

### 9.3 常用日志过滤命令

```bash
LOG="/path/to/logs/app.log"

# 查看最近 100 行
tail -100 $LOG

# 实时追踪（监控模式）
tail -f $LOG

# 过滤 ERROR 级别
grep "ERROR" $LOG | tail -50

# 过滤特定模块
grep "modules.qa" $LOG | tail -30

# 统计今日错误数量
grep "$(date +%Y-%m-%dT)" $LOG | grep "ERROR" | wc -l

# 查看响应时间超过 3 秒的请求
grep "耗时" $LOG | awk -F'耗时 ' '{print $2}' | awk -F'ms' '$1 > 3000 {print}'
```

---

## 10. 常见问题排查

### Q1：启动报错 `ModuleNotFoundError`

```bash
# 确认 conda 环境已激活
conda activate vibe_coding
which python   # 应指向 miniconda3/envs/vibe_coding/bin/python

# 重新安装依赖
pip install -r requirements.txt
```

---

### Q2：健康检查中 MySQL 显示 `down`

```bash
# 1. 确认 MySQL 服务运行
sudo systemctl status mysql

# 2. 确认用户名密码正确
mysql -u edu_rag -p subjects_kg -e "SELECT 1;"

# 3. 确认环境变量已加载
echo $MYSQL_PASSWORD

# 4. 检查 config.ini 中的 host/user/database 是否与实际一致
cat documents/config.ini | grep -A4 "\[mysql\]"
```

---

### Q3：健康检查中 Redis 显示 `down`

```bash
# 1. 确认 Redis 服务运行
redis-cli ping   # 返回 PONG 表示正常

# 2. 若 Redis 有密码，确认 config.ini 中 password 字段已取消注释
# 若 Redis 无密码，确认 password 行已注释掉（# password = xxx）

# 3. 确认端口未被占用
lsof -i :6379
```

---

### Q4：健康检查中 Milvus 显示 `down`

```bash
# 1. 确认 Milvus 容器运行
docker ps | grep milvus

# 2. 确认端口可达
curl http://localhost:19530/healthz

# 3. 若使用 Docker，检查端口映射
docker inspect milvus | grep -A5 "Ports"
```

---

### Q5：问答接口返回兜底文本（"系统繁忙，请拨打 10086"）

原因通常为 LLM 调用失败，排查步骤：

```bash
# 1. 确认 API Key 已配置
echo $DASHSCOPE_API_KEY   # 不应为空

# 2. 测试 API Key 是否有效
python3 -c "
import os
from openai import OpenAI
client = OpenAI(
    api_key=os.environ['DASHSCOPE_API_KEY'],
    base_url='https://dashscope.aliyuncs.com/compatible-mode/v1'
)
resp = client.chat.completions.create(
    model='qwen-3.6',
    messages=[{'role':'user','content':'hello'}],
    max_tokens=10
)
print('API 正常，回复:', resp.choices[0].message.content)
"

# 3. 查看日志中的 LLM 错误
grep "LLM.*失败\|llm.*error" logs/app.log | tail -20
```

---

### Q6：流式问答前端无输出

```bash
# 1. 确认 Nginx 未缓冲 SSE 响应（生产环境）
# 检查 Nginx 配置中 /api/v1/chat/stream 是否有 proxy_buffering off

# 2. 直接通过 curl 测试 SSE
SESSION_ID="<your-session-id>"
curl -N -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"question\":\"你好\"}"
# 应逐行输出 data: {...}
```

---

### Q7：`PermissionError` 创建日志目录失败

```bash
# 检查 config.ini 中的 log_file 路径
# 若路径不存在或无权限，系统会自动回退到项目目录下的 logs/app.log
# 手动创建并授权：
mkdir -p /your/log/path
chmod 755 /your/log/path
```

---

### Q8：文件上传入库失败（`503 DASHSCOPE_API_KEY 未配置`）

```bash
# 确认环境变量已设置
echo $DASHSCOPE_API_KEY   # 不应为空

# 若使用 systemd，确认 EnvironmentFile 中包含此变量
sudo systemctl cat vibe-coding | grep EnvironmentFile

# 临时手动注入环境变量并重启
export DASHSCOPE_API_KEY=sk-xxxx
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

### Q9：入库报错 `batch size is invalid` 或 `dimension is invalid`

这是 DashScope text-embedding-v3 的 API 限制：

- **批次限制**：单次最多 10 条（已内置，无需手动调整）
- **维度限制**：有效值为 `[64, 128, 256, 512, 768, 1024]`，**不支持 1536**

若出现此错误，检查 `app/ingest/embedder.py` 中的 `_EMBED_DIM` 和 `_BATCH_SIZE`：

```python
_EMBED_DIM = 1024   # ← 必须为 API 有效值之一
_BATCH_SIZE = 10    # ← 不超过 10
```

Milvus collection 的 `dim` 必须与 `_EMBED_DIM` 一致。若不一致，需先删除集合再重建：

```bash
python3 -c "
from pymilvus import MilvusClient
MilvusClient(uri='http://localhost:19530', db_name='itcast').drop_collection('edurag_bj29')
print('已删除，下次入库时自动重建')
"
```

---

### Q10：测试全部失败（import 报错）

```bash
# 确认在项目根目录执行 pytest，而非子目录
cd /path/to/01-vibe-coding
python -m pytest tests/ -v

# 确认 pyproject.toml 中没有覆盖 testpaths 配置
cat pyproject.toml | grep -A5 "\[tool.pytest"
```

---

## 11. 数据库初始化

### 11.1 MySQL 建库建表

> **注意**：以下表结构由 `app/ingest/ingestor.py` 的 `_ensure_mysql_schema()` **自动幂等创建**，首次运行入库时无需手动执行。此处仅供参考和手动恢复使用。

```sql
-- 1. 创建数据库（root 权限执行）
CREATE DATABASE IF NOT EXISTS subjects_kg DEFAULT CHARSET utf8mb4;
FLUSH PRIVILEGES;

-- 2. 切换到 subjects_kg 数据库
USE subjects_kg;

-- 3. 学科元数据表
CREATE TABLE IF NOT EXISTS `subject` (
    `id`         INT AUTO_INCREMENT PRIMARY KEY,
    `code`       VARCHAR(50) NOT NULL UNIQUE COMMENT '学科代码，如 ai / java',
    `name`       VARCHAR(100) NOT NULL            COMMENT '学科中文名称',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学科信息表';

-- 4. 已入库文档表
CREATE TABLE IF NOT EXISTS `document` (
    `id`           INT AUTO_INCREMENT PRIMARY KEY,
    `subject_code` VARCHAR(50)  NOT NULL          COMMENT '所属学科代码',
    `filename`     VARCHAR(255) NOT NULL          COMMENT '原始文件名',
    `filepath`     VARCHAR(512) NOT NULL          COMMENT '入库时文件绝对路径',
    `char_count`   INT DEFAULT 0                  COMMENT '提取文本字符数',
    `chunk_count`  INT DEFAULT 0                  COMMENT '父块数量',
    `created_at`   DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_filepath` (`filepath`(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='已入库文档表';

-- 5. 父块内容表（RAG 核心）
CREATE TABLE IF NOT EXISTS `parent_chunk` (
    `id`          INT AUTO_INCREMENT PRIMARY KEY, -- Milvus child 的 parent_id 引用此字段
    `document_id` INT NOT NULL                   COMMENT '所属文档 ID',
    `subject`     VARCHAR(50) NOT NULL           COMMENT '学科代码（冗余）',
    `chunk_index` INT NOT NULL                   COMMENT '在文档中的顺序编号（0-based）',
    `content`     MEDIUMTEXT NOT NULL            COMMENT '父块全文',
    `created_at`  DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_document_id` (`document_id`),
    INDEX `idx_subject`     (`subject`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='父块存储表';

-- 6. 初始化学科数据
INSERT IGNORE INTO `subject` (code, name) VALUES
  ('ai',      '人工智能'),
  ('java',    'Java 开发'),
  ('test',    '软件测试'),
  ('ops',     '运维与云计算'),
  ('bigdata', '大数据');
```

### 11.2 Milvus 集合初始化

> **注意**：集合由 `app/ingest/ingestor.py` 的 `_ensure_milvus_collection()` **自动幂等创建**，首次运行入库时无需手动执行。

```python
# 手动创建（恢复场景）—— 在 vibe_coding 环境中执行
from pymilvus import MilvusClient, DataType

client = MilvusClient(uri="http://localhost:19530", db_name="itcast")

schema = client.create_schema(auto_id=True, enable_dynamic_field=False)
schema.add_field("id",        DataType.INT64,        is_primary=True, auto_id=True)
schema.add_field("vector",    DataType.FLOAT_VECTOR, dim=1024)          # dim=1024，非 1536
schema.add_field("parent_id", DataType.INT64)                           # 对应 MySQL parent_chunk.id
schema.add_field("source",    DataType.VARCHAR,      max_length=50)     # 学科代码过滤字段

index_params = client.prepare_index_params()
index_params.add_index(
    field_name="vector",
    index_type="IVF_FLAT",
    metric_type="IP",
    params={"nlist": 128},
)

client.create_collection(
    collection_name="edurag_bj29",
    schema=schema,
    index_params=index_params,
)
print("Milvus 集合初始化完成（dim=1024）")
```

---

## 12. 目录结构速查

```
01-vibe-coding/
├── app/                          后端应用
│   ├── main.py                   FastAPI 入口，路由挂载（含 ingest 路由）
│   ├── config.py                 配置读取（config.ini + 环境变量）
│   ├── database/
│   │   ├── mysql_client.py       MySQL 连接池封装
│   │   ├── redis_client.py       Redis 连接池封装
│   │   └── milvus_client.py      Milvus 客户端封装
│   ├── ingest/                   知识库入库模块（v1.1 新增）
│   │   ├── __init__.py
│   │   ├── file_parser.py        多格式文件解析（PDF/DOCX/XLSX/CSV/PPTX/TXT/MD/图片）
│   │   ├── text_chunker.py       父子两级分块（1200/300/50，从 config 读取）
│   │   ├── embedder.py           子块向量化（DashScope text-embedding-v3，批次≤10，dim=1024）
│   │   └── ingestor.py           入库主流程（幂等 DDL + 双写 MySQL/Milvus）
│   ├── modules/
│   │   ├── session_manager.py    会话创建/历史/清空（Redis）
│   │   ├── subject_manager.py    学科列表查询（Redis 缓存）
│   │   ├── rag_retriever.py      RAG 检索主流程（Embedding→Milvus→MySQL）
│   │   ├── llm_client.py         LLM 即时/流式调用、问候识别
│   │   └── qa_engine.py          问答引擎主入口（整合 RAG + LLM + 会话）
│   ├── routers/
│   │   ├── system.py             GET /health, GET /subjects
│   │   ├── sessions.py           POST/GET/DELETE /sessions
│   │   ├── chat.py               POST /chat, POST /chat/stream
│   │   └── ingest.py             POST /ingest/upload, GET /ingest/subjects|documents
│   ├── models/
│   │   └── schemas.py            Pydantic 请求/响应模型
│   └── utils/
│       └── logger.py             结构化日志工具
├── scripts/
│   └── ingest_data.py            CLI 入库脚本（--file / --dir --subject --name）
├── tests/                        测试套件（168 个用例）
│   ├── conftest.py               共享 fixtures
│   ├── test_config.py
│   ├── test_logger.py
│   ├── test_db_clients.py
│   ├── test_session_manager.py
│   ├── test_subject_manager.py
│   ├── test_rag_retriever.py
│   ├── test_llm_client.py
│   ├── test_qa_engine.py
│   ├── test_system_api.py
│   ├── test_sessions_api.py
│   ├── test_chat_api.py
│   └── test_ingest.py            文件解析/分块/向量化/入库流程测试（24 个用例）
├── frontend/                     前端（原生 HTML/CSS/JS）
│   ├── index.html                学生问答主页面（含"知识库管理"导航链接）
│   ├── upload.html               知识库管理页面（文件上传/入库/文档列表）
│   ├── css/
│   │   ├── style.css             全局样式（问答页）
│   │   └── upload.css            上传页面专属样式
│   └── js/
│       ├── app.js                问答页交互逻辑（SSE、学科切换、会话管理）
│       └── upload.js             上传页面逻辑（拖拽/多选/文件夹/入库结果弹窗）
├── documents/
│   ├── config.ini                主配置文件
│   ├── data/                     示例数据
│   │   └── ai_data/              人工智能学科示例文档
│   │       ├── LLM基础知识.pdf
│   │       └── 人工智能就业课课程大纲.docx
│   ├── product_requirement_document.md
│   ├── technical_design_document.md
│   └── operation_manual.md       本文档
├── logs/                         日志目录（自动创建）
├── requirements.txt              Python 依赖锁定版本
└── .env.example                  环境变量示例模板
```

---

---

## 13. 变更记录

| 版本 | 日期 | 主要变更 |
|------|------|----------|
| v1.0.0 | 2026-05-19 | 初始版本：RAG 问答、会话管理、前端页面，144 个测试 |
| v1.1.0 | 2026-05-19 | 新增知识库入库模块及上传接口、知识库管理前端页面；MySQL 用户改为 root；Embedding 维度修正为 1024；测试增至 168 个 |

---

*如有疑问，请联系技术负责人或提交 Issue 至项目仓库。*
