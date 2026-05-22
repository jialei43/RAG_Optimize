import asyncio
from langchain_openai import ChatOpenAI
from mcp import ClientSession
from mcp.client.sse import sse_client
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from agent_learn.config import Config


conf = Config()

# 创建模型
llm = ChatOpenAI(base_url=conf.base_url,
                 api_key=conf.api_key,
                 model=conf.model_name,
                 temperature=0.1)

# MCP server URL for SSE connection
server_url = "http://192.168.23.77:8001/sse"

# 定义mcp客户端
mcp_client = None

# Main async function: connect, load tools, create agent, run chat loop
async def run_agent():
    global mcp_client
    # 启动 MCP server，通过 SSE 建立异步连接。
    async with sse_client(url=server_url) as streams:
    # async with sse_client(url=server_url) as (read, write):
        # 使用读写通道创建 MCP 会话
        # async with ClientSession(read, write)) as session:
        async with ClientSession(*streams) as session:
            await session.initialize()
            # 动态创建一个临时类 MCPClientHolder，把 session 放进去。这样就可以在函数外部通过 mcp_client.session 调用 MCP 工具
            # TODO 临时类，用于临时封装一个对象，获取对象的属性。但是类本身没有任何特殊
            mcp_client = type("MCPClientHolder", (), {"session": session})()

            # 从 session 自动获取 MCP server 提供的工具列表。
            tools = await load_mcp_tools(session)
            # print(f"tools-->{tools}")

            # 创建prompt模板
            prompt_template = ChatPromptTemplate.from_messages([
                ("system", "你是一个乐于助人的助手，能够调用工具回答用户问题。"),
                ("human", "{input}"),
                ("placeholder", "{agent_scratchpad}"),
            ])

            # 构建工具调用代理
            agent = create_tool_calling_agent(llm, tools, prompt_template)

            # 创建代理执行器
            agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

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

if __name__ == "__main__":
    asyncio.run(run_agent())
