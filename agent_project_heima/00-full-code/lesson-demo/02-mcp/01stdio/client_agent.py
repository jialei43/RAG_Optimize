"""
需求：实现基于STDIO的MCP智能代理客户端，集成大语言模型和远程工具
思路步骤：
1. 创建大语言模型实例，配置API参数
2. 配置MCP服务器脚本路径和启动参数
3. 建立STDIO连接并创建客户端会话
4. 加载服务器提供的工具列表
5. 构建工具调用代理和执行器
6. 实现交互式聊天循环，处理用户查询
7. 使用异步方式运行客户端程序
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "../../.."))
import asyncio
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from agent_learn.config import Config

conf = Config()
# 1. 创建大语言模型实例，配置API参数
# 创建模型
llm = ChatOpenAI(base_url=conf.base_url,
                 api_key=conf.api_key,
                 model=conf.model_name,
                 temperature=0.1)

# 2. 配置MCP服务器脚本路径和启动参数

# 配置mcp服务器脚本路径
server_script = r"server_sse.py"

# 配置mcp服务器启动参数
server_params = StdioServerParameters(
    command="python" if server_script.endswith(".py") else "node",
    args=[server_script],
)

PLACE_HOLDER = ("placeholder", "{agent_scratchpad}")


class MCPClient:

    def __init__(self, server_params):
        self.server_params = server_params
        self.session = None

    async def run(self):
        # 3. 建立STDIO连接并创建客户端会话
        # 3.1 基于stdio的参数构建读写流
        async with stdio_client(self.server_params) as (read, write):
            # 3.2 创建会话连接
            async with ClientSession(read, write) as session:
                await session.initialize()
                self.session = session

                # 4. 加载服务器提供的工具列表
                tools = await load_mcp_tools(session)
                print(f"服务端支持的tools:{tools}")

                # 创建prompt模板
                prompt_template = ChatPromptTemplate.from_messages([
                    ("system", "你是一个乐于助人的助手，能够调用工具回答用户问题。"),
                    ("human", "{input}"),
                    # 系统内置
                    PLACE_HOLDER,
                ])

                # 5. 构建工具调用代理和执行器
                agent = create_tool_calling_agent(llm, tools, prompt_template)

                # 创建代理执行器
                # AgentExecutor(chain): 一种特殊的链
                agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

                # 6. 实现交互式聊天循环，处理用户查询
                # 代理调用
                print("MCP客户端启动，输入'quit'退出")
                while True:
                    # 接收用户查询
                    query = input("\nQuery: ").strip()
                    if query.lower() == "quit":
                        break
                    # 发送用户查询给代理，并打印
                    try:
                        response = await agent_executor.ainvoke({"input": query})
                        print(f"response-->{response}")
                    except Exception:
                        print("解析有问题")

                return



if __name__ == '__main__':
    asyncio.run(MCPClient(server_params).run())