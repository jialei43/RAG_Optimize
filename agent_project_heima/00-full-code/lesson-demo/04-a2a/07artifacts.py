"""
需求：实现A2A服务器端，处理任务并将结果存储到artifacts中
思路步骤：
1. 定义代理卡片，包含代理名称、描述、URL和技能信息
2. 创建自定义A2AServer子类，重写任务处理逻辑
3. 解析任务内容并根据条件生成相应结果
4. 将处理结果存储到artifacts中并更新任务状态
5. 启动服务器监听指定端口
"""

from python_a2a import A2AServer, run_server, AgentCard, AgentSkill, TaskStatus, TaskState
from python_a2a import *

# 定义代理卡片
ticket_card = AgentCard(
    name="TicketAgentServer",
    description="票务代理",
    url="http://127.0.0.1:5010",
    skills=[AgentSkill(name="book_ticket", description="预订票务")]
)

# 自定义 A2AServer 子类
class TicketServer(A2AServer):
    def __init__(self):
        super().__init__(agent_card=ticket_card)

    def handle_task(self, task):
        print("收到A2A任务的task:=>", task)
        # Task(
        #   id='8c83215a-61e3-40f7-b08a-0e60772db447',
        #   session_id='2863d3a3-67b1-4039-8043-2d6d55fcc2d1',
        #   status=TaskStatus(state=<TaskState.SUBMITTED: 'submitted'>, message=None, timestamp='2026-02-28T18:01:46.980775'),
        #
        #   message={
        #       'content': {'text': '查询天气', 'type': <ContentType.TEXT: 'text'>},
        #       'role': 'user',
        #       'message_id': '108547d6-5848-4f98-80f9-eb0e56eb05b1'
        #       },
        #
        #   history=[],
        #   artifacts=[],
        #   metadata={}
        # )


        #默认写法：获取任务内容
        # TODO message = Message(content=TextContent(text="查询天气"), role=MessageRole.USER)
        query = (task.message or {}).get("content", {}).get("text", "")

        if "上海" in query and "北京" in query:
        # 这里的结果可以来自于 MCP 模块，这里我们直接模拟结果
            train_result = "上海到北京的火车票已经预订成功！  G1001,10车1A "
        else:
            train_result = "请输入明确的出发地和目的地。"


        # 服务端把处理的结果放到artifacts里面，格式是固定，内容不固定。
        task.artifacts = [
            {
                "parts":
                [
                {"type": "text", "text": train_result}
                ]
            }
        ]
        task.status = TaskStatus(state=TaskState.COMPLETED)


        print(f"[{self.agent_card.name} 日志] 任务处理完毕")
        print(f"[{self.agent_card.name} 日志] 输出结果task: {task}")
        print(f"[{self.agent_card.name} 日志] 输出结果task.artifacts: {task.artifacts}")
        return task

# 启动服务器
if __name__ == "__main__":
    server = TicketServer()
    print(f"[{server.agent_card.name}] 启动成功，服务地址: {server.agent_card.url}")
    run_server(server, host="127.0.0.1", port=5010, debug=True)

# 收到A2A任务的task:=>
# Task(
#   id='aef246f4-09ef-495f-8663-458eab99c8e7',
#   session_id='6f2cbe60-d6e7-47c2-917d-f4dab178f368',
#   status=TaskStatus(state=<TaskState.SUBMITTED: 'submitted'>, message=None, timestamp='2026-03-02T10:03:29.670558'),
#   message={'content': {'text': '预订一张从北京到上海的火车票', 'type': 'text'}, 'role': 'user', 'message_id': '188cb33d-e7e3-4348-bf11-b1a5d3f65b34'},
#   history=[],
#   artifacts=[],
#   metadata={}
#  )

# 输出结果task:
# Task(
#   id='aef246f4-09ef-495f-8663-458eab99c8e7',
#   session_id='6f2cbe60-d6e7-47c2-917d-f4dab178f368',
#   status=TaskStatus(state=<TaskState.COMPLETED: 'completed'>, message=None, timestamp='2026-03-02T10:03:29.683028'),
#   message={'content': {'text': '预订一张从北京到上海的火车票', 'type': 'text'}, 'role': 'user', 'message_id': '188cb33d-e7e3-4348-bf11-b1a5d3f65b34'},
#   history=[],
#   artifacts=[{'parts': [{'type': 'text', 'text': '上海到北京的火车票已经预订成功！  G1001,10车1A '}]}],
#   metadata={})
