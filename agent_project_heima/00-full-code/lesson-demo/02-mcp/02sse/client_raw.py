"""
需求：实现基于SSE的MCP客户端，连接服务器并调用远程工具
思路步骤：
1. 配置服务器URL和客户端连接参数
2. 建立SSE连接并创建客户端会话
3. 初始化会话并加载服务器提供的工具列表
4. 调用远程服务器的工具并处理响应
5. 使用异步方式运行客户端程序
"""

import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client
from langchain_mcp_adapters.tools import load_mcp_tools

# 1. 配置服务器URL和客户端连接参数
url = 'http://192.168.23.77:8001/sse'


class SSEMCPClient(object):
    def __init__(self, url):
        self.url = url
        self.session = None

    async def run(self):
        # 2. 建立SSE连接并创建客户端会话
        async with sse_client(self.url) as (read, write):
            async with ClientSession(read, write) as session:
                # 3. 初始化会话并加载服务器提供的工具列表
                await session.initialize()
                self.session = session
                tools = await load_mcp_tools(self.session)
                print(tools)

                # 4. 调用远程服务器的工具并处理响应
                result = await session.call_tool("get_weather", arguments={})

                print(result)

# 5. 使用异步方式运行客户端程序
if __name__ == '__main__':
    asyncio.run(SSEMCPClient(url).run())
