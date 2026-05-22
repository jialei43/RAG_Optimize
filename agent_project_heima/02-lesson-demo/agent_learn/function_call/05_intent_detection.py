"""
追问意图识别的两种改进方案，替代 04 文件中用"？"猜测的做法

方案一：[NEED_INFO] 结构化标记
  原理：在 system prompt 里强制规定输出格式，代码直接检测前缀，零额外调用
  优点：成本最低、响应最快
  缺点：依赖 LLM 严格遵守格式指令，偶尔会忘记加前缀

方案二：with_structured_output 意图分类
  原理：LLM 返回文本后，用第二个 LLM 调用把文本分类为 need_info/final_answer
  优点：识别最准确，不依赖格式约定
  缺点：多一次 LLM 调用（约 50-100ms、少量 token 费用）

注意：finish_reason 无法解决此问题。
  finish_reason="stop"   → 正常文本输出（追问和最终回答都是 stop，无法区分）
  finish_reason="tool_calls" → 模型要调用工具（等同于 response.tool_calls 非空）
"""

import os  # 环境变量
import json  # JSON 格式化
from datetime import datetime, timedelta  # 日期计算
from typing import Optional, Literal  # 类型注解
from dotenv import load_dotenv, find_dotenv  # 自动查找 .env
from pydantic import BaseModel, Field, field_validator  # 参数校验
from langchain_openai import ChatOpenAI  # OpenAI 协议客户端
from langchain_core.tools import StructuredTool  # 结构化工具
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage  # 消息类型

load_dotenv(find_dotenv())  # 加载环境变量


# ── 基础 LLM 实例 ───────────────────────────────────────────────────────────

def make_llm() -> ChatOpenAI:
    """创建 Qwen LLM 实例，集中管理连接参数"""
    return ChatOpenAI(
        model="qwen-plus",  # Qwen Plus，性价比高
        api_key=os.getenv("DASHSCOPE_API_KEY"),  # DashScope Key
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # OpenAI 兼容端点
    )


# ── 工具定义（两个方案共用）──────────────────────────────────────────────────

class FlightSearchInput(BaseModel):
    """机票查询参数 Schema"""
    origin: str = Field(description="出发城市，例如：北京、上海")  # 必填
    destination: str = Field(description="目的城市，例如：上海、广州")  # 必填
    date: str = Field(description="出发日期，格式 YYYY-MM-DD，根据 system prompt 中的日期推算")  # 必填
    passengers: int = Field(default=1, ge=1, le=9, description="乘客人数 1-9，未提及时用用户默认值")  # 选填
    cabin_class: Optional[str] = Field(default="economy", description="舱位：economy/business/first，未提及时用用户偏好")  # 选填

    @field_validator("date")  # 日期格式校验
    @classmethod
    def validate_date(cls, v: str) -> str:
        """校验日期格式，拒绝过去的日期"""
        try:
            parsed = datetime.strptime(v, "%Y-%m-%d")  # 尝试解析
        except ValueError:
            raise ValueError(f"日期格式错误，应为 YYYY-MM-DD，收到: {v}")  # 格式错误
        if parsed.date() < datetime.now().date():  # 日期不能是过去
            raise ValueError(f"日期 {v} 已是过去，请选择今天或未来的日期")
        return v  # 合法则返回


def search_flights_func(origin: str, destination: str, date: str,
                        passengers: int = 1, cabin_class: str = "economy") -> dict:
    """模拟机票查询，真实场景调用携程/去哪儿 API"""
    base_prices = {"economy": 800, "business": 2400, "first": 4000}  # 各舱位基础价
    price = base_prices.get(cabin_class, 800)  # 单人价格
    return {
        "route": f"{origin} → {destination}",  # 航线
        "date": date,  # 日期
        "passengers": passengers,  # 人数
        "cabin_class": cabin_class,  # 舱位
        "price_per_person": f"¥{price}",  # 单人价
        "total_price": f"¥{price * passengers}",  # 总价
        "available_flights": ["CA1234 07:00", "MU5678 12:30", "CZ9012 18:45"],  # 模拟航班
    }


flight_tool = StructuredTool.from_function(
    func=search_flights_func,  # 业务函数
    name="search_flights",  # 工具名
    description="搜索指定路线和日期的机票信息",  # 工具描述
    args_schema=FlightSearchInput,  # Pydantic Schema
)
TOOLS = [flight_tool]  # 工具列表
TOOL_MAP = {t.name: t for t in TOOLS}  # 名称到工具对象的映射


