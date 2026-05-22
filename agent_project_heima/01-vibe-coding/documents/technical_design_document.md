# 黑马程序员智能问答系统 — 技术设计文档 (TDD)

**版本**: v1.1.0  
**日期**: 2026-05-19  
**状态**: 正式  
**作者**: 技术架构组  
**关联文档**: [产品需求文档 PRD](./product_requirement_document.md)

---

## 目录

1. [文档说明](#1-文档说明)
2. [系统架构总览](#2-系统架构总览)
3. [技术选型](#3-技术选型)
4. [核心模块详细设计](#4-核心模块详细设计)
   - 4.1 RAG 检索模块
   - 4.2 会话管理模块
   - 4.3 LLM 集成模块
   - 4.4 学科过滤模块
   - 4.5 知识库入库模块（v1.1 新增）
5. [数据库设计](#5-数据库设计)
6. [API 接口设计](#6-api-接口设计)
7. [部署架构](#7-部署架构)
8. [性能设计](#8-性能设计)
9. [安全设计](#9-安全设计)
10. [监控与日志](#10-监控与日志)
11. [风险与应对](#11-风险与应对)

---

## 1. 文档说明

### 1.1 编写目的

本文档面向后端开发、前端开发、运维、测试等各技术团队，描述黑马程序员智能问答系统的完整技术实现方案，覆盖系统架构、模块设计、接口规范、数据库 Schema、部署方案及非功能性需求的落地策略，确保团队在统一的技术框架下协同开发。

### 1.2 适用范围

| 角色 | 关注章节 |
|------|----------|
| 后端开发 | 全部章节 |
| 前端开发 | §2、§6、§8 |
| 运维工程师 | §3、§7、§10 |
| 测试工程师 | §6、§8、§9 |
| 架构师 | §2、§3、§4、§7 |

### 1.3 术语与缩写

| 术语 | 说明 |
|------|------|
| RAG | Retrieval-Augmented Generation，检索增强生成 |
| LLM | Large Language Model，大语言模型 |
| Chunk | 文档切分后的文本片段 |
| Embedding | 文本向量化表示 |
| Parent Chunk | 父级文本块，提供上下文完整性 |
| Child Chunk | 子级文本块，用于精准向量检索 |
| KG | Knowledge Graph，知识图谱 |
| SSE | Server-Sent Events，服务端推送事件（流式响应） |
| TTL | Time To Live，缓存过期时间 |

---

## 2. 系统架构总览

### 2.1 架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                          客户端层 (Client Layer)                      │
│   Browser / Mobile (PC · Tablet · Phone)                             │
│   HTTP/HTTPS + SSE (流式模式) · multipart/form-data (文件上传)        │
└─────────────────────────────┬────────────────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────────────────┐
│                        接入层 (Gateway Layer)                         │
│   Nginx 反向代理 · 负载均衡 · SSL 终止 · 静态资源服务                  │
└─────────────────────────────┬────────────────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────────────────┐
│                       应用层 (Application Layer)                      │
│                                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌───────────┐  │
│  │  会话管理   │  │  问答核心    │  │  学科管理   │  │  系统监控 │  │
│  │  Session    │  │  QA Engine   │  │  Subject    │  │  Health   │  │
│  │  Manager    │  │              │  │  Manager    │  │  Check    │  │
│  └──────┬──────┘  └──────┬───────┘  └──────┬──────┘  └───────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  知识库入库管道（Ingest Pipeline）                             │   │
│  │  文件解析 → 父子分块 → Embedding → MySQL + Milvus 双写        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│         │                │                  │                        │
│         └────────────────┼──────────────────┘                       │
│                          │                                           │
│  ┌───────────────────────▼──────────────────────────────────────┐   │
│  │                   RAG Pipeline                                │   │
│  │  问候识别 → 学科校验 → 子块检索 → 父块召回 → Rerank → LLM    │   │
│  └───────────────────────────────────────────────────────────────┘  │
└──────┬────────────────────────────────────────────────┬─────────────┘
       │                                                │
┌──────▼──────────────────┐              ┌─────────────▼──────────────┐
│     存储层 (Storage)     │              │    外部服务 (External)      │
│                         │              │                            │
│  ┌──────┐  ┌─────────┐  │              │  ┌──────────────────────┐  │
│  │MySQL │  │  Redis  │  │              │  │  DashScope API       │  │
│  │知识图谱│  │  会话   │  │              │  │  qwen-3.6 LLM        │  │
│  │subjects│ │  缓存   │  │              │  │  Embedding 服务      │  │
│  │_kg   │  │  限流   │  │              │  └──────────────────────┘  │
│  └──────┘  └─────────┘  │              │                            │
│  ┌──────────────────┐   │              └────────────────────────────┘
│  │     Milvus       │   │
│  │  向量数据库       │   │
│  │  db: itcast      │   │
│  │  col: edurag_bj29│   │
│  └──────────────────┘   │
└─────────────────────────┘
```

### 2.2 架构设计原则

| 原则 | 落地方式 |
|------|----------|
| **高内聚低耦合** | 各功能模块独立，通过统一接口通信 |
| **可观测性** | 结构化日志 + 健康检查端点 + 关键指标埋点 |
| **优雅降级** | LLM 超时 → 兜底回复；向量检索失败 → 关键词检索 |
| **数据安全** | 敏感配置环境变量化，传输层 HTTPS |
| **水平扩展** | 无状态应用层，状态外置至 Redis/MySQL/Milvus |

---

## 3. 技术选型

### 3.1 技术栈概览

| 层次 | 组件 | 版本建议 | 说明 |
|------|------|----------|------|
| **Web 框架** | FastAPI | ≥ 0.111 | 原生异步支持，自动生成 OpenAPI 文档 |
| **大语言模型** | Qwen-3.6 (via DashScope) | — | 阿里云通义千问，国产合规，低延迟 |
| **向量数据库** | Milvus | ≥ 2.4 | 分布式向量检索，支持 ANN 索引 |
| **关系数据库** | MySQL | ≥ 8.0 | 存储知识图谱、学科元数据 |
| **缓存/会话** | Redis | ≥ 7.0 | 会话上下文、热点缓存、接口限流 |
| **Embedding 模型** | text-embedding-v3 (DashScope) | — | 与 Qwen 同生态，语义一致性强 |
| **接入层** | Nginx | ≥ 1.24 | 反向代理、负载均衡、静态服务 |
| **日志** | Python logging + RotatingFileHandler | — | 结构化日志，按天轮转 |
| **配置管理** | configparser (config.ini) | — | 分环境配置，敏感字段走环境变量 |

### 3.2 核心依赖清单

```
fastapi>=0.111.0          # Web 框架
uvicorn[standard]>=0.29   # ASGI 服务器
pymysql>=1.1              # MySQL 驱动
redis>=5.0                # Redis 客户端
pymilvus>=2.4             # Milvus 客户端
openai>=1.0               # OpenAI 兼容客户端（接入 DashScope）
dashscope>=1.19           # DashScope SDK (LLM)
langchain>=0.2            # RAG 编排框架
langchain-community>=0.2  # 向量检索器集成
pydantic>=2.7             # 数据校验
python-dotenv>=1.0        # 环境变量加载
# ── 文件解析（v1.1 新增）───────────────────────────────────────
pypdf>=4.0                # PDF 文本提取
python-docx>=1.0          # DOCX 文档解析（含表格）
openpyxl>=3.1             # Excel (.xlsx/.xlsm) 解析
python-pptx>=1.0          # PowerPoint (.pptx) 解析
Pillow>=10.0              # 图片元信息读取
python-multipart>=0.0.9   # FastAPI multipart/form-data 文件上传
socksio>=1.0              # SOCKS 代理支持（httpx 依赖）
```

---

## 4. 核心模块详细设计

### 4.1 RAG 检索模块

#### 4.1.1 父子块检索策略

本系统采用 **Parent-Child Chunking** 策略，平衡检索精度与上下文完整性：

```
原始文档
    │
    ├── Parent Chunk (1200 tokens, overlap=50)   ← 存入 MySQL / 文件系统
    │       └── Child Chunk 1 (300 tokens)       ← 向量化后存入 Milvus
    │       └── Child Chunk 2 (300 tokens)       ← 向量化后存入 Milvus
    │       └── Child Chunk 3 (300 tokens)       ← 向量化后存入 Milvus
    │       └── Child Chunk 4 (300 tokens)       ← 向量化后存入 Milvus
    │
    └── Parent Chunk N ...
```

**检索流程**:

```
用户问题
    │
    ▼
[1] 向量化 (Embedding)
    │  使用 text-embedding-v3 将问题转为向量
    ▼
[2] 子块向量检索 (Milvus ANN Search)
    │  retrieval_k=10，召回 Top-10 相关子块
    ▼
[3] 父块回溯
    │  根据子块的 parent_id 召回对应父块
    │  去重后取 candidate_m=3 个父块
    ▼
[4] 上下文组装
    │  将 3 个父块内容拼接为 context
    ▼
[5] Prompt 构建
    │  system prompt + context + 对话历史 + 用户问题
    ▼
[6] LLM 推理 (Qwen-3.6)
    │  即时模式: 一次性返回
    │  流式模式: SSE 逐 token 推送
    ▼
[7] 返回答案
```

#### 4.1.2 检索参数配置

```ini
[retrieval]
parent_chunk_size = 1200   # 父块 token 上限
child_chunk_size  = 300    # 子块 token 上限，控制向量精度
chunk_overlap     = 50     # 块间重叠，避免边界信息丢失
retrieval_k       = 10     # ANN 初检数量
candidate_m       = 3      # 最终送入 LLM 的父块数
```

#### 4.1.3 Milvus 集合 Schema

```python
# Collection: edurag_bj29  (database: itcast)
# 由 app/ingest/ingestor.py _ensure_milvus_collection() 幂等创建
fields = [
    FieldSchema(name="id",        dtype=DataType.INT64,        is_primary=True, auto_id=True),
    FieldSchema(name="vector",    dtype=DataType.FLOAT_VECTOR, dim=1024),         # 子块向量（dim=1024）
    FieldSchema(name="parent_id", dtype=DataType.INT64),                          # 关联 MySQL parent_chunk.id
    FieldSchema(name="source",    dtype=DataType.VARCHAR,      max_length=50),    # 学科代码（用于过滤）
]
# 索引策略: IVF_FLAT，nlist=128，metric_type=IP（内积相似度）
# 注意: text-embedding-v3 有效维度为 [64,128,256,512,768,1024]，不支持 1536
```

### 4.2 会话管理模块

#### 4.2.1 会话存储结构

会话数据存储于 Redis，Key 设计遵循命名空间规范：

```
session:{session_id}:meta    → Hash   会话元数据 (创建时间、学科、消息数)
session:{session_id}:history → List   对话历史 (JSON 序列化的消息列表)
```

**TTL 策略**: 会话默认保留 **24 小时**，每次活跃操作重置 TTL。

#### 4.2.2 会话数据模型

```python
# 会话元数据 (存入 Redis Hash)
class SessionMeta:
    session_id:    str       # UUID v4
    created_at:    datetime  # 创建时间 (ISO 8601)
    last_active:   datetime  # 最后活跃时间
    subject:       str       # 当前选择的学科，默认 ""
    message_count: int       # 累计消息数

# 历史消息单条记录 (存入 Redis List，JSON 序列化)
class Message:
    role:       str       # "user" | "assistant"
    content:    str       # 消息内容
    created_at: datetime  # 消息时间戳
```

#### 4.2.3 会话生命周期

```
首次请求
    │
    ▼
生成 session_id (UUID4)
    │
    ▼
写入 Redis (TTL=86400s)
    │
    ├── 每次问答 → 追加 history，重置 TTL
    │
    ├── 用户清空 → DEL session:{id}:history (保留 meta)
    │
    └── TTL 到期 → Redis 自动清理
```

### 4.3 LLM 集成模块

#### 4.3.1 接入方式

通过 DashScope OpenAI 兼容接口接入 Qwen-3.6：

```python
# 连接配置
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
model    = "qwen-3.6"
api_key  = os.environ["DASHSCOPE_API_KEY"]   # 禁止硬编码，必须从环境变量读取
```

#### 4.3.2 Prompt 工程

```
┌─────────────────────────────────────────────────────────────┐
│  System Prompt                                              │
│  "你是黑马程序员的专属学习助手，专注于 IT 技术答疑。         │
│   请根据以下参考资料回答学生问题，如无法从资料中找到答案，   │
│   请引导学生拨打客服热线 10086。"                            │
├─────────────────────────────────────────────────────────────┤
│  Context (RAG 召回的 3 个父块，按相关性排序)                 │
├─────────────────────────────────────────────────────────────┤
│  对话历史 (最近 N 轮，受 token 预算控制)                     │
├─────────────────────────────────────────────────────────────┤
│  User: {当前问题}                                            │
└─────────────────────────────────────────────────────────────┘
```

#### 4.3.3 流式与非流式模式

| 参数 | 即时模式 | 流式模式 |
|------|----------|----------|
| `stream` | `False` | `True` |
| 响应格式 | JSON `{"answer": "..."}` | `text/event-stream` (SSE) |
| 适用场景 | 简单问题、API 调用 | 复杂问题、前端实时展示 |
| 超时设置 | 10s | 60s (首 token 超时 10s) |

#### 4.3.4 兜底策略

```
LLM 调用失败
    ├── 超时 (>10s)       → 返回: "系统繁忙，请稍后再试或拨打 10086"
    ├── API 限流 (429)    → 指数退避重试 3 次，仍失败则返回兜底语
    └── 服务异常 (5xx)    → 记录错误日志，返回兜底语，触发告警
```

### 4.5 知识库入库模块（v1.1 新增）

#### 4.5.1 模块位置

```
app/ingest/
├── file_parser.py    # 多格式文件解析（16 种格式）
├── text_chunker.py   # 父子两级分块
├── embedder.py       # 子块向量化（DashScope text-embedding-v3 + 批次重试）
└── ingestor.py       # 入库主流程（幂等 DDL + 双写 MySQL/Milvus）

scripts/
└── ingest_data.py    # CLI 命令行入口
```

#### 4.5.2 支持的文件格式

| 格式 | 扩展名 | 依赖库 | 备注 |
|------|--------|--------|------|
| PDF | `.pdf` | pypdf | 文本型 PDF；扫描件需 Tesseract OCR |
| Word | `.docx` | python-docx | 含段落和表格提取 |
| Word (老版) | `.doc` | antiword / LibreOffice | 需系统安装，未安装则跳过 |
| Excel | `.xlsx` `.xlsm` `.xls` | openpyxl / pandas | 多 Sheet 转管道符文本 |
| CSV | `.csv` | pandas | 自动识别 UTF-8 / GBK 编码 |
| PPT | `.pptx` | python-pptx | 逐幻灯片提取文本框 |
| 纯文本 | `.txt` `.md` | 内置 | 自动识别编码（UTF-8/GBK） |
| 图片 | `.png` `.jpg` `.jpeg` `.gif` `.bmp` `.webp` | Pillow | 仅返回元信息；OCR 需安装 Tesseract |

#### 4.5.3 入库流程

```
上传文件 / CLI 指定路径
      │
      ▼
[1] 幂等初始化
      │  _ensure_mysql_schema()   — CREATE TABLE IF NOT EXISTS
      │  _ensure_milvus_collection() — 若不存在则创建 dim=1024 集合
      ▼
[2] 文件解析 (file_parser.parse_file)
      │  根据后缀分发到对应解析器，返回纯文本
      ▼
[3] 父子分块 (text_chunker.chunk_document)
      │  父块: 1200 字符，重叠 50
      │  子块: 300 字符，重叠 50
      ▼
[4] 向量化 (embedder.embed_texts)
      │  批次 ≤ 10（API 限制）
      │  失败自动重试 3 次
      ▼
[5] 写 MySQL
      │  INSERT IGNORE INTO subject (幂等写学科)
      │  INSERT INTO document (filepath 唯一约束，已入库则跳过)
      │  批量 INSERT INTO parent_chunk
      ▼
[6] 写 Milvus
      │  INSERT child 向量（字段: vector, parent_id, source）
      ▼
返回每个文件的结果 {status, parent_count, child_count, message}
```

#### 4.5.4 Embedding 规格

| 参数 | 值 |
|------|----|
| 模型 | `text-embedding-v3` |
| 向量维度 | **1024**（有效值 64/128/256/512/768/1024） |
| 批次大小 | **10**（API 单次上限） |
| 重试次数 | 3 次，间隔 2 秒 |
| 接入方式 | OpenAI 兼容接口（与 LLM 一致） |

#### 4.5.5 幂等保障

- **重复入库保护**：`document` 表对 `filepath` 设 UNIQUE 约束，相同文件路径第二次入库时直接跳过
- **重复学科保护**：使用 `INSERT IGNORE` 写 `subject` 表
- **重建集合保护**：`_ensure_milvus_collection()` 先调用 `list_collections()` 检查，已存在则跳过

---

### 4.4 学科过滤模块

#### 4.4.1 支持学科

```python
# 来自 config.ini [app] valid_sources
VALID_SOURCES = ["ai", "java", "test", "ops", "bigdata"]

# 中文展示名称映射
SOURCE_LABELS = {
    "ai":      "人工智能",
    "java":    "Java 开发",
    "test":    "软件测试",
    "ops":     "运维与云计算",
    "bigdata": "大数据",
}
```

#### 4.4.2 过滤逻辑

```
用户选择学科 (可选)
    │
    ├── 未选择 → Milvus 全集合检索，不添加 source 过滤条件
    │
    └── 已选择 → 添加 Milvus 标量过滤: expr="source == '{subject}'"
                 同时在 system prompt 中注入学科上下文提示
```

#### 4.4.3 问候识别

```python
# 规则 + LLM 双路识别
GREETING_PATTERNS = [
    r"^(你好|您好|hi|hello|嗨|哈喽|早上好|下午好|晚上好)[\s，,。.！!]*$"
]

def is_greeting(text: str) -> bool:
    """优先正则匹配，节省 LLM token 消耗"""
    # 正则命中 → 直接返回 True
    # 未命中 → 调用 LLM 判断 (轻量 classify prompt)
```

---

## 5. 数据库设计

### 5.1 MySQL — 知识图谱库 (subjects_kg)

#### 5.1.1 表：subject (学科元数据)

```sql
CREATE TABLE subject (
    id          INT         UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    code        VARCHAR(32) NOT NULL UNIQUE COMMENT '学科代码，对应 valid_sources',
    name        VARCHAR(64) NOT NULL            COMMENT '学科中文名称',
    description TEXT                            COMMENT '学科简介',
    is_active   TINYINT(1)  NOT NULL DEFAULT 1  COMMENT '是否启用: 1启用 0禁用',
    created_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_code (code),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学科元数据';
```

#### 5.1.2 表：document (已入库文档)

```sql
-- 由 app/ingest/ingestor.py _ensure_mysql_schema() 幂等创建
CREATE TABLE IF NOT EXISTS `document` (
    `id`            INT AUTO_INCREMENT PRIMARY KEY,
    `subject_code`  VARCHAR(50)  NOT NULL                COMMENT '所属学科代码（冗余，加速查询）',
    `filename`      VARCHAR(255) NOT NULL                COMMENT '原始文件名',
    `filepath`      VARCHAR(512) NOT NULL                COMMENT '入库时文件绝对路径',
    `char_count`    INT DEFAULT 0                        COMMENT '提取文本字符数',
    `chunk_count`   INT DEFAULT 0                        COMMENT '父块数量',
    `created_at`    DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_filepath` (`filepath`(255))           -- 幂等防重入库的核心约束
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='已入库文档表';
```

#### 5.1.3 表：parent_chunk (父块存储)

```sql
-- 由 app/ingest/ingestor.py _ensure_mysql_schema() 幂等创建
CREATE TABLE IF NOT EXISTS `parent_chunk` (
    `id`            INT AUTO_INCREMENT PRIMARY KEY,       -- Milvus child 的 parent_id 引用此字段
    `document_id`   INT NOT NULL                         COMMENT '所属文档 ID',
    `subject`       VARCHAR(50) NOT NULL                 COMMENT '学科代码（冗余，加速检索）',
    `chunk_index`   INT NOT NULL                         COMMENT '在文档中的顺序编号（0-based）',
    `content`       MEDIUMTEXT NOT NULL                  COMMENT '父块全文（最大 16MB）',
    `created_at`    DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_document_id` (`document_id`),
    INDEX `idx_subject`     (`subject`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='父块存储表';
```

### 5.2 Redis — 会话与缓存

| Key 模式 | 类型 | 内容 | TTL |
|----------|------|------|-----|
| `session:{id}:meta` | Hash | 会话元数据 | 86400s (24h) |
| `session:{id}:history` | List | 消息历史 JSON 列表 | 86400s (24h) |
| `subject:list` | String | 学科列表 JSON 缓存 | 3600s (1h) |
| `ratelimit:{ip}` | String | IP 请求计数 | 60s |

### 5.3 Milvus — 向量存储

| 属性 | 值 |
|------|----|
| Database | `itcast` |
| Collection | `edurag_bj29` |
| 向量字段 | `vector` (FLOAT_VECTOR) |
| **向量维度** | **1024**（text-embedding-v3 有效值，非 1536） |
| 标量字段 | `parent_id` (INT64) · `source` (VARCHAR 50) |
| 索引类型 | IVF_FLAT，nlist=128 |
| 相似度度量 | IP (内积) |
| 副本数量 | 1（生产环境建议 2） |
| 管理工具 | Attu（:30000 端口，Docker 容器 crazy_swartz） |

---

## 6. API 接口设计

**Base URL**: `http(s)://{host}/api/v1`  
**认证方式**: 当前版本内网部署，通过 Nginx IP 白名单控制；后续版本扩展 JWT Bearer Token。  
**统一响应格式**:

```json
{
  "code":    0,          // 0=成功，非0=业务错误码
  "message": "success",  // 描述信息
  "data":    {}          // 业务数据，失败时为 null
}
```

---

### 6.1 会话管理接口

#### POST /sessions — 创建会话

**请求体**: 无  
**响应**:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "session_id":  "550e8400-e29b-41d4-a716-446655440000",
    "created_at":  "2026-05-19T10:00:00+08:00"
  }
}
```

---

#### GET /sessions/{session_id}/history — 获取对话历史

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | 会话 ID |

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码 |
| `page_size` | int | 20 | 每页条数，最大 100 |

**响应**:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "total":   42,
    "page":    1,
    "page_size": 20,
    "messages": [
      {
        "role":       "user",
        "content":    "Java 的多态是什么？",
        "created_at": "2026-05-19T10:01:00+08:00"
      },
      {
        "role":       "assistant",
        "content":    "多态是面向对象编程的三大特性之一...",
        "created_at": "2026-05-19T10:01:02+08:00"
      }
    ]
  }
}
```

---

#### DELETE /sessions/{session_id}/history — 清空对话历史

**响应**:

```json
{
  "code": 0,
  "message": "历史记录已清空",
  "data": null
}
```

---

### 6.2 问答接口

#### POST /chat — 即时问答

**请求体**:

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "question":   "Java 中的 HashMap 和 HashTable 有什么区别？",
  "subject":    "java"   // 可选，不传则全学科检索
}
```

**字段约束**:

| 字段 | 类型 | 必填 | 约束 |
|------|------|------|------|
| `session_id` | string | 是 | UUID v4 格式 |
| `question` | string | 是 | 长度 1–500 字符 |
| `subject` | string | 否 | 枚举值: ai / java / test / ops / bigdata |

**响应**:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "answer":       "HashMap 是非线程安全的，允许 null 键值...",
    "sources": [
      {
        "parent_id": "doc_001_chunk_003",
        "subject":   "java",
        "excerpt":   "HashMap 底层基于数组+链表+红黑树实现..."
      }
    ],
    "response_time_ms": 1240
  }
}
```

---

#### POST /chat/stream — 流式问答 (SSE)

**请求体**: 同 `/chat`

**响应**: `Content-Type: text/event-stream`

```
data: {"type": "start", "session_id": "..."}

data: {"type": "token", "content": "HashMap"}

data: {"type": "token", "content": " 是非线程安全的"}

data: {"type": "token", "content": "，允许 null 键值..."}

data: {"type": "sources", "sources": [...]}

data: {"type": "end", "response_time_ms": 1580}

```

**错误事件**:

```
data: {"type": "error", "code": 5001, "message": "LLM 服务超时"}

```

---

### 6.3 系统管理接口

#### GET /health — 系统健康检查

**响应**:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status":   "healthy",
    "timestamp": "2026-05-19T10:00:00+08:00",
    "components": {
      "mysql":  {"status": "up",   "latency_ms": 2},
      "redis":  {"status": "up",   "latency_ms": 1},
      "milvus": {"status": "up",   "latency_ms": 8},
      "llm":    {"status": "up",   "latency_ms": 320}
    }
  }
}
```

---

#### GET /subjects — 获取学科列表

**响应**:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "subjects": [
      {"code": "ai",      "name": "人工智能"},
      {"code": "java",    "name": "Java 开发"},
      {"code": "test",    "name": "软件测试"},
      {"code": "ops",     "name": "运维与云计算"},
      {"code": "bigdata", "name": "大数据"}
    ]
  }
}
```

---

### 6.4 知识库管理接口（v1.1 新增）

#### POST /ingest/upload — 上传文件并入库

**请求格式**: `multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `files` | File[] | 是 | 支持同时上传多个文件（批量或文件夹） |
| `subject` | string | 是 | 学科代码（ai/java/test/ops/bigdata） |
| `subject_name` | string | 否 | 学科中文名，不填则与 subject 相同 |

**文件限制**：单文件最大 100MB，格式限于支持列表（§4.5.2）。

**响应**:

```json
{
  "summary": {
    "total": 2,
    "ok": 2,
    "skipped": 0,
    "error": 0
  },
  "results": [
    {
      "file": "LLM基础知识.pdf",
      "status": "ok",
      "parent_count": 8,
      "child_count": 36,
      "message": "入库成功"
    },
    {
      "file": "人工智能就业课课程大纲.docx",
      "status": "ok",
      "parent_count": 10,
      "child_count": 46,
      "message": "入库成功"
    }
  ]
}
```

**status 枚举**:

| 值 | 含义 |
|----|------|
| `ok` | 入库成功 |
| `skipped` | 已入库（幂等跳过）或内容为空 |
| `error` | 解析/向量化/写库失败 |

---

#### GET /ingest/subjects — 获取学科与支持格式列表

**响应**:

```json
{
  "subjects": [
    {"code": "ai", "name": "人工智能"},
    {"code": "java", "name": "Java 开发"}
  ],
  "supported_formats": [".bmp", ".csv", ".doc", ".docx", ".gif",
                        ".jpeg", ".jpg", ".md", ".pdf", ".png",
                        ".pptx", ".txt", ".webp", ".xls", ".xlsm", ".xlsx"]
}
```

---

#### GET /ingest/documents — 查询已入库文档

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `subject` | string | — | 按学科过滤，不填返回全部 |
| `page` | int | 1 | 页码（≥1） |
| `page_size` | int | 20 | 每页条数（1-100） |

**响应**:

```json
{
  "total": 2,
  "page": 1,
  "page_size": 20,
  "documents": [
    {
      "id": 1,
      "subject": "ai",
      "filename": "LLM基础知识.pdf",
      "char_count": 8261,
      "chunk_count": 8,
      "created_at": "2026-05-19 09:51:02"
    }
  ]
}
```

---

### 6.5 业务错误码

| 错误码 | HTTP 状态 | 说明 |
|--------|-----------|------|
| 0 | 200 | 成功 |
| 1001 | 400 | 参数校验失败 |
| 1002 | 400 | 问题内容为空或超长 |
| 1003 | 400 | 学科代码不合法 |
| 2001 | 404 | 会话不存在或已过期 |
| 3001 | 429 | 请求频率超限 |
| 4001 | 415 | 上传文件格式不支持 |
| 4002 | 400 | 上传文件列表为空 |
| 5001 | 503 | LLM 服务不可用 |
| 5002 | 503 | 向量检索服务不可用 |
| 5003 | 503 | 数据库连接失败 |
| 5004 | 503 | DASHSCOPE_API_KEY 未配置 |
| 9999 | 500 | 系统内部错误 |

---

## 7. 部署架构

### 7.1 单机部署（开发 / 测试环境）

```
┌──────────────────────────────────┐
│         单台 Linux 服务器         │
│                                  │
│  Nginx  :80/:443                 │
│  FastAPI :8000 (uvicorn)         │
│  MySQL   :3306                   │
│  Redis   :6379                   │
│  Milvus  :19530 (Docker)         │
└──────────────────────────────────┘
```

**Docker Compose 服务编排**:

```yaml
# docker-compose.yml (精简示意)
version: "3.9"
services:
  milvus:
    image: milvusdb/milvus:v2.4.0
    ports: ["19530:19530"]
    volumes: ["./data/milvus:/var/lib/milvus"]

  mysql:
    image: mysql:8.0
    environment:
      MYSQL_DATABASE: subjects_kg
      MYSQL_USER: edu_rag
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}  # 从 .env 文件读取
    ports: ["3306:3306"]
    volumes: ["./data/mysql:/var/lib/mysql"]

  redis:
    image: redis:7.0-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    ports: ["6379:6379"]
    volumes: ["./data/redis:/data"]

  app:
    build: .
    env_file: .env
    ports: ["8000:8000"]
    depends_on: [milvus, mysql, redis]
    volumes: ["./logs:/app/logs"]
```

### 7.2 生产部署建议

| 组件 | 建议方案 | 原因 |
|------|----------|------|
| 应用层 | 2+ 实例 + Nginx upstream 负载均衡 | 单点故障消除 |
| MySQL | 主从复制 (1主1从) | 读写分离，数据冗余 |
| Redis | Redis Sentinel 或 Cluster | 高可用保障 |
| Milvus | 分布式模式 (QueryNode × 2) | 向量检索性能 |
| 日志 | ELK Stack 或 Loki+Grafana | 集中式日志管理 |
| 配置 | 配置中心 (Nacos/Apollo) | 动态配置，避免重启 |

### 7.3 日志文件配置

```ini
[logger]
log_file = /app/logs/app.log
# 轮转策略: 每天滚动，保留 30 天，单文件最大 100MB
```

```
/app/logs/
├── app.log           # 当天日志
├── app.log.2026-05-18
├── app.log.2026-05-17
└── ...
```

---

## 8. 性能设计

### 8.1 性能指标（对应 PRD 要求）

| 指标 | PRD 要求 | 设计目标 |
|------|----------|----------|
| 页面首次加载 | < 2s | Nginx Gzip + 静态资源 CDN，目标 < 1.5s |
| 即时问答响应 | < 3s | 向量检索 < 200ms + LLM 推理 < 2.5s |
| 流式问答首 token | — | < 1s（用户感知流畅） |
| 复杂问题响应 | < 5s | 含 RAG 全流程不超过 5s |
| 并发用户数 | — | 支持 100 并发（单机），扩展后 1000+ |

### 8.2 关键优化措施

#### 8.2.1 缓存策略

```
学科列表查询
    └── Redis 缓存 (TTL=1h)，命中率 > 99%

向量检索结果
    └── 相同问题 + 相同学科 → Redis 缓存 (TTL=10min)
    └── Key: md5(question + subject)

健康检查
    └── 组件状态缓存 30s，避免频繁探测
```

#### 8.2.2 连接池配置

```python
# MySQL 连接池
mysql_pool = {
    "pool_size":    10,  # 初始连接数
    "max_overflow": 20,  # 最大额外连接数
    "pool_timeout": 30,  # 等待连接超时秒数
    "pool_recycle": 3600 # 连接复用最长时间（秒）
}

# Redis 连接池
redis_pool = {
    "max_connections": 50,
    "socket_timeout":  5,
    "socket_connect_timeout": 5
}
```

#### 8.2.3 Milvus 检索优化

```python
# 搜索参数
search_params = {
    "metric_type": "IP",
    "params": {"nprobe": 16}  # 扫描的聚类数，精度与性能的平衡点
}
# 开启 Milvus QueryNode 缓存，热点向量驻留内存
```

### 8.3 接口限流

```
基于 Redis 滑动窗口限流:
- 单 IP: 60 次/分钟
- 单 session: 30 次/分钟
- 全局 QPS: 200 次/秒（Nginx limit_req）

超限返回: HTTP 429，错误码 3001
```

---

## 9. 安全设计

### 9.1 敏感配置管理

**禁止** 将以下信息硬编码或提交至 Git:

| 配置项 | 安全做法 |
|--------|----------|
| `DASHSCOPE_API_KEY` | 环境变量 / Docker Secret |
| `MYSQL_PASSWORD` | 环境变量 / Vault |
| `REDIS_PASSWORD` | 环境变量 / Vault |
| `config.ini` 密码字段 | 生产环境替换为占位符，实际值由 CI/CD 注入 |

### 9.2 输入校验

```python
# 所有用户输入在进入业务逻辑前强制校验:
class ChatRequest(BaseModel):
    session_id: str = Field(..., pattern=r'^[0-9a-f-]{36}$')       # UUID 格式
    question:   str = Field(..., min_length=1, max_length=500)       # 长度限制
    subject:    Optional[str] = Field(None, pattern=r'^(ai|java|test|ops|bigdata)$')
```

### 9.3 Prompt 注入防护

```
用户输入在送入 Prompt 前:
1. 过滤控制字符 (\x00-\x1f)
2. 截断超长输入 (> 500 字符)
3. 系统 Prompt 与用户输入严格分离（不允许用户覆盖 system role）
4. 对 LLM 输出做安全过滤，屏蔽个人信息泄露模式
```

### 9.4 传输安全

- 生产环境强制 HTTPS，HTTP 请求 301 重定向至 HTTPS
- CORS 配置白名单，仅允许前端域名跨域访问
- 响应头添加: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`

---

## 10. 监控与日志

### 10.1 日志规范

**结构化日志格式** (JSON):

```json
{
  "timestamp":  "2026-05-19T10:01:02.123+08:00",
  "level":      "INFO",
  "module":     "qa_engine",
  "session_id": "550e8400-...",
  "event":      "rag_retrieval_complete",
  "duration_ms": 187,
  "retrieval_k": 10,
  "candidate_m": 3,
  "subject":    "java"
}
```

**日志级别规范**:

| 级别 | 使用场景 |
|------|----------|
| `DEBUG` | 开发调试，不进入生产 |
| `INFO` | 正常业务流程关键节点（每次问答完成、会话创建） |
| `WARNING` | 降级处理、缓存未命中、重试触发 |
| `ERROR` | 外部服务异常、DB 连接失败、LLM 超时 |
| `CRITICAL` | 系统不可用，需立即人工介入 |

### 10.2 核心监控指标

| 指标名 | 类型 | 说明 | 告警阈值 |
|--------|------|------|----------|
| `qa_request_total` | Counter | 问答请求总数 | — |
| `qa_response_time_p99` | Histogram | 问答响应时间 P99 | > 5s |
| `llm_error_rate` | Gauge | LLM 调用错误率 | > 5% |
| `retrieval_latency_p95` | Histogram | 向量检索延迟 P95 | > 500ms |
| `session_active_count` | Gauge | 当前活跃会话数 | — |
| `redis_memory_usage` | Gauge | Redis 内存使用率 | > 80% |
| `milvus_query_latency` | Histogram | Milvus 查询延迟 | > 200ms |

### 10.3 健康检查端点

```
GET /api/v1/health
    ├── MySQL: 执行 SELECT 1 探测
    ├── Redis: 执行 PING 探测
    ├── Milvus: 调用 list_collections 探测
    └── LLM (DashScope): 发送最小化测试请求探测

全部 UP → HTTP 200，status: "healthy"
任一 DOWN → HTTP 503，status: "degraded"，标注故障组件
```

---

## 11. 风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|----------|
| DashScope API 限流 / 欠费 | 中 | 高 | 指数退避重试 + 监控 API 余额告警 |
| Milvus 内存不足 | 低 | 高 | 监控内存使用率，超 70% 扩容 |
| 向量数据与文本数据不一致 | 低 | 中 | 文档入库事务保障，提供数据一致性检查工具 |
| 用户问题超出知识库范围 | 高 | 低 | 兜底回复 + 引导拨打客服 10086 |
| Redis 会话数据丢失 | 低 | 低 | 会话可重建，仅影响历史记录，不影响核心功能 |
| Prompt 注入攻击 | 中 | 中 | §9.3 防护措施 + 定期安全审计 |

---

---

## 12. 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0.0 | 2026-05-19 | 初始版本：RAG 问答、会话管理、学科过滤、前端页面 |
| v1.1.0 | 2026-05-19 | 新增知识库入库模块（§4.5）：多格式文件解析、父子分块、Embedding 批次入库、HTTP 上传接口（§6.4）；修正 Embedding 维度为 1024；修正 MySQL 表 Schema；前端新增知识库管理页面 |

---

*文档结束 — 如有疑问请联系技术架构组*