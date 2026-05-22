"""
需求：定义任务数据结构，封装用户请求信息
思路步骤：
1. 创建消息对象，包含用户问题和角色信息
2. 将消息封装到任务对象中
3. 输出任务对象用于调试和验证
"""

from python_a2a import Task, Message, MessageRole, TextContent

# 创建任务的message，包含用户的问题，也就是从客户端发送给服务端时，把用的问题封装到Message
message = Message(content=TextContent(text="查询天气"), role=MessageRole.USER)

# 创建一个任务
task = Task(message=message.to_dict())
print(task)

# Task(
#   id='8c83215a-61e3-40f7-b08a-0e60772db447',
#   session_id='2863d3a3-67b1-4039-8043-2d6d55fcc2d1',
#   status=TaskStatus(state=<TaskState.SUBMITTED: 'submitted'>, message=None, timestamp='2026-02-28T18:01:46.980775'),
#   message={'content': {'text': '查询天气', 'type': <ContentType.TEXT: 'text'>}, 'role': 'user', 'message_id': '108547d6-5848-4f98-80f9-eb0e56eb05b1'},
#   history=[],
#   artifacts=[],
#   metadata={}
# )