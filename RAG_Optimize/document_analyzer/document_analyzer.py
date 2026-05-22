"""
文档预处理与版面分析 —— 中文适配版

改动说明（相对原版）：
1. is_text_extractable：增加全角字符计数，防止中文 PDF 被误判为扫描件
2. get_page_elements：补充 PaddleOCR 扫描件分支，strategy 降级策略
3. _normalize_elements：
   - 标题识别增加中文序号正则（第X章 / 一、 / （一））
   - element_type 新增 "title" 分支，保留层级信息
   - 图片元素补充周围文本（surrounding_text），供 Vision 模型使用
4. 新增 _detect_cn_heading：中文标题层级识别
5. 新增 _build_section_path：维护滚动标题栈，为每个元素记录所属章节路径
6. 新增 _get_surrounding_text：提取图片/表格的前后文本，增强 Vision 理解
"""


"""
1. re
出处: Python标准库（无需安装）
作用: 正则表达式模块
用于中文标题识别（如"第一章"、"一、"等模式匹配）
噪声行过滤（页眉页脚特征识别）
文本内容验证和提取
2. fitz (PyMuPDF)
出处: pip install PyMuPDF
作用: 高性能PDF处理库
打开和读取PDF文件
判断PDF是否可提取文本（is_text_extractable方法）
将PDF页面渲染为图片供OCR使用（扫描件处理）
获取页面信息和文本内容
3. pdfplumber
出处: pip install pdfplumber
作用: PDF内容提取工具
虽然在这个文件中导入了，但实际代码中未直接使用
可能在其他模块中用于表格提取的补充方案
提供精确的字符级位置信息
4. unstructured.partition.pdf
出处: pip install unstructured[local-inference]
作用: 智能文档解析库
核心版面分析功能（partition_pdf函数）
自动识别文档元素类型：文本、表格、图片、标题等
支持两种策略：
hi_res: 高分辨率模式，适用于可提取文本的PDF
ocr_only: OCR模式，适用于扫描件
推断表格结构和提取图片
5. dataclasses (dataclass, field)
出处: Python标准库（Python 3.7+）
作用: 数据类装饰器
@dataclass: 简化数据类定义，自动生成__init__等方法
field: 定义字段默认值和工厂函数
用于定义DocumentElement数据结构，存储文档元素信息
6. typing (Literal, Optional)
出处: Python标准库
作用: 类型提示支持
Literal: 限定字符串字面量类型（如element_type只能是"text"/"table"/"image"/"title"）
Optional: 标注可能为None的类型（如bbox: Optional[tuple]）
提高代码可读性和IDE类型检查支持
7. hashlib
出处: Python标准库
作用: 哈希算法库
虽然在这个文件中导入了，但实际代码中未使用
可能用于生成文档指纹或内容哈希（在其他模块中）
8. logging
出处: Python标准库
作用: Python日志框架
记录处理过程中的重要事件和异常
日志级别包括：
INFO: PDF策略切换信息
WARNING: 解析失败降级警告
ERROR: 严重错误（如PaddleOCR未安装）
便于调试和生产环境监控
"""
import re
import fitz          # PyMuPDF
import pdfplumber
from unstructured.partition.pdf import partition_pdf
from dataclasses import dataclass, field
from typing import Literal, Optional
import hashlib
import logging

logger = logging.getLogger(__name__)

# ─── 中文标题识别正则（按层级排列）────────────────────────────────────────────
_HEADING_PATTERNS: list[tuple[int, re.Pattern]] = [
    # 层级1：第X章 / 第X篇 / 第X部分
    (1, re.compile(r'^第\s*[一二三四五六七八九十百千\d]+\s*[章篇部分]\s*.{1,30}$')),
    # 层级2：第X节 / 第X条
    (2, re.compile(r'^第\s*[一二三四五六七八九十百千\d]+\s*[节条款]\s*.{1,30}$')),
    # 层级2：一、二、三、（中文序号 + 顿号）
    (2, re.compile(r'^[一二三四五六七八九十]+[、．.]\s*.{1,30}$')),
    # 层级2：1. 2. 3.（阿拉伯数字 + 点）
    (2, re.compile(r'^\d+[．.、]\s*.{1,30}$')),
    # 层级3：（一）（二）/ (1)(2)
    (3, re.compile(r'^[（(][一二三四五六七八九十\d]+[）)]\s*.{1,30}$')),
    # 层级3：1.1 / 1.2.3（多级编号）
    (3, re.compile(r'^\d+(\.\d+){1,3}\s*.{1,30}$')),
]


