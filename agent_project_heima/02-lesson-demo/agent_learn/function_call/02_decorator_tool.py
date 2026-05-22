"""
模式二：@tool 装饰器模式
用 Python 函数 + docstring 定义工具，LangChain 自动解析类型注解生成 Schema。
适合：快速开发，代码最简洁，函数即工具。
"""

import os  # 环境变量读取
from typing import Optional  # Optional 表示参数可以为 None
from dotenv import load_dotenv, find_dotenv  # 自动向上查找 .env
from langchain_openai import ChatOpenAI  # Qwen 通过 OpenAI 协议接入
from langchain_core.tools import tool  # @tool 装饰器
from langchain_core.messages import HumanMessage, ToolMessage  # 消息类型

load_dotenv(find_dotenv())  # 加载环境变量


# ── 初始化 Qwen 模型 ────────────────────────────────────────────────────────

llm = ChatOpenAI(
    model="qwen-plus",  # 使用 qwen-plus，性价比高
    api_key=os.getenv("DASHSCOPE_API_KEY"),  # DashScope Key
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # OpenAI 兼容端点
)


# ── @tool 装饰器定义工具 ──────────────────────────────────────────────────────
# 规则：
#   1. 函数名      → 工具名
#   2. docstring   → 工具描述（模型靠这个决定调用时机）
#   3. 类型注解    → 自动生成 JSON Schema（int/str/float/bool/Optional 都支持）
#   4. 函数体      → 真实执行逻辑


@tool
def get_weather(city: str, unit: Optional[str] = "celsius") -> dict:
    """获取指定城市的当前天气信息。

    Args:
        city: 城市名称，例如：北京、上海、广州
        unit: 温度单位，celsius 表示摄氏度，fahrenheit 表示华氏度，默认 celsius
    """
    mock_data = {  # 模拟数据，替换成真实 API 调用即可
        "北京": {"temp": 28, "desc": "晴", "wind": "东南风3级"},
        "上海": {"temp": 32, "desc": "多云", "wind": "南风2级"},
        "广州": {"temp": 35, "desc": "雷阵雨", "wind": "西南风4级"},
        "深圳": {"temp": 33, "desc": "阴", "wind": "东风2级"},
    }
    data = mock_data.get(city, {"temp": 0, "desc": "暂无数据", "wind": "无"})  # 城市不存在时用默认值
    return {**data, "city": city, "unit": unit}  # 返回完整天气信息


@tool
def calculate(expression: str) -> dict:
    """执行数学计算，支持加减乘除、括号、幂运算。

    Args:
        expression: 合法的数学表达式，例如：2 + 3 * 4，(100 + 50) / 5，2 ** 10
    """
    try:
        # 限制 eval 只能用数学运算，禁止内置函数调用（安全措施）
        result = eval(expression, {"__builtins__": {}}, {})  # type: ignore
        return {"result": result, "expression": expression}  # 返回计算结果和原始表达式
    except Exception as e:
        return {"error": str(e), "expression": expression}  # 表达式非法时返回错误信息


@tool
def translate_text(text: str, target_language: str = "English") -> dict:
    """将文本翻译成目标语言。

    Args:
        text: 需要翻译的原始文本
        target_language: 目标语言，例如：English、日本語、한국어、法语
    """
    # 这里模拟翻译，真实场景接入翻译 API（百度/腾讯/DeepL 等）
    mock_translations = {  # 简单的模拟翻译表
        ("你好", "English"): "Hello",
        ("今天天气很好", "English"): "The weather is great today",
        ("人工智能", "English"): "Artificial Intelligence",
    }
    translated = mock_translations.get((text, target_language), f"[{target_language}] {text}")  # 没找到时原样返回
    return {"original": text, "translated": translated, "target_language": target_language}


# ── 查看装饰器自动生成的 Schema ──────────────────────────────────────────────

def inspect_tool_schema() -> None:
    """打印 @tool 自动生成的 JSON Schema，方便理解装饰器做了什么"""
    print("\n【@tool 自动生成的 Schema 示例】")
    print(f"工具名: {get_weather.name}")  # 自动用函数名作为工具名
    print(f"描述:   {get_weather.description}")  # 自动用 docstring 第一行作为描述
    print(f"Schema: {get_weather.args_schema.model_json_schema()}")  # 自动从类型注解生成


# ── 工具列表和调度器 ──────────────────────────────────────────────────────────

tools = [get_weather, calculate, translate_text]  # 所有工具放到列表里
llm_with_tools = llm.bind_tools(tools)  # 绑定工具列表到模型
TOOL_MAP = {t.name: t for t in tools}  # 建立名称到工具对象的映射，方便调度


# ── 通用 Agent 执行器（支持多轮、多工具）──────────────────────────────────────

def run_agent(question: str, max_rounds: int = 5) -> None:
    """
    执行完整的 Agent 对话流程，支持连续多次工具调用。
    max_rounds: 最大工具调用轮次，防止无限循环
    """
    print(f"\n{'='*50}")
    print(f"用户提问: {question}")
    print("=" * 50)

    messages = [HumanMessage(content=question)]  # 初始化消息历史
    round_count = 0  # 记录工具调用轮次

    while round_count < max_rounds:  # 循环直到模型不再调用工具，或达到最大轮次
        response = llm_with_tools.invoke(messages)  # 调用模型
        messages.append(response)  # 把模型回复加入历史

        if not response.tool_calls:  # 没有工具调用，说明模型已给出最终答案
            print(f"\n最终回复: {response.content}")
            return

        round_count += 1  # 每轮工具调用计数加一
        print(f"\n[第{round_count}轮工具调用]")

        for tc in response.tool_calls:  # 处理本轮所有工具调用（可能同时调用多个）
            tool_obj = TOOL_MAP.get(tc["name"])  # 找到对应的工具对象
            if not tool_obj:
                result = {"error": f"工具 {tc['name']} 未注册"}  # 工具不存在的安全处理
            else:
                result = tool_obj.invoke(tc["args"])  # 调用 LangChain tool 对象的 invoke 方法

            print(f"  {tc['name']}({tc['args']}) => {result}")

            messages.append(  # 把工具结果加入消息历史
                ToolMessage(content=str(result), tool_call_id=tc["id"])
            )

    print("[达到最大轮次，终止]")  # 防止无限循环的兜底提示


# ── 运行演示 ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    inspect_tool_schema()  # 先看看自动生成的 Schema 长什么样

    print("\n\n【演示一：单工具调用】")
    run_agent("帮我计算 (100 + 50) * 2 / 5 的结果")  # 只需要计算工具

    print("\n\n【演示二：多工具同时调用】")
    run_agent("北京天气怎么样？同时帮我计算 2 的 10 次方")  # 模型可能同时调两个工具

    print("\n\n【演示三：翻译工具】")
    run_agent("把「人工智能改变世界」翻译成英文")  # 使用翻译工具
