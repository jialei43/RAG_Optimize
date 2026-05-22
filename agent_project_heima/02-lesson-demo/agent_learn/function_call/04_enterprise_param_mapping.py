"""
企业级参数映射完整方案
解决问题：用户自然语言输入（"今天北京到上海"）如何可靠地映射到函数参数

四层防护：
  Layer 1 - 上下文注入：把日期/用户信息注入 system prompt，解决"今天"/"明天"
  Layer 2 - 实体预处理：城市别名、机场代码归一化，在进 LLM 之前做
  Layer 3 - Slot Filling：缺参数时 LLM 主动追问，而不是猜
  Layer 4 - 校验重试：Pydantic 校验失败后把错误反馈给 LLM，让它自我修正
"""

import os  # 环境变量
import json  # JSON 格式化输出
from datetime import datetime, timedelta  # 日期计算
from typing import Optional, Literal  # 可选类型 / 字面量枚举类型
from dotenv import load_dotenv, find_dotenv  # 自动查找 .env
from pydantic import BaseModel, Field, field_validator  # 参数校验
from langchain_openai import ChatOpenAI  # OpenAI 协议客户端
from langchain_core.tools import StructuredTool  # 结构化工具
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage  # 消息类型

load_dotenv(find_dotenv())  # 加载 .env 文件


# ══════════════════════════════════════════════════════════════════════════════
# Layer 1：上下文注入 — 解决"今天"/"明天"/"下周五"等动态时间表达
# ══════════════════════════════════════════════════════════════════════════════

def build_system_prompt(user_id: str = "guest") -> str:
    """
    构建注入动态上下文的 system prompt。
    规则：把一切 LLM 训练时不知道的信息都注入进来，让模型有依据做推理。
    """
    now = datetime.now()  # 获取当前真实时间
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")  # 明天的日期
    today_str = now.strftime("%Y-%m-%d")  # 今天的 ISO 格式日期
    weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]  # 中文星期

    # 模拟从用户数据库读取的个人偏好（真实场景走 DB/Redis）
    user_profile = {
        "guest":     {"name": "访客",   "default_passengers": 1, "preferred_cabin": "economy"},
        "user_vip":  {"name": "张总",   "default_passengers": 1, "preferred_cabin": "business"},
    }
    profile = user_profile.get(user_id, user_profile["guest"])  # 读取用户偏好，找不到用默认值

    return f"""你是一个专业的旅行助手，帮助用户查询机票和天气信息。

【当前时间上下文】
- 今天日期：{today_str}（{weekday_cn}）
- 明天日期：{tomorrow}
- 当前时刻：{now.strftime("%H:%M")}

【当前用户信息】
- 用户ID：{user_id}
- 姓名：{profile['name']}
- 默认乘客数：{profile['default_passengers']}
- 偏好舱位：{profile['preferred_cabin']}

【参数映射规则】
- 用户说"今天" → 日期填 {today_str}
- 用户说"明天" → 日期填 {tomorrow}
- 用户说"后天" → 日期填 {(now + timedelta(days=2)).strftime("%Y-%m-%d")}
- 用户没有指定乘客数 → 使用用户默认乘客数 {profile['default_passengers']}
- 用户没有指定舱位 → 使用用户偏好舱位 {profile['preferred_cabin']}
- 日期格式必须是 YYYY-MM-DD

【输出格式规定 - 必须严格遵守】
- 情况A：必填参数不足，需要追问用户 → 回复必须以 {NEED_INFO_PREFIX} 开头
  示例：{NEED_INFO_PREFIX} 请问您要飞往哪个城市？
- 情况B：工具调用完毕，给出最终回答 → 直接输出内容，不加任何前缀
  示例：为您查询到以下航班信息...

禁止：缺少必填参数时随意猜测，必须以 {NEED_INFO_PREFIX} 开头追问用户。"""


# ══════════════════════════════════════════════════════════════════════════════
# Layer 2：实体预处理 — 在进入 LLM 之前做城市别名/机场代码归一化
# ══════════════════════════════════════════════════════════════════════════════

# 城市别名映射表（企业实际用知识图谱或专有 NER 模型）
CITY_ALIAS_MAP = {
    "魔都": "上海",   # 上海别名
    "帝都": "北京",   # 北京别名
    "羊城": "广州",   # 广州别名
    "蓉城": "成都",   # 成都别名
    "BJ":   "北京",   # 英文缩写
    "SH":   "上海",
    "GZ":   "广州",
    "PEK":  "北京",   # IATA 机场代码
    "SHA":  "上海",
    "PVG":  "上海",   # 浦东机场代码也归一化到城市
    "CAN":  "广州",
}