@dataclass
class DocumentElement:
    """结构化文档元素，新增 section_path / level / surrounding_text 字段"""
    element_type: Literal["text", "table", "image", "title"]
    content: str                    # 文本内容 / 表格 HTML / 图片描述（空）
    raw_data: any                   # 表格 HTML str 或图片 base64 str
    page_num: int
    bbox: Optional[tuple]           # (x0, y0, x1, y1)
    metadata: dict = field(default_factory=dict)
    # ── 新增字段 ──────────────────────────────────────────────────────────────
    section_path: list[str] = field(default_factory=list)   # ["第一章 总则", "一、定义"]
    level: int = 0                  # 标题层级（0=正文，1/2/3=各级标题）
    surrounding_text: str = ""      # 图片 / 表格 周围文本，供 Vision 模型参考


class PDFAnalyzer:
    """
    PDF 文档分析器（中文适配版）

    主要职责：
    1. 判断是否为扫描件（中文字符感知）
    2. 调用 unstructured 进行版面解析
    3. 规范化元素列表，重建中文章节层级
    4. 扫描件自动降级到 PaddleOCR
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.doc = fitz.open(filepath)

    # ─── 1. 可提取性判断 ──────────────────────────────────────────────────────

    def is_text_extractable(self, threshold: int = 30) -> bool:
        """
        判断是否为可提取文本的 PDF（非扫描件）

        中文适配改动：
        - 原版 threshold=50 对中文 PDF 偏严（中文字符密度低于英文）
        - 调整为 30，并同时统计全角字符，防止误判
        - 单页超过 20 个有效字符即认为该页可提取
        """
        # 可提取页面
        extractable_pages = 0
        total_pages = len(self.doc)

        for page in self.doc:
            text = page.get_text()
            # 有效字符 = 非空白字符（含中文）
            effective_chars = len(re.sub(r'\s', '', text))
            if effective_chars >= 20:
                extractable_pages += 1

        # 超过 threshold% 的页面可提取，则认为整体可提取
        ratio = extractable_pages / total_pages if total_pages > 0 else 0
        return ratio >= (threshold / 100)

    # ─── 2. 版面解析主入口 ────────────────────────────────────────────────────

    def get_page_elements(self) -> list[DocumentElement]:
        """
        版面解析主入口

        策略：
        - 可提取文本 → unstructured hi_res（含表格/图片推断）
        - 扫描件      → unstructured ocr_only（内部调用 Tesseract）
                        或降级到 PaddleOCR（中文更准确，见 _ocr_fallback）
        """
        if self.is_text_extractable():
            strategy = "hi_res"
        else:
            logger.info(f"[{self.filepath}] 疑似扫描件，切换 OCR 策略")
            strategy = "ocr_only"

        try:
            raw_elements = partition_pdf(
                filename=self.filepath,
                strategy=strategy,
                infer_table_structure=True,    # 推断表格结构
                extract_images_in_pdf=True,    # 提取图片块
                extract_image_block_types=["Image", "Table"],
                languages=["chi_sim", "eng"],  # 简体中文 + 英文 OCR
            )
        except Exception as e:
            logger.warning(f"unstructured 解析失败，降级到 PaddleOCR: {e}")
            return self._ocr_fallback()

        return self._normalize_elements(raw_elements)

    # ─── 3. 元素规范化（核心改动）────────────────────────────────────────────

    def _normalize_elements(self, raw_elements) -> list[DocumentElement]:
        """
        将 unstructured 原始元素列表转换为 DocumentElement 列表

        中文适配改动：
        - 标题元素：识别中文序号标题，记录 level 和 section_path
        - 文本元素：过滤噪声（纯符号行、页眉页脚特征行）
        - 图片/表格：附加 surrounding_text，供 Vision 模型理解上下文
        """
        result: list[DocumentElement] = []
        # 滚动标题栈：[(level, title_text), ...]
        section_stack: list[tuple[int, str]] = []
        # 用于构建 surrounding_text 的文本缓冲（最近 3 个文本元素）
        recent_texts: list[str] = []

        for el in raw_elements:
            elem_type_name = type(el).__name__.lower()
            page_num = self._safe_page_num(el)
            content = (el.text or "").strip()

            # ── 表格元素 ───────────────────────────────────────────────────────
            if "table" in elem_type_name:
                html = getattr(el.metadata, 'text_as_html', '') or ''
                surrounding = self._build_surrounding_text(recent_texts)
                result.append(DocumentElement(
                    element_type="table",
                    content=content,
                    raw_data=html,
                    page_num=page_num,
                    bbox=self._safe_bbox(el),
                    metadata={
                        "html": html,
                        "category": "table",
                    },
                    section_path=[t for _, t in section_stack],
                    surrounding_text=surrounding,
                ))
                continue

            # ── 图片元素 ───────────────────────────────────────────────────────
            if "image" in elem_type_name:
                img_b64 = getattr(el.metadata, 'image_base64', None) or ''
                surrounding = self._build_surrounding_text(recent_texts)
                result.append(DocumentElement(
                    element_type="image",
                    content="",          # 后续由 Vision 模型填充
                    raw_data=img_b64,
                    page_num=page_num,
                    bbox=self._safe_bbox(el),
                    metadata={"category": "image"},
                    section_path=[t for _, t in section_stack],
                    surrounding_text=surrounding,
                ))
                continue

            # ── 文本 / 标题元素 ────────────────────────────────────────────────
            if not content:
                continue
            if self._is_noise_line(content):
                continue

            # 检测是否为中文标题
            level = self._detect_cn_heading(content, elem_type_name)

            if level > 0:
                # 更新标题栈
                section_stack = self._update_section_stack(section_stack, level, content)
                result.append(DocumentElement(
                    element_type="title",
                    content=content,
                    raw_data=None,
                    page_num=page_num,
                    bbox=self._safe_bbox(el),
                    metadata={"category": "title", "level": level},
                    section_path=[t for _, t in section_stack],
                    level=level,
                ))
            else:
                result.append(DocumentElement(
                    element_type="text",
                    content=content,
                    raw_data=None,
                    page_num=page_num,
                    bbox=None,
                    metadata={"category": elem_type_name},
                    section_path=[t for _, t in section_stack],
                ))

            # 维护最近文本缓冲（用于 surrounding_text）
            if content:
                recent_texts.append(content)
                if len(recent_texts) > 3:
                    recent_texts.pop(0)

        return result

    # ─── 4. 中文标题识别 ──────────────────────────────────────────────────────

    def _detect_cn_heading(self, text: str, elem_type_name: str) -> int:
        """
        检测文本是否为中文标题，返回层级（0=非标题）

        判断依据（优先级由高到低）：
        1. unstructured 已识别为 Title 类型
        2. 匹配中文标题正则（含序号、章节词）
        3. 行长 ≤ 30 且以句号结尾之外的短句
        """
        text = text.strip()

        # 超长文本不可能是标题
        if len(text) > 60:
            return 0

        # unstructured 已标记为标题类型
        if "title" in elem_type_name or "header" in elem_type_name:
            return self._infer_level_from_pattern(text)

        # 中文标题正则匹配
        level = self._infer_level_from_pattern(text)
        if level > 0:
            return level

        # 短行启发（≤20字，不以句号/问号结尾，纯文字）—— 保守处理，仅返回3级
        if (len(text) <= 20
                and not text.endswith(('。', '！', '？', '；', '…'))
                and re.search(r'[\u4e00-\u9fff]', text)   # 含中文
                and not re.search(r'[,，]', text)):         # 不含逗号（非列举句）
            return 3

        return 0

    def _infer_level_from_pattern(self, text: str) -> int:
        """正则匹配返回标题层级"""
        for level, pattern in _HEADING_PATTERNS:
            if pattern.match(text):
                return level
        return 0

    # ─── 5. 标题栈维护 ────────────────────────────────────────────────────────

    @staticmethod
    def _update_section_stack(
        stack: list[tuple[int, str]],
        new_level: int,
        new_title: str,
    ) -> list[tuple[int, str]]:
        """
        维护滚动标题栈
        规则：遇到新标题时弹出所有同级及下级标题
        例：栈 [(1,"第一章"), (2,"一、定义")] 遇到 level=2 的新标题
            → 弹出 (2,"一、定义")，压入 (2,"二、范围")
        """
        stack = [(lv, t) for lv, t in stack if lv < new_level]
        stack.append((new_level, new_title))
        return stack

    # ─── 6. 辅助工具 ──────────────────────────────────────────────────────────

    @staticmethod
    def _safe_page_num(el) -> int:
        """安全获取页码（unstructured 不同版本字段名可能不同）"""
        try:
            return el.metadata.page_number or 0
        except AttributeError:
            return 0

    @staticmethod
    def _safe_bbox(el) -> Optional[tuple]:
        """安全获取坐标框"""
        try:
            coords = el.metadata.coordinates
            if coords and coords.points:
                pts = coords.points
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                return (min(xs), min(ys), max(xs), max(ys))
        except AttributeError:
            pass
        return None

    @staticmethod
    def _is_noise_line(text: str) -> bool:
        """
        过滤噪声行：页眉页脚、纯符号、极短无意义行

        中文文档常见噪声：
        - "第 X 页 / 共 X 页"
        - "—— X ——" 分割线
        - 单个数字（页码）
        - 全角空白行
        """
        text = text.strip()
        if not text:
            return True
        # 纯数字（页码）
        if re.match(r'^\d+$', text):
            return True
        # 分割线
        if re.match(r'^[-—─═＝]{3,}$', text):
            return True
        # 页眉页脚特征（第X页/共X页）
        if re.search(r'第\s*\d+\s*页|共\s*\d+\s*页|Page\s*\d+', text, re.IGNORECASE):
            return True
        # 极短且不含中文和英文字母（纯标点）
        if len(text) <= 2 and not re.search(r'[\u4e00-\u9fffa-zA-Z]', text):
            return True
        return False

    @staticmethod
    def _build_surrounding_text(recent_texts: list[str], max_chars: int = 200) -> str:
        """拼接最近文本作为 surrounding_text，限制总长度"""
        combined = " ".join(recent_texts)
        return combined[-max_chars:] if len(combined) > max_chars else combined

    # ─── 7. PaddleOCR 降级分支 ────────────────────────────────────────────────

    def _ocr_fallback(self) -> list[DocumentElement]:
        """
        当 unstructured 解析失败时，逐页用 PaddleOCR 提取文本

        依赖：pip install paddleocr paddlepaddle
        """
        try:
            from paddleocr import PaddleOCR
            import numpy as np

            ocr_engine = PaddleOCR(
                use_angle_cls=True,
                lang="ch",
                show_log=False,
                use_gpu=False,   # 无 GPU 时设 False
            )
        except ImportError:
            logger.error("PaddleOCR 未安装，扫描件解析失败。请 pip install paddleocr")
            return []

        result: list[DocumentElement] = []
        for page_idx, page in enumerate(self.doc, start=1):
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")

            try:
                ocr_result = ocr_engine.ocr(img_bytes, cls=True)
                lines = []
                for block in (ocr_result or []):
                    if block:
                        # 按 y 坐标排序保证阅读顺序
                        for item in sorted(block, key=lambda x: x[0][0][1]):
                            text, conf = item[1]
                            if conf >= 0.6 and text.strip():
                                lines.append(text.strip())

                full_text = "\n".join(lines)
                if full_text.strip():
                    result.append(DocumentElement(
                        element_type="text",
                        content=full_text,
                        raw_data=None,
                        page_num=page_idx,
                        bbox=None,
                        metadata={"category": "ocr", "source": "paddleocr"},
                    ))
            except Exception as e:
                logger.warning(f"第 {page_idx} 页 OCR 失败: {e}")

        return result
