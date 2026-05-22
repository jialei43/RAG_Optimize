# models/chinese_models.py
"""
统一国产开源模型接口，支持热切换
Embedding: BGE-M3（FlagEmbedding，支持稠密+稀疏双路）
Reranker:  BGE-Reranker-v2-m3
Vision:    InternVL2-8B 或 Qwen2-VL-7B（本地 Ollama 部署）
OCR:       PaddleOCR 3.x（中英文混排）
"""
from FlagEmbedding import BGEM3FlagModel, FlagReranker
from paddleocr import PaddleOCR
import requests, base64, numpy as np
from dataclasses import dataclass
from typing import Optional

# ─── Embedding（稠密 + 稀疏双路，BGE-M3 一模型两用）────────────────────────
class BGEEmbedder:
    """
    BGE-M3 同时输出 dense(1024d) 和 sparse(词级权重)
    适合中英文混合企业文档
    """
    def __init__(self, model_path: str = "BAAI/bge-m3", device: str = "cuda"):
        self.model = BGEM3FlagModel(
            model_path,
            use_fp16=True,      # 半精度推理，显存减半
            device=device,
        )

    def encode(
        self,
        texts: list[str],
        batch_size: int = 32,
        return_sparse: bool = True,
    ) -> dict:
        """
        返回:
          dense:  np.ndarray [N, 1024]
          sparse: list[dict] 每个文本的词→权重字典（BM25-like）
        """
        output = self.model.encode(
            texts,
            batch_size=batch_size,
            max_length=512,
            return_dense=True,
            return_sparse=return_sparse,
            return_colbert_vecs=False,
        )
        return {
            "dense": output["dense_vecs"],                  # np.ndarray
            "sparse": output.get("lexical_weights", []),    # list[dict]
        }

    def encode_query(self, query: str) -> dict:
        """查询端编码（前缀不同，提升召回率）"""
        return self.encode([f"Represent this sentence for searching: {query}"])


# ─── Reranker（BGE-Reranker-v2-m3，中英文精排）──────────────────────────────
class BGEReranker:
    """
    BGE-Reranker-v2-m3: 交叉编码器，输入(query, passage)对打分
    显著优于双编码器的精排效果，尤其中文场景
    """
    def __init__(
        self,
        model_path: str = "BAAI/bge-reranker-v2-m3",
        device: str = "cuda",
    ):
        self.model = FlagReranker(
            model_path,
            use_fp16=True,
            device=device,
        )

    def rerank(
        self,
        query: str,
        passages: list[str],
        top_k: int = 5,
        batch_size: int = 16,
    ) -> list[dict]:
        """
        返回按相关性降序排列的 [{idx, score, text}]
        """
        if not passages:
            return []

        pairs = [[query, p] for p in passages]
        scores = self.model.compute_score(
            pairs,
            batch_size=batch_size,
            normalize=True,     # sigmoid 归一化到 [0,1]
        )

        ranked = sorted(
            [{"idx": i, "score": float(s), "text": passages[i]}
             for i, s in enumerate(scores)],
            key=lambda x: x["score"],
            reverse=True,
        )
        return ranked[:top_k]


# ─── Vision 模型（InternVL2 via Ollama 本地部署）────────────────────────────
class InternVLVision:
    """
    调用本地 Ollama 部署的 InternVL2-8B 或 Qwen2-VL-7B
    ollama pull internvl2:8b
    ollama pull qwen2-vl:7b
    """
    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = "internvl2:8b",
    ):
        self.base_url = ollama_url
        self.model = model

    def describe_image(
        self,
        img_bytes: bytes,
        prompt: str = "请详细描述这张图片的内容，如果包含图表请提取关键数据。",
        surrounding_text: str = "",
    ) -> str:
        img_b64 = base64.b64encode(img_bytes).decode()
        if surrounding_text:
            prompt = f"上下文：{surrounding_text[:200]}\n\n{prompt}"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 512},
        }
        resp = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["response"].strip()

    def describe_table_image(self, img_bytes: bytes) -> str:
        """专用于表格理解的提示词"""
        return self.describe_image(
            img_bytes,
            prompt=(
                "请将图中的表格转换为 Markdown 格式输出。"
                "保持所有列名和数据，合并单元格用最左上角的值表示。"
                "只输出 Markdown 表格，不要其他文字。"
            ),
        )


# ─── OCR（PaddleOCR 3.x，中英文混排优化）────────────────────────────────────
class PaddleOCREngine:
    """
           初始化PaddleOCR引擎

           Args:
               lang: OCR识别语言类型，默认为"ch"（简体中文）。
                     可选值："ch"（中文）、"en"（英文）、"korean"、"japan"等
               use_gpu: 是否使用GPU加速推理，默认为True。
                       无GPU时自动降级到CPU模式

           Note:
               PaddleOCR关键配置参数说明：
               - use_angle_cls: 启用文字方向分类器，自动纠正旋转文本（0°/90°/180°/270°）
               - det_db_box_thresh: 文本检测置信度阈值（0-1），设为0.3降低漏检率，适合模糊文档
               - rec_batch_num: 识别阶段批处理大小，设为8平衡显存占用和推理速度
               - show_log: 关闭详细日志输出，避免控制台噪音
    """
    def __init__(self, lang: str = "ch", use_gpu: bool = True):
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang=lang,
            use_gpu=use_gpu,
            show_log=False,
            det_db_box_thresh=0.3,
            rec_batch_num=8,
        )

    def extract_text(self, img_path_or_bytes) -> str:
        """提取图片中的文字，保留布局顺序

        提取图片中的文字内容

        对OCR识别结果进行后处理，按从上到下的阅读顺序拼接文本行。

        x = [
            [[10, 20], [100, 20], [100, 50], [10, 50]],  # 这是 x[0]：4个顶点坐标信息 (Box)
            ("人工智能", 0.99)                            # 这是 x[1]：内容信息 (Text, Score)
        ]

        Args:
            img_path_or_bytes: 图片文件路径（str）或图片二进制数据（bytes）

        Returns:
            提取的文本内容，每行之间用换行符分隔

        Note:
            OCR返回的数据结构说明：
            - result是一个列表，每个元素代表一页的识别结果
            - 每页包含多个识别项，每项格式为：[坐标框, (文本, 置信度)]
            - 坐标框格式：[[x0,y0], [x1,y1], [x2,y2], [x3,y3]]
            - 通过y坐标（x[0][0][1]）排序确保文本按从上到下的顺序排列
        """
        result = self.ocr.ocr(img_path_or_bytes, cls=True)
        lines = []
        for page in result:
            if page:
                # 按 y 坐标排序保证阅读顺序
                # 获取图片左上角坐标的y坐标（高度），进行排序
                sorted_lines = sorted(page, key=lambda x: x[0][0][1])
                lines.extend([item[1][0] for item in sorted_lines])
        return "\n".join(lines)