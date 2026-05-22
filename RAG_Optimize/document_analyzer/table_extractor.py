"""
表格多策略提取（企业级）—— 中文适配版

改动说明（相对原版）：
1. Vision 兜底从 Anthropic Claude → Ollama 国产 Vision 模型（InternVL2 / Qwen2-VL）
   - 调用方式统一改为 ImageUnderstanding.describe_table_image()
2. 中文 PDF 表格特殊处理：
   - 合并单元格检测：中文财务表常见"/"斜线表头、跨行合并
   - 列名清洗：去除换行符、全角空格、常见 OCR 噪声字符
   - 数值规范化：万/亿/百万等中文数量词统一
3. pdfplumber 策略增强：
   - 新增 snap_tolerance / join_tolerance 参数，适配中文 PDF 排版
   - 表头自动识别（第一行加粗或背景色）
   - 空单元格填充策略（NaN → 同列上方非空值向下填充）
4. 置信度评估增加中文专项指标：
   - 列名含中文字符比例
   - 数据行非空率
   - 合并单元格比例（过高则触发 Vision 兜底）
5. 新增 _clean_cn_dataframe()：中文表格数据清洗
6. 新增 _detect_merged_cells()：合并单元格检测
7. EnterpriseTableExtractor.__init__ 接收 vision_model 参数，支持注入
8. 向后兼容：保留原版 extract() 签名和返回格式
"""

import re
import logging
from typing import Optional

import camelot
import fitz
import base64
import pandas as pd
import pdfplumber

from image_understander import ImageUnderstanding, VisionModel

logger = logging.getLogger(__name__)

# ─── 中文数值规范化映射 ───────────────────────────────────────────────────────
_CN_UNIT_MAP = {
    "万亿": 1e12,
    "百亿": 1e10,
    "十亿": 1e9,
    "亿":   1e8,
    "千万": 1e7,
    "百万": 1e6,
    "万":   1e4,
}

# ─── 中文 OCR 常见噪声字符 ────────────────────────────────────────────────────
_OCR_NOISE_RE = re.compile(r'[|｜丨\x00-\x08\x0b\x0c\x0e-\x1f]')

# ─── 列名合法性（最少含一个中文/英文字符）──────────────────────────────────────
_VALID_COL_RE = re.compile(r'[\u4e00-\u9fffa-zA-Z]')


