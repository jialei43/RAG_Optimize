from mcp.server.fastmcp import FastMCP

# 1. 构建Server对象
mcp = FastMCP("sdg", log_level="INFO")

# 2. 定义工具
# mcp: Server对象
# mcp.tool, 在server中注册当前这个工具
@mcp.tool(
    # 类比function-call的方法名
    name="query_high_frequency_question",
    # 类比function-call的方法描述
    description="从知识库中检索常见问题解答（FAQ）,返回包含问题和答案的结构化JSON数据。",
)
# 需要提供异步的方法
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


if __name__ == "__main__":
    # transport: 通信协议 stdio/sse/streamable-http
    mcp.run(transport="stdio")
