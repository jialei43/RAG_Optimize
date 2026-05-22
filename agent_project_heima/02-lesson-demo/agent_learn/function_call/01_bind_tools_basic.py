"""
模式一：bind_tools 基础模式
手动用 JSON Schema 定义工具，最接近原生 OpenAI function_call 协议。
适合：需要精确控制工具描述格式、或对接非 LangChain 代码时。
"""

import os  # 读取环境变量
from dotenv import load_dotenv, find_dotenv  # 自动向上查找 .env 文件
from langchain_openai import ChatOpenAI  # OpenAI 协议兼容客户端，Qwen 也走这里
from langchain_core.messages import HumanMessage, ToolMessage  # 消息类型

load_dotenv(find_dotenv())  # 加载 .env，find_dotenv() 会向上层目录搜索


# ── 第一步：初始化 Qwen 模型 ──────────────────────────────────────────────────

llm = ChatOpenAI(
    model="qwen-plus",  # Qwen 模型名，可换 qwen-max / qwen-turbo
    api_key=os.getenv("DASHSCOPE_API_KEY"),  # 从环境变量读取 Key
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # DashScope OpenAI 兼容入口
)


# ── 第二步：用 JSON Schema 手动定义工具 ────────────────────────────────────────

tools = [
    {
        "type": "function",  # 固定写法，表示这是一个函数类型工具
        "function": {
            "name": "get_weather",  # 工具名，模型调用时会返回这个名字
            "description": "获取指定城市的当前天气信息",  # 关键！模型靠这句话决定要不要调用
            "parameters": {  # 参数定义，标准 JSON Schema 格式
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",  # 参数类型
                        "description": "城市名称，例如：北京、上海",  # 告诉模型怎么填这个参数
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],  # 限定枚举值，防止模型乱填
                        "description": "温度单位，默认 celsius",
                    },
                },
                "required": ["city"],  # city 必填，unit 选填
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",  # 第二个工具：查股价
            "description": "查询指定股票代码的当前价格",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "股票代码，例如：AAPL、600036",
                    }
                },
                "required": ["symbol"],
            },
        },
    },
]


# ── 第三步：把工具绑定到模型（返回一个新的可调用对象）──────────────────────────

llm_with_tools = llm.bind_tools(tools)  # 绑定后，每次调用都会带上工具定义


# ── 第四步：实现真实的工具函数 ─────────────────────────────────────────────────

def get_weather(city: str, unit: str = "celsius") -> dict:
    """模拟天气 API，真实场景替换成 requests.get(weather_api_url)"""
    mock_data = {  # 假数据，演示用
        "北京": {"temp": 28, "desc": "晴", "humidity": "40%"},
        "上海": {"temp": 32, "desc": "多云", "humidity": "75%"},
        "广州": {"temp": 35, "desc": "雷阵雨", "humidity": "85%"},
    }
    data = mock_data.get(city, {"temp": 0, "desc": "暂无数据", "humidity": "0%"})  # 未知城市返回默认值
    unit_symbol = "°C" if unit == "celsius" else "°F"  # 根据参数选温度符号
    return {**data, "city": city, "unit": unit_symbol}  # 合并城市和单位到结果里


def get_stock_price(symbol: str) -> dict:
    """模拟股价查询"""
    mock_prices = {"AAPL": 189.5, "600036": 38.2, "TSLA": 245.0}  # 假数据
    price = mock_prices.get(symbol.upper(), None)  # 大写统一处理
    if price is None:
        return {"error": f"未找到股票 {symbol}"}  # 找不到时返回错误信息
    return {"symbol": symbol, "price": price, "currency": "USD"}  # 返回价格信息


# 工具名 -> 函数的映射字典，调度器靠这个找到该执行哪个函数
TOOL_MAP = {
    "get_weather": get_weather,
    "get_stock_price": get_stock_price,
}


# ── 第五步：完整的多轮对话调用流程 ────────────────────────────────────────────

def run_with_tools(question: str) -> None:
    """执行一次完整的工具调用流程：用户问题 -> 模型决策 -> 执行工具 -> 最终回答"""
    print(f"\n{'='*50}")
    print(f"用户提问: {question}")
    print("=" * 50)

    messages = [HumanMessage(content=question)]  # 初始消息列表

    # ── 第一轮请求：让模型判断是否需要调用工具 ──
    response = llm_with_tools.invoke(messages)  # 发送请求
    print(f"\n[第一轮] stop_reason: {response.response_metadata.get('finish_reason')}")
    print(f"[第一轮] tool_calls: {response.tool_calls}")  # 模型要调用的工具列表

    if not response.tool_calls:  # 模型认为不需要工具，直接回答
        print(f"\n最终回复: {response.content}")
        return

    messages.append(response)  # 把模型的第一轮回复加入消息历史（包含 tool_calls）

    # ── 执行所有工具调用（一次可能有多个）──
    for tool_call in response.tool_calls:
        tool_name = tool_call["name"]   # 模型想调用的工具名
        tool_args = tool_call["args"]   # 模型传的参数
        tool_id = tool_call["id"]       # 本次调用的唯一 ID，返回结果时要对应上

        func = TOOL_MAP.get(tool_name)  # 从映射表找到真正的函数
        if func:
            result = func(**tool_args)  # 用 ** 解包 dict 作为关键字参数传入
            # result = func.invoke(tool_args)
        else:
            result = {"error": f"工具 {tool_name} 不存在"}  # 安全降级处理

        print(f"\n[工具执行] {tool_name}({tool_args})")
        print(f"[工具结果] {result}")

        # 把工具结果包装成 ToolMessage 加入消息历史
        messages.append(
            ToolMessage(
                content=str(result),  # 内容是函数返回值的字符串形式
                tool_call_id=tool_id,  # 必须和模型返回的 id 对应，否则报错
            )
        )

    # ── 第二轮请求：模型根据工具结果生成最终答案 ──
    final_response = llm_with_tools.invoke(messages)  # 带上完整历史再次请求
    print(f"\n最终回复: {final_response.content}")


# ── 运行演示 ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_with_tools("北京今天天气怎么样？")  # 演示单工具调用
    run_with_tools("上海和广州哪个更热？")  # 演示模型可能调用两次工具
    run_with_tools("苹果公司的股价是多少？")  # 演示第二个工具被调用
