from mcp.server.fastmcp import FastMCP

ip = "192.168.23.77"
# 1. 构建Server对象
# host = 192.168.23.77 , 这个本机IP，按理说使用localhost是可以访问到同一个机器的
# 但是, host = 192.168.23.77的含义是，只允许通过192.168.23.77访问到本机的才提供服务。
mcp = FastMCP("sdg", log_level="INFO", host=ip, port=8001)


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
    print("正在启动MCP SSE服务器...")
    print(f"SSE端点: http://{ip}:8001/sse")
    print("按 Ctrl+C 停止服务器")

    try:
        # 运行SSE服务器
        mcp.run(transport="sse")
    except KeyboardInterrupt:
        print("\n服务器已停止")
    except Exception as e:
        print(f"服务器启动失败: {e}")
