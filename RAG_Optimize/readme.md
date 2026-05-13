# RAG项目相关
## 1.项目依赖
```python
# 核心依赖
pip install \
  FlagEmbedding>=1.2.0 \        # BGE-M3 + Reranker
  pymilvus>=2.4.0 \             # Milvus 客户端（含 BM25）
  paddleocr>=3.0.0 paddlepaddle-gpu \  # PaddleOCR
  jieba \                       # 中文分词（BM25）
  unstructured[pdf] pymupdf \   # 版面解析
  camelot-py[cv] pdfplumber \   # 表格提取
  redis prometheus-client \     # 监控+限流
  requests numpy pandas

pip install unstructured[pdf] pymupdf pdfplumber camelot-py[cv] \
    qdrant-client openai anthropic paddleocr \
    pandas tabulate markdown

# 本地部署 Vision 模型（Ollama）
curl https://ollama.ai/install.sh | sh
ollama pull internvl2:8b     # 首选
ollama pull qwen2-vl:7b      # 备选

# 启动 Milvus（Docker Compose）
wget https://raw.githubusercontent.com/milvus-io/milvus/master/deployments/docker/standalone/docker-compose.yml
docker compose up -d

# Prometheus + Grafana 监控栈
docker run -d -p 9090:9090 prom/prometheus
docker run -d -p 3000:3000 grafana/grafana
```