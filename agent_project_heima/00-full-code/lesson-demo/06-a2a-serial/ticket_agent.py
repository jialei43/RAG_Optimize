"""
需求：实现A2A票务代理服务器，处理火车票预订任务
思路步骤：
1. 定义代理卡片，包含代理名称、描述、URL和技能信息
2. 创建自定义A2AServer子类，继承基础服务器功能
3. 实现handle_task方法处理传入的票务预订任务
4. 根据任务内容生成相应的预订结果
5. 更新任务状态和artifacts，返回处理结果
6. 启动服务器监听指定端口
"""

from python_a2a import A2AServer, run_server, AgentCard, AgentSkill, TaskStatus, TaskState

ticket_card = AgentCard(
    name="TicketAgentServer",
    description="一个可以预订票务的专家 Agent。",
    url="http://127.0.0.1:5009",
    version="1.0.0",
    skills=[AgentSkill(name="book_ticket", description="预订票务")]
)

class TicketServer(A2AServer):
    def __init__(self):
        super().__init__(agent_card=ticket_card)

    def handle_task(self, task):
        print("收到A2A任务的task:=>", task)
        query = (task.message or {}).get("content", {}).get("text", "")
        print(f"[{self.agent_card.name} 日志] 收到 A2A 任务: '{query}'")

        if "上海" in query and "北京" in query:
        # 这里的结果可以来自于 MCP 模块，这里我们直接模拟结果
            train_result = "上海到北京的火车票已经预订成功！  G1001,10车1A "
            task.status = TaskStatus(state=TaskState.COMPLETED)
        else:
            train_result = "请输入明确的出发地和目的地。"
            task.status = TaskStatus(state=TaskState.INPUT_REQUIRED)
        print(f"[{self.agent_card.name} 日志] 返回结果: {train_result}")
        task.artifacts = [{"parts": [{"type": "text", "text": train_result}]}]
        print(f"[{self.agent_card.name} 日志] 任务处理完毕")
        print(f"[{self.agent_card.name} 日志] 输出结果task: {task}")
        print(f"[{self.agent_card.name} 日志] 输出结果task.artifacts: {task.artifacts}")
        return task


if __name__ == "__main__":
    server = TicketServer()
    print(f"[{server.agent_card.name}] 启动成功，服务地址: {server.agent_card.url}")
    run_server(server, host="127.0.0.1", port=5009)