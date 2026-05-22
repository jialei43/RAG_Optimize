import asyncio
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

"""
需求：实现基于STDIO的MCP原始客户端，连接服务器并调用远程工具
思路步骤：
1. 配置MCP服务器脚本路径和启动参数
2. 建立STDIO连接并创建客户端会话
3. 初始化会话并加载服务器提供的工具列表
4. 调用远程服务器的工具并处理响应
5. 使用异步方式运行客户端程序
"""

# 1. 配置MCP服务器脚本路径和启动参数
# 配置mcp服务器脚本路径
server_script = r"server_stdio.py"

# 配置mcp服务器启动参数
server_params = StdioServerParameters(
    command="python" if server_script.endswith(".py") else "node",
    args=[server_script],
)

# 定义mcp客户端
class MCPClient(object):

    def __init__(self, server_params):
        self.server_params = server_params
        self.session = None

    # 主要的异步函数run_agent
    async def run(self):
        # 2. 建立STDIO连接并创建客户端会话
        # 启动 MCP server，并通过标准输入输出建立异步连接。
        # stdio_client: 基于stdio传输方式，构建MCPClient对象
        # server_params: 构建client的参数，主要读取里面的server的脚本路径。用于定位进程，获取进程的stdio
        async with stdio_client(server_params) as (read, write):
            # 使用读写通道创建 MCP 会话。
            async with ClientSession(read, write) as session:
                # await的目的是为了在异步的方法中，实现等待
                # 3. 初始化会话并加载服务器提供的工具列表
                # TODO 这里需要注意，为了满足在load_mcp_tools的时候可以获取到服务端的信息
                # 必须要等到session初始化完毕以后，才能继续往下执行
                #  async def initialize(self) -> types.InitializeResult:
                await session.initialize()
                self.session = session
                # 从 session 自动获取 MCP server 提供的工具列表。
                tools = await load_mcp_tools(session)
                print(f"tools-->{tools}")
                # 4. 调用远程服务器的工具并处理响应

                # 调用 MCP server 的 get_weather 工具
                response = await session.call_tool("get_weather", arguments={})
                print(f"response-->{response}")

        return


if __name__ == '__main__':
    # 5. 使用异步方式运行客户端程序
    # asyncio.run: 阻塞并等待执行异步方法，直到结果返回
    # 如果没有asyncio.run，因为MCPClient(server_params).run()是异步方法。
    # 在执行的时候，启动一个协程在后台运行。 运行的过程中，main函数就退出了，所以这个方法永远不会返回结果
    asyncio.run(MCPClient(server_params).run())

    # asyncio.run和await的区别：
    # asyncio.run: 在普通方法（同步方法）等待异步方法执行完毕再继续往下执行
    # await: 在异步方法中等待异步方法执行完毕