# ── 公共：上下文注入 + 实体预处理 ──────────────────────────────────────────────

CITY_ALIAS_MAP = {"魔都": "上海", "帝都": "北京", "羊城": "广州", "PEK": "北京",
                  "SHA": "上海", "PVG": "上海"}  # 城市别名映射表


def normalize_query(query: str) -> str:
    """实体预处理：城市别名替换为标准名称"""
    for alias, standard in CITY_ALIAS_MAP.items():  # 遍历别名表
        query = query.replace(alias, standard)  # 替换
    return query  # 返回归一化后的文本


MAX_RETRY = 2  # Pydantic 校验失败后最大重试次数


def execute_tool_calls(response, messages: list, llm_with_tools) -> None:
    """执行工具调用，含 Pydantic 校验失败重试（两个方案共用）"""
    for tc in response.tool_calls:  # 处理每个工具调用
        tool_obj = TOOL_MAP.get(tc["name"])  # 查找工具对象
        if not tool_obj:  # 工具不存在
            messages.append(ToolMessage(content=f"工具 {tc['name']} 不存在", tool_call_id=tc["id"]))
            continue

        print(f"\n[工具调用] {tc['name']}({json.dumps(tc['args'], ensure_ascii=False)})")

        retry_count = 0  # 重试计数器
        while retry_count <= MAX_RETRY:  # 最多重试 MAX_RETRY 次
            try:
                result = tool_obj.invoke(tc["args"])  # 触发 Pydantic 校验并执行
                print(f"[工具结果] {json.dumps(result, ensure_ascii=False, indent=2)}")
                messages.append(ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id=tc["id"]))
                break  # 成功，退出重试

            except Exception as e:  # Pydantic 校验失败
                retry_count += 1
                print(f"[校验失败 第{retry_count}次] {e}")
                if retry_count > MAX_RETRY:  # 超出上限，告知 LLM 失败
                    messages.append(ToolMessage(content=f"参数校验失败：{e}", tool_call_id=tc["id"]))
                    break
                # 把错误反馈给 LLM，触发自我修正
                messages.append(ToolMessage(content=f"参数错误：{e}，请修正后重新调用", tool_call_id=tc["id"]))
                messages.append(HumanMessage(content=f"参数有误：{e}，请修正参数后重新调用工具"))
                retry_resp = llm_with_tools.invoke(messages)  # LLM 重新生成参数
                messages.append(retry_resp)  # 记录修正回复
                if retry_resp.tool_calls:  # 取修正后的 tool_call
                    tc = retry_resp.tool_calls[0]
                    print(f"[LLM 自修正] 新参数: {json.dumps(tc['args'], ensure_ascii=False)}")
                else:
                    break  # LLM 放弃调用，退出


# ══════════════════════════════════════════════════════════════════════════════
# 方案一：[NEED_INFO] 结构化标记
# ══════════════════════════════════════════════════════════════════════════════
#
# 核心思路：
#   在 system prompt 里强制约定：追问时必须以 [NEED_INFO] 开头。
#   代码用 startswith("[NEED_INFO]") 检测，比"？"更精确，且不会被正文里的问号误触发。
#
#   原始"？"方案的问题：
#     "找到3个航班，价格是¥800？"  → 误判为追问（最终回答里含问号）
#     "请您补充目的地信息。"        → 误判为最终回答（追问没用问号）
#
#   [NEED_INFO] 方案：
#     "[NEED_INFO] 请问您要飞往哪个城市？" → startswith 检测，精确命中追问
#     "为您找到以下航班..."              → 无前缀，直接判定为最终回答
# ══════════════════════════════════════════════════════════════════════════════

NEED_INFO_PREFIX = "[NEED_INFO]"  # 追问时 LLM 必须使用的前缀标记


