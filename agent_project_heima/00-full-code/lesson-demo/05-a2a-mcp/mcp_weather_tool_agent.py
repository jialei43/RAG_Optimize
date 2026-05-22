"""
需求：实现MCP天气工具代理，提供城市天气查询服务
思路步骤：
1. 创建FastMCP实例，配置工具代理名称
2. 定义天气查询工具函数，接收城市参数并返回天气信息
3. 启动FastAPI应用服务器
4. 监听指定端口提供天气查询服务
"""

import uvicorn
from python_a2a.mcp import FastMCP, create_fastapi_app

# 1. 创建FastMCP实例，配置工具代理名称
mcp = FastMCP(name="WeatherTool")

# 2. 定义天气查询工具函数，接收城市参数并返回天气信息
@mcp.tool(name="get_weather", description="获取城市天气")
def get_weather(city: str) -> str:
    print(f"[MCP 工具 Agent 日志] 收到工具调用，查询城市: {city}")
    if city == "北京":
        return "北京今天阳光明媚，29°C"
    return f"找不到 {city} 的天气"


if __name__ == "__main__":
    app = create_fastapi_app(mcp)
    print("[MCP 工具 Agent] 已启动，在 http://127.0.0.1:6005")
    uvicorn.run(app, host="127.0.0.1", port=6005)