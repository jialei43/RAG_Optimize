"""
需求：实现A2A天气代理服务器，通过MCP客户端调用下游天气工具
思路步骤：
1. 定义代理卡片，包含代理名信称、描述、URL和技能息
2. 创建自定义A2AServer子类，集成MCP客户端连接下游工具
3. 实现handle_task方法处理传入的天气查询任务
4. 根据任务内容决策是否调用MCP工具获取天气数据
5. 将结果保存为任务artifacts并更新任务状态
6. 启动服务器监听指定端口
"""

from python_a2a import A2AServer, run_server, AgentCard, AgentSkill, TaskStatus, TaskState
from python_a2a.mcp import MCPClient
import asyncio

# 1. 定义代理卡片，包含代理名信称、描述、URL和技能息
# A2A Agent 的名片
agent_card = AgentCard(
    name="WeatherServer",
    description="用来查询天气",
    url="http://127.0.0.1:8005",
    skills=[AgentSkill(name="查询天气", description="查询指定城市的天气")]
)


# 2. 创建自定义A2AServer子类，集成MCP客户端连接下游工具
class WeatherServer(A2AServer):
    def __init__(self):
        super().__init__(agent_card=agent_card)

        # 在内部，它拥有一个 MCP 客户端，用于连接下游工具
        self.mcp_client = MCPClient("http://127.0.0.1:6005")
        # 可以创建多个MCP客户端，链接多个MCP服务端。

    # 3. 实现handle_task方法处理传入的天气查询任务
    def handle_task(self, task):
        print("收到A2A任务的task:=>", task)

        query = (task.message or {}).get("content", {}).get("text", "")

        print(f"[{self.agent_card.name} 日志] 收到 A2A 任务: '{query}'")

        # 决策：如果查询包含"天气"，就调用 MCP 工具

        # 4. 根据任务内容决策是否调用MCP工具获取天气数据
        if "天气" in query:
            city = "北京"  # 简单提取城市
            print(f"[{self.agent_card.name} 日志] 决策：任务需要天气数据，准备调用 MCP 工具...")

            # 异步调用 MCP 工具
            try:
                # 在同步方法中运行异步代码的标准方式
                weather_result = asyncio.run(self.mcp_client.call_tool("get_weather", city=city))

                print(f"[{self.agent_card.name} 日志] 从 MCP 工具获得结果: '{weather_result}'")
                # 5. 将结果保存为任务artifacts并更新任务状态
                task.artifacts = [{"parts": [{"type": "text", "text": weather_result}]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)
            except Exception as e:
                error_msg = f"调用 MCP 工具失败: {e}"
                print(f"[{self.agent_card.name} 日志] {error_msg}")
                task.artifacts = [{"parts": [{"type": "text", "text": error_msg}]}]
                task.status = TaskStatus(state=TaskState.FAILED)
        else:
            task.artifacts = [{"parts": [{"type": "text", "text": "无法理解的任务"}]}]
            task.status = TaskStatus(state=TaskState.FAILED)


        print(f"[{self.agent_card.name} 日志] 任务完成，结果已返回给 A2A")
        print("task:=>", task)
        print("task.artifacts:=>", task.artifacts)
        return task


if __name__ == "__main__":
    server = WeatherServer()
    print(f"[{server.agent_card.name}] 已启动，在 {server.agent_card.url}")
    run_server(server, host="127.0.0.1", port=8005)