def normalize_query(query: str) -> str:
    """
    实体预处理：把用户输入的别名/缩写替换成标准城市名。
    真实场景：用专有 NER 模型（如 HanLP）或城市知识库，这里用简单字典演示。
    """
    normalized = query  # 从原始输入开始
    for alias, standard in CITY_ALIAS_MAP.items():  # 遍历别名表
        normalized = normalized.replace(alias, standard)  # 替换别名为标准名
    return normalized  # 返回替换后的查询


# ══════════════════════════════════════════════════════════════════════════════
# Pydantic Schema 定义（这是 Layer 3 Slot Filling 和 Layer 4 校验的基础）
# ══════════════════════════════════════════════════════════════════════════════

class FlightSearchInput(BaseModel):
    """机票查询参数 Schema，description 是 LLM 做参数映射的核心依据"""

    origin: str = Field(
        description="出发城市名称，例如：北京、上海、广州。必须是具体城市，不能是别名"  # 精确描述帮助 LLM 正确填参
    )
    destination: str = Field(
        description="目的地城市名称，例如：上海、深圳、成都。必须是具体城市"
    )
    date: str = Field(
        description="出发日期，格式 YYYY-MM-DD。根据上下文中今天/明天的日期推算，不要用相对表述"  # 提示 LLM 用注入的日期
    )
    passengers: int = Field(
        default=1,
        ge=1,  # 最少 1 人
        le=9,  # 最多 9 人
        description="乘客人数 1-9，用户未提及时使用 system prompt 中的用户默认乘客数"  # 告诉 LLM 找默认值
    )
    cabin_class: Optional[str] = Field(
        default="economy",
        description="舱位：economy（经济舱）、business（商务舱）、first（头等舱）。用户未提及时使用用户偏好舱位"
    )

    @field_validator("date")  # 日期格式校验器
    @classmethod
    def validate_date(cls, v: str) -> str:
        """校验日期格式，并拒绝过去的日期"""
        try:
            parsed = datetime.strptime(v, "%Y-%m-%d")  # 尝试解析日期
        except ValueError:
            raise ValueError(f"日期格式错误，应为 YYYY-MM-DD，收到: {v}")  # 格式错误时报错
        if parsed.date() < datetime.now().date():  # 不能预订过去的航班
            raise ValueError(f"日期 {v} 已是过去，请选择今天或未来的日期")  # 过去日期报错
        return v  # 合法则返回

    @field_validator("cabin_class")  # 舱位枚举校验
    @classmethod
    def validate_cabin(cls, v: Optional[str]) -> Optional[str]:
        """确保舱位值合法"""
        if v is None:
            return v  # None 是允许的（用默认值）
        allowed = {"economy", "business", "first"}  # 合法的舱位集合
        if v not in allowed:
            raise ValueError(f"舱位必须是 {allowed} 之一，收到: {v}")  # 非法舱位报错
        return v  # 合法则返回


# ══════════════════════════════════════════════════════════════════════════════
# 业务逻辑函数（和 Schema 分离）
# ══════════════════════════════════════════════════════════════════════════════

def search_flights_func(
    origin: str,
    destination: str,
    date: str,
    passengers: int = 1,
    cabin_class: str = "economy",
) -> dict:
    """模拟机票搜索，真实场景调用携程/去哪儿 API"""
    base_prices = {"economy": 800, "business": 2400, "first": 4000}  # 舱位基础价格
    price = base_prices.get(cabin_class, 800)  # 获取单人价格
    return {
        "route": f"{origin} → {destination}",  # 航线
        "date": date,  # 日期
        "passengers": passengers,  # 乘客数
        "cabin_class": cabin_class,  # 舱位
        "price_per_person": f"¥{price}",  # 单人价格
        "total_price": f"¥{price * passengers}",  # 总价
        "available_flights": ["CA1234 07:00", "MU5678 12:30", "CZ9012 18:45"],  # 模拟航班
    }


# 注册工具
flight_tool = StructuredTool.from_function(
    func=search_flights_func,  # 业务函数
    name="search_flights",  # 工具名
    description="搜索机票，返回可用航班和价格",  # 工具描述
    args_schema=FlightSearchInput,  # Pydantic Schema 提供参数描述和校验
)

tools = [flight_tool]  # 工具列表（可扩展）


# ══════════════════════════════════════════════════════════════════════════════
# Layer 3 + 4：Slot Filling + 校验重试的 Agent 执行器
# ══════════════════════════════════════════════════════════════════════════════

MAX_RETRY = 2  # Pydantic 校验失败后最多重试次数，防止 LLM 反复填错死循环

# ══════════════════════════════════════════════════════════════════════════════
# 追问意图识别：两种方案替代原来的 "?" 猜测
# ══════════════════════════════════════════════════════════════════════════════

