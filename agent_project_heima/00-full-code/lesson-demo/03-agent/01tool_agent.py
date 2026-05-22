"""
需求：实现Agent工具使用模式，让AI能够调用外部工具解决复杂问题
思路步骤：
1. 创建大语言模型实例，配置API参数
2. 定义可调用的工具函数（如乘法运算、天气查询等）
3. 构建提示模板，指导Agent何时及如何调用工具
4. 创建工具调用Agent，使其具备自动判断工具使用的能力
5. 创建Agent执行器，负责协调Agent和工具间的交互
6. 实现通用执行函数，用于运行Agent并展示结果
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent
from agent_learn.config import Config

# 1. 创建大语言模型实例，配置API参数

conf = Config()

# 1.创建模型
llm = ChatOpenAI(base_url=conf.base_url,
                 api_key=conf.api_key,
                 model=conf.model_name,
                 temperature=0.1)


# 2. 定义可调用的工具函数（如乘法运算、天气查询等）

@tool
def multiply(a: int, b: int) -> int:
    """用于计算两个整数的乘积。"""
    print(f"正在执行乘法: {a} * {b}")

    return a * b


@tool
def search_weather(city: str) -> str:
    """用于查询指定城市的实时天气。"""
    print(f"正在查询天气: {city}")
    if "北京" in city:
        return "北京今天是晴天，气温25摄氏度。"
    elif "上海" in city:
        return "上海今天是阴天，有小雨，气温22摄氏度。"
    else:
        return f"抱歉，我没有'{city}'的天气信息。"


# 3. 构建提示模板，指导Agent何时及如何调用工具
tools = [multiply, search_weather]

# 3.定义一个提示模板，用于控制Agent的思考过程和工具调用
tool_use_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "你是一个强大的AI助手，可以访问和使用各种工具来回答问题。请根据用户的问题，决定是否需要调用工具。当需要调用工具时，请使用正确的JSON格式。"),
    ("user", "{input}"),
    ("placeholder", "{agent_scratchpad}")  # 这个占位符用于保存 Agent 的思考过程和工具调用历史
])

# 4. 创建工具调用Agent，使其具备自动判断工具使用的能力
tool_calling_agent = create_tool_calling_agent(llm, tools, tool_use_prompt)

# 5. 创建Agent执行器，负责协调Agent和工具间的交互
tool_use_executor = AgentExecutor(
    agent=tool_calling_agent,
    tools=tools,
    verbose=True  # 开启 verbose 模式，可以打印详细的执行过程
)

# 6. 实现通用执行函数，用于运行Agent并展示结果

# 6.通用的执行函数，用于运行agent并打印结果
def run_agent_and_print(agent_executor, query):
    """一个通用函数，用于运行Agent并打印结果。"""
    print(f"--- 运行Agent，查询: {query} ---")
    response = agent_executor.invoke({"input": query})
    print(f"\n--- Agent响应: ---")
    print(response.get("output", "没有找到输出。"))
    print("-" * 30 + "\n")


if __name__ == "__main__":
    run_agent_and_print(tool_use_executor, "上海今天的天气怎么样？")
    run_agent_and_print(tool_use_executor, "30乘以5等于多少？ 上海天气怎么样")