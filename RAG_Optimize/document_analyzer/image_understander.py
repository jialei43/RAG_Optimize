"""
图表和图片理解 —— 中文适配版（国产模型）

改动说明（相对原版）：
1. 将 Anthropic Claude 调用替换为 Ollama 本地部署的国产 Vision 模型
   - 默认：InternVL2-8B（上海 AI 实验室，图表理解 SOTA）
   - 备选：Qwen2-VL-7B（阿里通义，文档表格理解强）
   - 接口统一为 Ollama REST API，可热切换模型
2. SYSTEM_PROMPT 补充中文文档常见图表类型（财务图、组织架构、流程图）
3. describe() 方法：
   - 新增 chart_type_hint 参数，让调用方传入图表类型提示
   - 输出结构新增 chart_type / data_points / trend 字段
   - surrounding_text 截断从 300 → 400 字符，中文语境更丰富
4. 新增 describe_table_image()：专用表格截图理解，输出 Markdown
5. 新增 describe_chart_image()：专用图表理解，结构化提取数据点
6. 新增 _call_ollama() / _call_ollama_with_retry()：统一 HTTP 调用 + 重试
7. 新增 OllamaVisionModel 枚举，记录可用模型及其特长
8. 保留原版 describe() 签名，向后兼容
"""

import base64
import logging
import time
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import requests

logger = logging.getLogger(__name__)


# ─── 支持的国产 Vision 模型 ────────────────────────────────────────────────────

class VisionModel(str, Enum):
    """
    Ollama 支持的国产 Vision 模型

    部署命令：
        ollama pull internvl2:8b
        ollama pull qwen2-vl:7b
        ollama pull minicpm-v:8b
    """
    INTERNVL2_8B  = "internvl2:8b"       # 图表理解强，中文优秀
    QWEN2_VL_7B   = "qwen2-vl:7b"        # 文档/表格理解强
    MINICPM_V_8B  = "minicpm-v:8b"       # 轻量，RTX 3090 可跑


# ─── 图像描述结果结构 ─────────────────────────────────────────────────────────

@dataclass
class ImageDescription:
    """Vision 模型输出的结构化描述"""
    description: str                      # 完整描述（用于向量化）
    searchable_text: str                  # 检索用文本（同 description）
    has_data: bool = False                # 是否包含数据（图表、表格）
    chart_type: str = ""                  # 图表类型（柱状图/折线图/饼图/流程图等）
    data_points: list[str] = field(default_factory=list)   # 提取的关键数据点
    trend: str = ""                       # 趋势描述（如"营收逐年增长"）
    raw_markdown: str = ""               # 若为表格图，附带 Markdown


# ─── 主类 ─────────────────────────────────────────────────────────────────────