# 方案一：[NEED_INFO] 结构化标记
# LLM 在 system prompt 的约定下，追问时必须以此前缀开头，代码用 startswith 精确检测
# 失效场景：LLM 偶尔忘记加前缀（概率低，实测约 2-5%）
NEED_INFO_PREFIX = "[NEED_INFO]"  # 追问前缀标记，system prompt 里会要求 LLM 遵守


# 方案二：with_structured_output 意图分类
# LLM 返回文本后，用第二个 LLM 调用把文本分类为 need_info / final_answer
# 代价：每次文本回复多一次 LLM 调用（约 50-100ms、少量 token）
# 收益：识别准确率接近 100%，彻底消除误判

class IntentResult(BaseModel):
    """意图分类结果，with_structured_output 强制 LLM 输出此格式"""
    intent: Literal["need_info", "final_answer"] = Field(  # 只允许这两个枚举值
        description="need_info=需要用户补充参数，final_answer=任务完成可以结束"
    )
    reason: str = Field(description="判断依据，一句话说明，方便调试")  # 调试用，了解分类原因


def classify_intent(text: str, llm: ChatOpenAI) -> IntentResult:
    """
    对 LLM 的文本输出做意图分类，返回 IntentResult。
    使用 with_structured_output 绑定 Pydantic Schema，强制输出结构化结果。
    传入 llm 实例复用连接，避免每次新建。
    """
    classifier = llm.with_structured_output(IntentResult)  # 绑定结构化输出 Schema
    prompt = (
        "判断下面这段 AI 助手的回复属于哪种意图：\n"
        "- need_info：助手在向用户追问，需要用户补充信息才能继续\n"
        "- final_answer：助手已完成任务，给出了最终答案或查询结果\n\n"
        f"助手回复：\n{text}"  # 把待分类的文本嵌入 prompt
    )
    return classifier.invoke([HumanMessage(content=prompt)])  # 返回 IntentResult 对象


