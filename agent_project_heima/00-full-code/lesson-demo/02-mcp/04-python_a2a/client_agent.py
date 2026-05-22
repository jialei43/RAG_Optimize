import asyncio
import logging
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from python_a2a.mcp import MCPClient

# 把python_a2a定义的工具转换成langchain的tool
from python_a2a.langchain import to_langchain_tool

from agent_learn.config import Config

"""
需求：实现基于Python A2A协议的MCP智能代理客户端，集成大语言模型和远程工具
思路步骤：
1. 创建大语言模型实例，配置API参数
2. 创建MCP客户端实例，连接到指定服务器
3. 获取服务器提供的可用工具列表
4. 将MCP工具转换为LangChain兼容的工具格式
5. 构建工具调用代理和执行器
6. 实现交互式聊天循环，处理用户查询
7. 使用异步方式运行客户端程序
8. 确保资源正确释放
"""

conf = Config()

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s -%(lineno) - %(message)s')
logger = logging.getLogger(__name__)

# 1. 创建大语言模型实例，配置API参数
# 创建模型
llm = ChatOpenAI(base_url=conf.base_url,
                 api_key=conf.api_key,
                 model=conf.model_name,
                 temperature=0.1)

async def test_mcp_tools():
    # 连接到服务端，端口 8000
    # 2. 创建MCP客户端实例，连接到指定服务器
    client = MCPClient("http://localhost:8010")
    try:
        # 步骤 1：获取可用工具列表
        # 3. 获取服务器提供的可用工具列表
        tools = await client.get_tools()
        logger.info("可用工具列表：")
        for tool in tools:
            print(tool)
            logger.info(f"- {tool.get('name', '未知')}: {tool.get('description', '无描述')}")

        # TODO 将 python-a2a包下的 MCP tool 转成 LangChain 的工具
        get_weather_tool = to_langchain_tool("http://localhost:8010", "get_weather")
        query_high_frequency_question = to_langchain_tool("http://localhost:8010", "query_high_frequency_question")
        tools=[get_weather_tool, query_high_frequency_question]

        # 创建prompt模板
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", "你是一个乐于助人的助手，能够调用工具回答用户问题。工具不需要传参。"),
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
    except Exception as e:
        logger.error(f"MCP 客户端出错：{str(e)}", exc_info=True)
    finally:
        await client.close()

async def main():
    await test_mcp_tools()

if __name__ == "__main__":
    asyncio.run(main())