"""
需求：实现A2A客户端，向服务器发送任务请求并接收结果
思路步骤：
1. 创建A2A客户端实例，连接到指定服务器
2. 发送任务请求到服务器
3. 接收并打印服务器返回的结果
4. 使用异步方式运行客户端程序
"""

import asyncio
from python_a2a import A2AClient

async def main():
    ticket_client = A2AClient("http://127.0.0.1:5010")

    #预订火车票
    ticket_query = "预订一张从北京到上海的火车票"
    print(f"[主控客户端日志]预订票务 -> '{ticket_query}'")
    ticket_result = ticket_client.ask(ticket_query)
    print(f"[主控客户端日志] 收到票务预订结果: {ticket_result}")

if __name__ == "__main__":
    asyncio.run(main())