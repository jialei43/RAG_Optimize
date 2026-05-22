from mcp.server.fastmcp import FastMCP


# 1. 创建server服务，指定host和port
mcp = FastMCP(name='server', port=8001, host='192.168.23.77')

# 2. 定义工具，注册工具
@mcp.tool(
    name="query_high_frequency_question",
    description="从知识库中检索常见问题解答（FAQ）,返回包含问题和答案的结构化JSON数据。",
)
async def query_high_frequency_question() -> str:
    """
    高频问题查询
    """
    try:
        print("调用查询高频问题的tool成功！！")
        return "高频问题是: 恐龙是怎么灭绝的？"
    except Exception as e:
        print(f"Unexpected error in question retrieval: {str(e)}")
        raise

@mcp.tool(
    name="get_weather",
    description="查询天气"
)
async def get_weather() -> str:
    """
    查询天气的tools
    """
    try:
        print("调用查询天气的tools")
        return "北京的天气是多云"
    except Exception as e:
        print(f"Unexpected error in question retrieval: {str(e)}")
        raise


# 3. 启动server, transport = streamable-http
if __name__ == '__main__':
    mcp.run(transport="streamable-http")