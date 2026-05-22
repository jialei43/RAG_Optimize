import asyncio
import logging
from python_a2a.mcp import MCPClient

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s -%(lineno)d - %(message)s')
logger = logging.getLogger(__name__)

async def test_mcp_tools():
    # 连接到服务端，端口 8000
    client = MCPClient("http://localhost:8010")
    try:
        # 步骤 1：获取可用工具列表
        tools = await client.get_tools()
        logger.info("可用工具列表：")
        for tool in tools:
            print(tool)
            logger.info(f"- {tool.get('name', '未知')}: {tool.get('description', '无描述')}")

        # 步骤 2：调用查询高频问题工具
        result_qhf = await client.call_tool("query_high_frequency_question")
        logger.info(f"高频问题查询结果：{result_qhf}")

        # 步骤 3：调用查询天气工具
        result_weather = await client.call_tool("get_weather")
        logger.info(f"天气查询结果：{result_weather}")

    except Exception as e:
        logger.error(f"MCP 客户端出错：{str(e)}", exc_info=True)
    finally:
        await client.close()

async def main():
    await test_mcp_tools()


if __name__ == "__main__":
    asyncio.run(main())