def build_system_prompt_v1(user_id: str = "guest") -> str:
    """
    方案一的 system prompt：
    在原有上下文注入基础上，新增【输出格式规定】，要求追问时必须加 [NEED_INFO] 前缀。
    这是让 [NEED_INFO] 检测生效的关键，没有这段指令，LLM 不会主动加前缀。
    """
    now = datetime.now()  # 当前时间
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")  # 明天日期
    weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]  # 中文星期
    profiles = {
        "guest":    {"name": "访客", "default_passengers": 1, "preferred_cabin": "economy"},
        "user_vip": {"name": "张总", "default_passengers": 1, "preferred_cabin": "business"},
    }
    p = profiles.get(user_id, profiles["guest"])  # 读取用户偏好

    return f"""你是一个专业的旅行助手。

【当前时间】今天：{now.strftime("%Y-%m-%d")}（{weekday_cn}），明天：{tomorrow}
【用户信息】姓名：{p['name']}，默认乘客数：{p['default_passengers']}，偏好舱位：{p['preferred_cabin']}
【日期映射】"今天"={now.strftime("%Y-%m-%d")}，"明天"={tomorrow}，"后天"={(now + timedelta(days=2)).strftime("%Y-%m-%d")}

【输出格式规定 - 必须严格遵守】
- 情况A：参数不足，需要向用户追问 → 回复必须以 {NEED_INFO_PREFIX} 开头
  示例：{NEED_INFO_PREFIX} 请问您要飞往哪个城市？
- 情况B：工具调用完毕，给出最终回答 → 直接输出内容，不加任何前缀
  示例：为您查询到以下航班信息...

禁止：缺少必填参数时直接猜测，必须追问用户。"""


def run_agent_v1(question: str, user_id: str = "guest") -> None:
    """
    方案一执行器：用 startswith(NEED_INFO_PREFIX) 识别追问意图
    替换了原来的 "?" in response.content 逻辑
    """
    print(f"\n{'━'*60}")
    print(f"【方案一：结构化标记】用户输入: {question}")

    normalized = normalize_query(question)  # 实体预处理
    if normalized != question:
        print(f"[预处理] 归一化: {normalized}")

    llm = make_llm()  # 创建 LLM 实例
    llm_with_tools = llm.bind_tools(TOOLS)  # 绑定工具
    messages = [
        SystemMessage(content=build_system_prompt_v1(user_id)),  # 含[NEED_INFO]规定的 system prompt
        HumanMessage(content=normalized),  # 归一化后的用户输入
    ]

    for _ in range(10):  # 最多 10 轮（含追问轮）
        response = llm_with_tools.invoke(messages)  # 调用 LLM
        messages.append(response)  # 记录 LLM 回复

        if response.tool_calls:  # LLM 决定调用工具
            execute_tool_calls(response, messages, llm_with_tools)  # 执行工具（含 Pydantic 重试）
            continue  # 工具执行完，继续下一轮让 LLM 生成最终回答

        # ── 核心改进：用 startswith 取代 "?" 检测 ──────────────────────
        content = response.content  # 取 LLM 文本输出
        if content.startswith(NEED_INFO_PREFIX):  # 精确检测追问前缀，不会被正文问号误触发
            question_text = content[len(NEED_INFO_PREFIX):].strip()  # 去掉前缀，取追问正文
            print(f"\n[Agent 追问] {question_text}")
            user_input = input("请补充: ").strip()  # 等待用户补充
            if not user_input:  # 用户未输入
                print("[终止] 用户未提供信息")
                return
            messages.append(HumanMessage(content=normalize_query(user_input)))  # 补充信息归一化后加入对话
        else:
            print(f"\n[最终回答] {content}")  # 无前缀 = 最终回答，直接输出
            return


# ══════════════════════════════════════════════════════════════════════════════
# 方案二：with_structured_output 意图分类
# ══════════════════════════════════════════════════════════════════════════════
#
# 核心思路：
#   当 LLM 返回文本（无 tool_calls）时，用第二个 LLM 调用对这段文本做意图分类。
#   分类模型使用 with_structured_output，输出固定为 IntentResult Pydantic 对象。
#   结果只有两种：need_info（需要追问）或 final_answer（最终回答）。
#
#   为什么不用 finish_reason：
#     finish_reason="stop"      → 包含"追问"和"最终回答"两种情况，无法区分
#     finish_reason="tool_calls"→ 等同于 response.tool_calls 非空，已经在上面处理了
#     finish_reason 对本问题没有额外信息价值
#
#   代价：每次 LLM 返回文本都多一次分类调用（约 50-100ms、少量 token）
#   收益：识别准确率接近 100%，彻底消除问号误判和漏判
# ══════════════════════════════════════════════════════════════════════════════

class IntentResult(BaseModel):
    """意图分类结果，with_structured_output 会强制 LLM 输出这个格式"""
    intent: Literal["need_info", "final_answer"] = Field(  # 只允许这两个值
        description="need_info=还需要用户补充信息，final_answer=可以直接结束对话"
    )
    reason: str = Field(description="判断依据，一句话说明")  # 方便调试，了解 LLM 的判断理由


