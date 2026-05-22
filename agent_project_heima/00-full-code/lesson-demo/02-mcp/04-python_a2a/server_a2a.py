import logging
import uvicorn
from python_a2a.mcp import FastMCP
from python_a2a.mcp import create_fastapi_app

# 配置日志，方便调试
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s -%(lineno)d - %(message)s')
logger = logging.getLogger(__name__)

# 创建 MCP 服务器实例
# TODO 如果是fastmcp包，这里需要直接定义host和port，但是使用python-a2a这里只定义服务器的基本信息
mcp = FastMCP(
    name="MyMCPTools",
    description="提供高频问题和天气查询工具",
    version="1.0.0"
)

# 定义工具 1：查询高频问题
# TODO 定义工具，写法和使用fastmcp一致
@mcp.tool(
    name="query_high_frequency_question",
    description="获取知识库中的高频问答，返回 JSON 数据",
)
async def query_high_frequency_question(**kwargs) -> str:

    # {"question_id": 1, "question_text": "恐龙怎么灭绝", "answer_text": "小行星撞击", ...}
    """
    query_high_frequency_question 不需要任何传参
    查询高频问题并返回答案
    返回示例：[{"question_id": 1, "question_text": "恐龙怎么灭绝", "answer_text": "小行星撞击", ...}]
    """
    try:
        logger.info(f"调用查询高频问题的工具，参数为：{kwargs}")
        return '{"status": "success", "data": [{"question_id": 1, "question_text": "恐龙是怎么灭绝的？", "answer_text": "可能是小行星撞击", "category": "历史", "frequency_score": 0.9}]}'
    except Exception as e:
        logger.error(f"查询高频问题出错: {str(e)}")
        raise

# 定义工具 2：查询天气
@mcp.tool(
    name="get_weather",
    description="查询天气",
)
async def get_weather(**kwargs) -> str:
    """
    get_weather 不需要任何传参
    查询天气并返回结果
    返回示例：{"status": "success", "data": "北京的天气是多云"}
    """
    try:
        logger.info(f"调用查询天气的工具，参数为{kwargs}")
        return '{"status": "success", "data": "北京的天气是多云"}'
    except Exception as e:
        logger.error(f"查询天气出错: {str(e)}")
        raise

# 启动服务器
# TODO 启动服务器， 这里需要使用create_fastapi_app(mcp服务器对象)，启动fastapi程序
# 我们可以再用uvicorn包一层，让服务的性能更强
def start_server():
    logger.info("=== MCP 服务器信息 ===")
    logger.info(f"名称: {mcp.name}")
    logger.info(f"描述: {mcp.description}")

    port = 8010
    app = create_fastapi_app(mcp)
    logger.info(f"启动 MCP 服务器于 http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    start_server()