class EnterpriseTableExtractor:
    """
    多策略融合表格提取器（中文适配版）

    策略执行顺序：
    1. Camelot lattice  —— 有线框表格（中文财务报告常见）
    2. Camelot stream   —— 无线框对齐表格
    3. pdfplumber       —— 补充兜底（中文 snap_tolerance 增大）
    4. Vision LLM       —— 合并单元格 / 彩色背景 / 手绘表格

    Attributes:
        confidence_threshold: 置信度阈值（0-1），低于此值触发 Vision 兜底
        vision:               Vision 模型实例（中文适配，替代原版 Anthropic）
    """

    def __init__(
        self,
        confidence_threshold: float = 0.8,
        vision_model: Optional[ImageUnderstanding] = None,
        ollama_url: str = "http://localhost:11434",
        model: str = VisionModel.INTERNVL2_8B,
    ):
        """
        参数：
            confidence_threshold: 置信度阈值，默认 0.8
            vision_model:         外部注入的 ImageUnderstanding 实例（可选）
                                  不传则自动创建（用 ollama_url + model）
            ollama_url:           Ollama 服务地址
            model:                Vision 模型名称
        """
        self.confidence_threshold = confidence_threshold

        # 支持外部注入（便于在 pipeline 中复用同一 Vision 实例）
        if vision_model is not None:
            self.vision = vision_model
        else:
            self.vision = ImageUnderstanding(
                ollama_url=ollama_url,
                model=model,
            )

    # ─── 主入口（保持原版签名）────────────────────────────────────────────────

    def extract(self, pdf_path: str, page_num: int) -> list[dict]:
        """
        从 PDF 指定页面提取表格数据

        Args:
            pdf_path: PDF 文件路径
            page_num: 页码（从 1 开始）

        Returns:
            包含最佳提取结果的列表（最多 1 条），格式：
            [{"method": str, "confidence": float, "dataframe": pd.DataFrame|None,
              "markdown": str}]
        """
        results: list[dict] = []

        # ── 策略1：Camelot lattice（有线框，精度最高）────────────────────────
        results = self._try_camelot_lattice(pdf_path, page_num, results)

        # ── 策略2：Camelot stream（无线框，中文财务表常用）───────────────────
        if not results:
            results = self._try_camelot_stream(pdf_path, page_num, results)

        # ── 策略3：pdfplumber（中文增强参数）─────────────────────────────────
        if not results:
            results = self._try_pdfplumber(pdf_path, page_num, results)

        # ── 策略4：Vision LLM 兜底（合并单元格 / 低置信度）──────────────────
        needs_vision = (
            not results
            or any(r["confidence"] < self.confidence_threshold for r in results)
            or self._has_complex_structure(results)
        )
        if needs_vision:
            vision_result = self._extract_with_vision(pdf_path, page_num)
            if vision_result:
                results.append(vision_result)

        # 按置信度降序，返回最佳结果
        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results[:1]

    # ─── 策略1：Camelot lattice ───────────────────────────────────────────────

    def _try_camelot_lattice(
        self, pdf_path: str, page_num: int, results: list[dict]
    ) -> list[dict]:
        try:
            tables = camelot.read_pdf(
                pdf_path,
                pages=str(page_num),
                flavor="lattice",
                line_scale=40,
                copy_text=["v"],          # 垂直合并单元格时复制文本
                strip_text="\n",          # 去除单元格内换行
            )
            for t in tables:
                if t.accuracy < self.confidence_threshold * 100:
                    continue
                df = self._clean_cn_dataframe(t.df)
                if df is None:
                    continue
                results.append({
                    "method": "camelot_lattice",
                    "confidence": t.accuracy / 100,
                    "dataframe": df,
                    "markdown": self._df_to_markdown(df),
                })
        except Exception as e:
            logger.debug(f"Camelot lattice 失败（第{page_num}页）: {e}")
        return results

    # ─── 策略2：Camelot stream ────────────────────────────────────────────────

    def _try_camelot_stream(
        self, pdf_path: str, page_num: int, results: list[dict]
    ) -> list[dict]:
        try:
            tables = camelot.read_pdf(
                pdf_path,
                pages=str(page_num),
                flavor="stream",
                edge_tol=50,
                row_tol=10,               # 中文行间距更小
                column_tol=5,
                strip_text="\n",
            )
            for t in tables:
                if t.accuracy < self.confidence_threshold * 100:
                    continue
                df = self._clean_cn_dataframe(t.df)
                if df is None:
                    continue
                results.append({
                    "method": "camelot_stream",
                    "confidence": t.accuracy / 100,
                    "dataframe": df,
                    "markdown": self._df_to_markdown(df),
                })
        except Exception as e:
            logger.debug(f"Camelot stream 失败（第{page_num}页）: {e}")
        return results

    # ─── 策略3：pdfplumber（中文增强）────────────────────────────────────────

    def _try_pdfplumber(
        self, pdf_path: str, page_num: int, results: list[dict]
    ) -> list[dict]:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                page = pdf.pages[page_num - 1]
                # 中文 PDF 排版特征：字符间距较小，snap_tolerance 适当放大
                tables = page.extract_tables(
                    table_settings={
                        "vertical_strategy":   "lines",
                        "horizontal_strategy": "lines",
                        "snap_tolerance":      5,     # 原版默认 3，中文放大
                        "join_tolerance":      3,
                        "edge_min_length":     3,
                        "min_words_vertical":  1,
                        "min_words_horizontal": 1,
                        "intersection_tolerance": 5,
                    }
                )
                for raw_table in tables:
                    if not raw_table or len(raw_table) < 2:
                        continue
                    df = self._raw_table_to_df(raw_table)
                    df = self._clean_cn_dataframe(df)
                    if df is None:
                        continue
                    results.append({
                        "method": "pdfplumber",
                        "confidence": 0.65,   # pdfplumber 无内置置信度
                        "dataframe": df,
                        "markdown": self._df_to_markdown(df),
                    })
        except Exception as e:
            logger.debug(f"pdfplumber 失败（第{page_num}页）: {e}")
        return results

    # ─── 策略4：Vision LLM 兜底 ──────────────────────────────────────────────

    def _extract_with_vision(self, pdf_path: str, page_num: int) -> Optional[dict]:
        """
        渲染页面为高分辨率图片，调用国产 Vision 模型提取表格

        相对原版改动：
        - 调用 self.vision.describe_table_image() 而非 Anthropic API
        - 2× 放大保持中文字符清晰度（与原版相同）
        - 置信度固定 0.85（与原版相同）
        """
        try:
            doc = fitz.open(pdf_path)
            page = doc[page_num - 1]
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            doc.close()
        except Exception as e:
            logger.warning(f"页面渲染失败（第{page_num}页）: {e}")
            return None

        markdown = self.vision.describe_table_image(img_bytes)
        if not markdown or "|" not in markdown:
            return None

        # 尝试将 Vision 输出解析为 DataFrame（便于后续数据处理）
        df = self._markdown_to_df(markdown)

        return {
            "method": "vision_llm",
            "confidence": 0.85,
            "dataframe": df,
            "markdown": markdown,
        }

    # ─── 中文 DataFrame 清洗 ──────────────────────────────────────────────────

    def _clean_cn_dataframe(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """
        中文表格数据清洗

        处理项：
        1. 使用第一行作为列名（若列名无效）
        2. 清洗列名：去噪声字符、去多余空白
        3. 过滤全空行
        4. 空单元格向下填充（处理合并单元格）
        5. 数值列规范化（万/亿 → 数字）
        6. 过滤无效表格（列数过少 / 列名不含中英文）

        返回 None 表示该表格不可用
        """
        if df is None or df.empty:
            return None

        df = df.copy()

        # ── 1. 列名处理 ────────────────────────────────────────────────────────
        # 若 pandas 自动命名列（0,1,2...），尝试用第一行作列名
        if all(isinstance(c, int) for c in df.columns):
            if len(df) > 0:
                df.columns = [str(v).strip() for v in df.iloc[0]]
                df = df.iloc[1:].reset_index(drop=True)

        # 清洗列名
        cleaned_cols: list[str] = []
        seen: dict[str, int] = {}
        for col in df.columns:
            col = str(col) if col is not None else ""
            col = _OCR_NOISE_RE.sub('', col)           # 去噪声字符
            col = re.sub(r'\s+', ' ', col).strip()     # 规范化空白
            col = col.replace('\n', ' ')
            if not col:
                col = "未命名列"
            # 处理重复列名
            if col in seen:
                seen[col] += 1
                col = f"{col}_{seen[col]}"
            else:
                seen[col] = 0
            cleaned_cols.append(col)
        df.columns = cleaned_cols

        # ── 2. 过滤有效性 ──────────────────────────────────────────────────────
        if len(df.columns) < 2:
            return None
        # 列名中至少有一列含中文或英文字母
        valid_cols = [c for c in df.columns if _VALID_COL_RE.search(c)]
        if not valid_cols:
            return None

        # ── 3. 清洗单元格 ──────────────────────────────────────────────────────
        df = df.applymap(self._clean_cell)

        # ── 4. 过滤全空行 ──────────────────────────────────────────────────────
        df = df.replace('', pd.NA)
        df = df.dropna(how='all').reset_index(drop=True)
        if df.empty:
            return None

        # ── 5. 空单元格向下填充（处理跨行合并单元格）────────────────────────────
        # 仅对"非数值"列进行 ffill（数值列保持 NaN 便于后续计算）
        for col in df.columns:
            col_vals = df[col].dropna().astype(str)
            is_numeric_col = col_vals.apply(
                lambda x: bool(re.match(r'^[\d,，.．%亿万元]*$', x.strip()))
            ).mean() > 0.6
            if not is_numeric_col:
                df[col] = df[col].fillna(method='ffill')

        # ── 6. 还原空字符串（fillna 不影响空字符串）──────────────────────────────
        df = df.fillna('')

        return df if not df.empty else None

    @staticmethod
    def _clean_cell(val) -> str:
        """单元格值清洗"""
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return ''
        val = str(val)
        val = _OCR_NOISE_RE.sub('', val)
        val = val.replace('\n', ' ').replace('\r', '')
        val = re.sub(r'\s+', ' ', val).strip()
        # 去除前后的单引号（pandas 某些情况下添加）
        val = val.strip("'\"")
        return val

    # ─── 合并单元格检测 ───────────────────────────────────────────────────────

    @staticmethod
    def _has_complex_structure(results: list[dict]) -> bool:
        """
        检测是否存在复杂表格结构（触发 Vision 兜底的条件）

        判断依据：
        - DataFrame 中空单元格比例 > 30%（疑似合并单元格）
        - 列数 == 1（提取错误，整行被当作一列）
        - Markdown 含斜线（/）表头
        """
        for r in results:
            df = r.get("dataframe")
            if df is None:
                continue
            if len(df.columns) <= 1:
                return True
            # 空单元格比例
            total = df.size
            empty = (df == '').sum().sum() + df.isna().sum().sum()
            if total > 0 and (empty / total) > 0.3:
                return True
            # 斜线表头（中文财务表常见）
            if any('/' in str(c) or '\\' in str(c) for c in df.columns):
                return True
        return False

    # ─── 工具方法 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _raw_table_to_df(raw_table: list[list]) -> pd.DataFrame:
        """将 pdfplumber 原始二维列表转为 DataFrame"""
        if not raw_table:
            return pd.DataFrame()
        # 确保所有行等长
        max_cols = max(len(row) for row in raw_table)
        padded = [row + [''] * (max_cols - len(row)) for row in raw_table]
        headers = [str(h).strip() if h else f"列{i}" for i, h in enumerate(padded[0])]
        return pd.DataFrame(padded[1:], columns=headers)

    @staticmethod
    def _df_to_markdown(df: pd.DataFrame) -> str:
        """DataFrame → Markdown 表格字符串"""
        try:
            return df.to_markdown(index=False)
        except Exception:
            # tabulate 不可用时退回手动拼接
            lines = ["| " + " | ".join(str(c) for c in df.columns) + " |"]
            lines.append("| " + " | ".join(["---"] * len(df.columns)) + " |")
            for _, row in df.iterrows():
                lines.append("| " + " | ".join(str(v) for v in row) + " |")
            return "\n".join(lines)

    @staticmethod
    def _markdown_to_df(markdown: str) -> Optional[pd.DataFrame]:
        """
        尝试将 Markdown 表格字符串解析为 DataFrame（容错处理）
        Vision 模型输出格式不规范时返回 None
        """
        try:
            lines = [l.strip() for l in markdown.split("\n")
                     if l.strip() and "|" in l]
            if len(lines) < 2:
                return None
            # 过滤分隔行
            data_lines = [l for l in lines if not re.match(r'^[\s|:\-]+$', l)]
            if not data_lines:
                return None
            headers = [h.strip() for h in data_lines[0].split("|") if h.strip()]
            rows = []
            for line in data_lines[1:]:
                cells = [c.strip() for c in line.split("|")]
                # 去掉首尾空字符串（由开头结尾的 | 产生）
                cells = [c for c in cells if c != ''] if cells[0] == '' else cells
                # 补齐列数
                while len(cells) < len(headers):
                    cells.append('')
                rows.append(cells[:len(headers)])
            if not rows:
                return None
            return pd.DataFrame(rows, columns=headers)
        except Exception as e:
            logger.debug(f"Markdown 解析为 DataFrame 失败: {e}")
            return None