def classify_intent(text: str) -> IntentResult:
    """
    用独立的 LLM 调用对文本做意图分类，返回 IntentResult。
    使用独立 LLM 实例（不带工具），避免干扰主对话的 tool_calls 流程。
    """
    classifier = make_llm().with_structured_output(IntentResult)  # 绑定结构化输出 Schema
    prompt = f"""判断下面这段 AI 助手的回复属于哪种意图：
- need_info：助手在向用户追问，需要用户补充信息才能继续
- final_answer：助手已经完成任务，给出了最终答案或告知了结果

助手回复：
{text}"""
    return classifier.invoke([HumanMessage(content=prompt)])  # 返回 IntentResult 对象


def build_system_prompt_v2(user_id: str = "guest") -> str:
    """
    方案二的 system prompt：不需要 [NEED_INFO] 格式规定，让 LLM 自然输出。
    意图识别交给独立的 classify_intent() 处理，system prompt 只负责业务逻辑。
    """
    now = datetime.now()  # 当前时间
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")  # 明天
    weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]  # 星期
    profiles = {
        "guest":    {"name": "访客", "default_passengers": 1, "preferred_cabin": "economy"},
        "user_vip": {"name": "张总", "default_passengers": 1, "preferred_cabin": "business"},
    }
    p = profiles.get(user_id, profiles["guest"])  # 用户偏好

    return f"""你是一个专业的旅行助手。

【当前时间】今天：{now.strftime("%Y-%m-%d")}（{weekday_cn}），明天：{tomorrow}
【用户信息】姓名：{p['name']}，默认乘客数：{p['default_passengers']}，偏好舱位：{p['preferred_cabin']}
【日期映射】"今天"={now.strftime("%Y-%m-%d")}，"明天"={tomorrow}，"后天"={(now + timedelta(days=2)).strftime("%Y-%m-%d")}

缺少必填参数时，直接用自然语言向用户追问，不要猜测。"""  # 不需要格式规定，自然输出即可


def run_agent_v2(question: str, user_id: str = "guest") -> None:
    """
    方案二执行器：用 classify_intent() 意图分类取代 "?" 检测
    LLM 自然输出 → 意图分类 → 决定追问还是结束
    """
    print(f"\n{'━'*60}")
    print(f"【方案二：意图分类】用户输入: {question}")

    normalized = normalize_query(question)  # 实体预处理
    if normalized != question:
        print(f"[预处理] 归一化: {normalized}")

    llm = make_llm()  # 主对话 LLM
    llm_with_tools = llm.bind_tools(TOOLS)  # 绑定工具
    messages = [
        SystemMessage(content=build_system_prompt_v2(user_id)),  # 不含格式规定的 system prompt
        HumanMessage(content=normalized),  # 用户输入
    ]

    for _ in range(10):  # 最多 10 轮
        response = llm_with_tools.invoke(messages)  # 调用主 LLM
        messages.append(response)  # 记录回复

        if response.tool_calls:  # LLM 决定调用工具
            execute_tool_calls(response, messages, llm_with_tools)  # 执行工具
            continue  # 继续下一轮

        # ── 核心改进：用独立 LLM 分类意图，彻底取代 "?" 猜测 ──────────
        content = response.content  # 取文本输出
        intent_result = classify_intent(content)  # 调用意图分类器，返回 IntentResult
        print(f"[意图分类] intent={intent_result.intent}，原因：{intent_result.reason}")  # 调试信息

        if intent_result.intent == "need_info":  # 分类结果：需要追问
            print(f"\n[Agent 追问] {content}")
            user_input = input("请补充: ").strip()  # 等待用户输入
            if not user_input:  # 未输入则退出
                print("[终止] 用户未提供信息")
                return
            messages.append(HumanMessage(content=normalize_query(user_input)))  # 加入对话
        else:  # 分类结果：final_answer
            print(f"\n[最终回答] {content}")  # 直接输出最终回答
            return


# ══════════════════════════════════════════════════════════════════════════════
# 演示
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "█" * 60)
    print("【方案一演示：结构化标记，零额外调用】")
    print("█" * 60)
    run_agent_v1("帮我定明天从北京出发的机票")  # 缺目的地，触发 [NEED_INFO] 追问

    print("\n" + "█" * 60)
    print("【方案二演示：意图分类，彻底精准识别】")
    print("█" * 60)
    run_agent_v2("帮我定明天从北京出发的机票")  # 缺目的地，触发意图分类追问