def run_enterprise_agent(question: str, user_id: str = "guest",
                         intent_mode: str = "prefix") -> None:
    """
    企业级 Agent 执行器，整合四层机制：
      1. system prompt 注入当前日期/用户信息
      2. 实体预处理（城市别名归一化）
      3. Slot Filling（缺参数时追问而不是猜）
      4. Pydantic 校验失败后把错误反馈给 LLM，触发自我修正

    intent_mode 控制 Layer 3 的追问识别方式：
      "prefix"   - 方案一：检测 [NEED_INFO] 前缀，零额外调用，速度快
      "classify" - 方案二：用独立 LLM 做意图分类，准确率更高，多一次调用
    """
    print(f"\n{'='*60}")
    print(f"用户输入: {question}  [intent_mode={intent_mode}]")

    # ── Layer 2：实体预处理 ──────────────────────────────────────
    normalized_question = normalize_query(question)  # 别名归一化
    if normalized_question != question:  # 有替换时打印，方便调试
        print(f"[预处理] 归一化后: {normalized_question}")

    # ── Layer 1：上下文注入 ──────────────────────────────────────
    system_prompt = build_system_prompt(user_id)  # 注入日期、用户偏好
    llm = ChatOpenAI(
        model="qwen-plus",  # Qwen Plus 模型
        api_key=os.getenv("DASHSCOPE_API_KEY"),  # 从环境变量读取 Key
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # DashScope 端点
    )
    llm_with_tools = llm.bind_tools(tools)  # 绑定工具列表

    messages = [
        SystemMessage(content=system_prompt),  # 带上动态 system prompt（含日期/用户信息）
        HumanMessage(content=normalized_question),  # 归一化后的用户输入
    ]

    print("=" * 60)

    # ── 主循环：支持 Slot Filling 多轮追问 ──────────────────────
    for _ in range(10):  # 最多 10 轮（含追问轮次）
        response = llm_with_tools.invoke(messages)  # 调用 LLM
        messages.append(response)  # 记录 LLM 回复

        # ── Layer 3：Slot Filling ────────────────────────────────
        # LLM 没有调用工具 = 两种情况：
        #   a. 缺少必填参数，LLM 在追问用户
        #   b. 工具调用完毕，LLM 在给最终回答
        if not response.tool_calls:
            content = response.content  # 取 LLM 文本输出

            # ── 方案一：[NEED_INFO] 前缀检测 ─────────────────────
            # system prompt 规定：追问时必须以 [NEED_INFO] 开头
            # startswith 精确匹配，不会被正文里的"？"误触发
            if intent_mode == "prefix":
                is_clarification = content.startswith(NEED_INFO_PREFIX)  # 精确检测追问前缀
                question_text = content[len(NEED_INFO_PREFIX):].strip() if is_clarification else content  # 去掉前缀取正文

            # ── 方案二：with_structured_output 意图分类 ──────────
            # 用独立 LLM 把文本分类为 need_info / final_answer
            # 彻底消除误判，代价是多一次 LLM 调用（约 50-100ms）
            else:
                result = classify_intent(content, llm)  # 调用意图分类器
                print(f"[意图分类] intent={result.intent}，原因：{result.reason}")  # 打印分类依据，方便调试
                is_clarification = result.intent == "need_info"  # 分类结果转布尔值
                question_text = content  # 方案二不需要剥前缀，直接用原文

            if is_clarification:  # 追问：等待用户补充信息
                print(f"\n[Agent 追问] {question_text}")
                user_input = input("请补充: ").strip()  # 等待用户输入
                if not user_input:  # 用户未输入
                    print("[终止] 用户未提供信息")
                    return
                messages.append(HumanMessage(content=normalize_query(user_input)))  # 补充信息归一化后加入对话
                continue  # 继续下一轮
            else:  # 最终回答：直接输出并退出
                print(f"\n[最终回答] {content}")
                return

        # ── Layer 4：工具调用 + Pydantic 校验 + 重试 ────────────
        for tc in response.tool_calls:  # 处理每个工具调用
            tool_obj = next((t for t in tools if t.name == tc["name"]), None)  # 找工具对象
            if not tool_obj:
                messages.append(ToolMessage(
                    content=f"错误：工具 {tc['name']} 不存在",  # 工具不存在的错误信息
                    tool_call_id=tc["id"]
                ))
                continue

            print(f"\n[工具调用] {tc['name']}({json.dumps(tc['args'], ensure_ascii=False)})")

            retry_count = 0  # 重试计数器
            while retry_count <= MAX_RETRY:  # 最多重试 MAX_RETRY 次
                try:
                    result = tool_obj.invoke(tc["args"])  # 调用工具（触发 Pydantic 校验）
                    print(f"[工具结果] {json.dumps(result, ensure_ascii=False, indent=2)}")
                    messages.append(ToolMessage(  # 把成功结果加入历史
                        content=json.dumps(result, ensure_ascii=False),
                        tool_call_id=tc["id"]
                    ))
                    break  # 成功，退出重试循环

                except Exception as e:
                    retry_count += 1  # 失败，重试次数加一
                    error_msg = str(e)  # 错误信息
                    print(f"[校验失败 第{retry_count}次] {error_msg}")

                    if retry_count > MAX_RETRY:  # 超出重试上限
                        messages.append(ToolMessage(  # 把最终错误加入历史
                            content=f"参数校验失败，无法执行：{error_msg}",
                            tool_call_id=tc["id"]
                        ))
                        break

                    # ── 把错误反馈给 LLM，让它自我修正 ──────────
                    messages.append(ToolMessage(  # 先把当前 tool_call 对应的错误结果填上
                        content=f"参数错误：{error_msg}，请修正后重新调用工具",
                        tool_call_id=tc["id"]
                    ))
                    # 追加一条系统级提示，明确告诉 LLM 要重试
                    messages.append(HumanMessage(
                        content=f"上面的工具调用参数有误：{error_msg}。请修正参数后重新调用工具。"  # 错误反馈给 LLM
                    ))
                    retry_response = llm_with_tools.invoke(messages)  # LLM 根据错误重新生成参数
                    messages.append(retry_response)  # 记录 LLM 的修正回复

                    if retry_response.tool_calls:  # LLM 重新生成了工具调用
                        tc = retry_response.tool_calls[0]  # 取第一个（通常只有一个）
                        print(f"[LLM 自修正] 新参数: {json.dumps(tc['args'], ensure_ascii=False)}")
                    else:
                        break  # LLM 放弃了工具调用，退出重试


# ══════════════════════════════════════════════════════════════════════════════
# 演示
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # print("\n" + "█" * 60)
    # print("【演示一：'今天' 被正确解析为当前日期，prefix 模式】")
    # print("█" * 60)
    # run_enterprise_agent("帮我定今天北京到上海的机票", user_id="guest", intent_mode="prefix")
    #
    # print("\n" + "█" * 60)
    # print("【演示二：城市别名归一化，VIP 用户默认商务舱，prefix 模式】")
    # print("█" * 60)
    # run_enterprise_agent("明天从帝都到魔都，查一下机票", user_id="user_vip", intent_mode="prefix")

    print("\n" + "█" * 60)
    print("【演示三：缺少目的地，[NEED_INFO] 前缀追问（prefix 模式）】")
    print("█" * 60)
    run_enterprise_agent("帮我定明天去上海的的机票", user_id="guest", intent_mode="prefix")

    print("\n" + "█" * 60)
    print("【演示四：缺少目的地，with_structured_output 意图分类追问（classify 模式）】")
    print("█" * 60)
    run_enterprise_agent("帮我定明天去上海的的机票", user_id="guest", intent_mode="classify")
