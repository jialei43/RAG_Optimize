"""
需求：实现A2A客户端，向天气代理服务器发送查询请求
思路步骤：
1. 创建A2A客户端实例，连接到指定的天气代理服务器
2. 构造天气查询请求
3. 发起A2A调用并等待响应结果
4. 输出最终结果
5. 使用异步方式运行客户端程序
"""

import asyncio
from python_a2a import A2AClient

async def main():
    # 创建客户端
    agent_client = A2AClient("http://127.0.0.1:8005")
    print("[主客户端日志] 准备向天气 Agent 发送任务...")

    # 发起 A2A 调用
    query = "请帮我查一下北京的天气"
    result = agent_client.ask(query)
    print(f"[主客户端日志] 收到最终结果: '{result}'")

if __name__ == "__main__":
    # 请确保 mcp_weather_tool_agent.py 和 a2a_weather_agent.py 正在运行...
    asyncio.run(main())