class ImageUnderstanding:
    """
    图表和图片理解（国产模型版）

    使用本地 Ollama 部署的国产 Vision 模型替代 Anthropic Claude，
    适合数据隐私要求高的企业环境，全量离线推理。
    """

    # 通用图像分析 Prompt（中文企业文档场景）
    SYSTEM_PROMPT = """你是专业的中文企业文档图像分析助手。
分析图像时，请按以下规则处理不同类型：

【数据图表】柱状图/折线图/饼图/散点图：
  - 提取图表标题、X轴/Y轴标签及单位
  - 列出3-5个关键数据点（含具体数值）
  - 总结核心趋势或结论

【表格图片】：
  - 输出完整 Markdown 表格
  - 保留所有列名和数据，合并单元格取左上角值

【流程图/架构图/组织架构】：
  - 描述节点名称和连接关系
  - 说明整体流程或层级结构

【照片/示意图】：
  - 描述主体内容和用途
  - 说明与文档上下文的关联

输出格式：【图像类型】 | 【核心内容描述】 | 【关键数据或结论】"""

    # 专用表格提取 Prompt
    TABLE_EXTRACT_PROMPT = (
        "请将图中的表格转换为 Markdown 格式。\n"
        "要求：\n"
        "1. 保留所有列名和数据，不要省略任何行\n"
        "2. 合并单元格用左上角的值填充\n"
        "3. 数字保持原始格式（含单位）\n"
        "4. 只输出 Markdown 表格，不要任何解释文字\n"
        "5. 如有多个表格，用 --- 分隔"
    )

    # 专用图表数据提取 Prompt
    CHART_EXTRACT_PROMPT = (
        "请分析此图表并按以下格式输出：\n"
        "图表类型：[柱状图/折线图/饼图/散点图/其他]\n"
        "标题：[图表标题，无则填'无']\n"
        "X轴：[标签和单位]\n"
        "Y轴：[标签和单位]\n"
        "关键数据：\n"
        "- [数据点1：具体数值]\n"
        "- [数据点2：具体数值]\n"
        "趋势结论：[一句话总结核心趋势或对比结论]"
    )

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = VisionModel.INTERNVL2_8B,
        timeout: int = 60,
        max_retries: int = 2,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ):
        """
        参数：
            ollama_url:   Ollama 服务地址
            model:        使用的 Vision 模型名称
            timeout:      单次请求超时（秒）
            max_retries:  失败重试次数
            temperature:  采样温度（建议 0.05-0.2，降低幻觉）
            max_tokens:   最大输出 token 数
        """
        self.ollama_url = ollama_url.rstrip("/")
        self.model = str(model)
        self.timeout = timeout
        self.max_retries = max_retries
        self.temperature = temperature
        self.max_tokens = max_tokens

        self._generate_url = f"{self.ollama_url}/api/generate"
        self._check_connection()

    # ─── 原版兼容接口 ──────────────────────────────────────────────────────────

    def describe(
        self,
        img_bytes: bytes,
        surrounding_text: str = "",
        doc_title: str = "",
        chart_type_hint: str = "",   # 新增：调用方传入的图表类型提示
    ) -> dict:
        """
        为图片生成结构化描述，供 RAG 检索使用

        保持与原版相同的返回字段（description / searchable_text / has_data），
        新增 chart_type / data_points / trend / raw_markdown

        参数：
            img_bytes:       图片字节流（PNG/JPEG）
            surrounding_text: 图片周围的文本上下文（最多 400 字符）
            doc_title:       所属文档标题
            chart_type_hint: 图表类型提示（如"财务图表"，留空则自动识别）
        """
        img_b64 = base64.standard_b64encode(img_bytes).decode()

        # 构建上下文提示
        context_parts: list[str] = []
        if doc_title:
            context_parts.append(f"文档标题：{doc_title}")
        if surrounding_text:
            context_parts.append(f"周围文本：{surrounding_text[:400]}")
        if chart_type_hint:
            context_parts.append(f"图表类型提示：{chart_type_hint}")
        context_str = "\n".join(context_parts)

        user_prompt = f"请分析此图像。{context_str}" if context_str else "请分析此图像。"

        raw_text = self._call_ollama_with_retry(
            prompt=user_prompt,
            img_b64=img_b64,
            system=self.SYSTEM_PROMPT,
        )

        result = self._parse_description(raw_text)

        # 向后兼容：保留原版字段格式
        return {
            "description": result.description,
            "searchable_text": result.searchable_text,
            "has_data": result.has_data,
            # 新增字段
            "chart_type": result.chart_type,
            "data_points": result.data_points,
            "trend": result.trend,
            "raw_markdown": result.raw_markdown,
        }

    # ─── 新增：专用表格图片理解 ───────────────────────────────────────────────

    def describe_table_image(
        self,
        img_bytes: bytes,
        surrounding_text: str = "",
    ) -> str:
        """
        专用于表格截图理解，直接输出 Markdown 格式

        适用场景：Camelot / pdfplumber 均无法提取的复杂表格（合并单元格、
        斜线表头、彩色背景表格等），用 Vision 模型兜底

        返回：Markdown 表格字符串，提取失败返回空字符串
        """
        img_b64 = base64.standard_b64encode(img_bytes).decode()
        prompt = self.TABLE_EXTRACT_PROMPT
        if surrounding_text:
            prompt += f"\n\n表格上下文：{surrounding_text[:200]}"

        raw = self._call_ollama_with_retry(
            prompt=prompt,
            img_b64=img_b64,
        )

        # 提取 Markdown 表格部分（容错：模型可能附带说明文字）
        md_match = re.search(r'(\|.+\|[\s\S]*)', raw)
        if md_match:
            return md_match.group(1).strip()
        return raw.strip() if "|" in raw else ""

    # ─── 新增：专用图表数据提取 ───────────────────────────────────────────────

    def describe_chart_image(
        self,
        img_bytes: bytes,
        doc_title: str = "",
    ) -> ImageDescription:
        """
        专用于数据图表理解，结构化提取数据点和趋势

        适用场景：财务报告中的折线图、柱状图、饼图等
        返回：ImageDescription 对象（含 chart_type / data_points / trend）
        """
        img_b64 = base64.standard_b64encode(img_bytes).decode()
        prompt = self.CHART_EXTRACT_PROMPT
        if doc_title:
            prompt += f"\n\n所属文档：{doc_title}"

        raw = self._call_ollama_with_retry(
            prompt=prompt,
            img_b64=img_b64,
        )
        return self._parse_chart_output(raw)

    # ─── Ollama HTTP 调用 ─────────────────────────────────────────────────────

    def _call_ollama_with_retry(
        self,
        prompt: str,
        img_b64: str,
        system: str = "",
    ) -> str:
        """带重试的 Ollama 调用"""
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._call_ollama(prompt, img_b64, system)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    wait = 2 ** attempt  # 指数退避
                    logger.warning(f"Ollama 调用失败（{attempt+1}/{self.max_retries+1}），{wait}s 后重试: {e}")
                    time.sleep(wait)

        logger.error(f"Ollama 调用最终失败: {last_error}")
        return ""

    def _call_ollama(
        self,
        prompt: str,
        img_b64: str,
        system: str = "",
    ) -> str:
        """向 Ollama REST API 发送 Vision 推理请求"""
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
                "top_p": 0.9,
                "repeat_penalty": 1.1,
            },
        }
        if system:
            payload["system"] = system

        resp = requests.post(
            self._generate_url,
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return (data.get("response") or "").strip()

    # ─── 结果解析 ─────────────────────────────────────────────────────────────

    def _parse_description(self, raw: str) -> ImageDescription:
        """
        解析通用描述输出（SYSTEM_PROMPT 格式：【类型】|【内容】|【结论】）
        """
        if not raw:
            return ImageDescription(description="图像解析失败", searchable_text="")

        # 尝试解析结构化格式（含 | 分隔）
        parts = [p.strip() for p in raw.split("|")]
        chart_type = ""
        if parts:
            # 去除【】符号提取图像类型
            chart_type = re.sub(r'[【】\[\]]', '', parts[0]).strip()

        # 判断是否含数据
        data_keywords = ["数据", "图表", "增长", "下降", "趋势", "%", "万", "亿", "元"]
        has_data = any(kw in raw for kw in data_keywords)

        # 若包含 Markdown 表格
        raw_markdown = ""
        if "|" in raw and "---" in raw:
            md_match = re.search(r'(\|.+\|[\s\S]*)', raw)
            if md_match:
                raw_markdown = md_match.group(1).strip()

        return ImageDescription(
            description=raw,
            searchable_text=raw,
            has_data=has_data,
            chart_type=chart_type,
            raw_markdown=raw_markdown,
        )

    @staticmethod
    def _parse_chart_output(raw: str) -> ImageDescription:
        """
        解析 CHART_EXTRACT_PROMPT 的结构化输出

        预期格式：
            图表类型：折线图
            标题：2020-2024年营收趋势
            X轴：年份
            Y轴：营收（亿元）
            关键数据：
            - 2020年：100亿
            趋势结论：营收逐年增长，2024年同比增长25%
        """
        if not raw:
            return ImageDescription(description="图表解析失败", searchable_text="")

        chart_type = ""
        data_points: list[str] = []
        trend = ""

        for line in raw.split("\n"):
            line = line.strip()
            if line.startswith("图表类型："):
                chart_type = line.replace("图表类型：", "").strip()
            elif line.startswith("趋势结论："):
                trend = line.replace("趋势结论：", "").strip()
            elif line.startswith("-") and ("：" in line or ":" in line):
                dp = line.lstrip("-").strip()
                data_points.append(dp)

        has_data = bool(data_points or trend)

        return ImageDescription(
            description=raw,
            searchable_text=raw,
            has_data=has_data,
            chart_type=chart_type,
            data_points=data_points,
            trend=trend,
        )

    # ─── 连接检测 ─────────────────────────────────────────────────────────────

    def _check_connection(self):
        """启动时检测 Ollama 是否可访问"""
        try:
            resp = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            if self.model not in models:
                logger.warning(
                    f"模型 {self.model} 未在 Ollama 中找到。"
                    f"已有模型：{models}。"
                    f"请运行：ollama pull {self.model}"
                )
            else:
                logger.info(f"Ollama 连接正常，使用模型：{self.model}")
        except Exception as e:
            logger.warning(
                f"无法连接 Ollama（{self.ollama_url}）: {e}。"
                f"请确认 Ollama 已启动：ollama serve"
            )
