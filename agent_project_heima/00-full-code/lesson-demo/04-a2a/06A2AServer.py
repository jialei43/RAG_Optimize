"""
需求：实现A2A架构中的服务器端，提供票务代理服务
思路步骤：
1. 定义代理卡片，包含代理名称、描述、URL和技能信息
2. 创建自定义A2AServer子类，继承基础服务器功能
3. 实现handle_task方法处理传入的任务
4. 启动服务器监听指定端口
"""

from python_a2a import A2AServer, run_server, AgentCard, AgentSkill, TaskStatus, TaskState

# 定义代理卡片
ticket_card = AgentCard(
    name="TicketAgentServer",
    description="票务代理",
    url="http://127.0.0.1:5009/a2a",
    skills=[AgentSkill(name="book_ticket", description="预订票务")]
)

# 自定义 A2AServer 子类
class TicketServer(A2AServer):
    def __init__(self):
        super().__init__(agent_card=ticket_card)

    def handle_task(self, task):
        # 如果客户端把 task给到了服务端，服务端处理完task，会返回给客户端。
        print(f"任务状态：{task.status.state}")

        return task

# 启动服务器
if __name__ == "__main__":
    server = TicketServer()
    print(f"[{server.agent_card.name}] 创建服务成功")
    run_server(server, host="127.0.0.1", port=5009, debug=False)