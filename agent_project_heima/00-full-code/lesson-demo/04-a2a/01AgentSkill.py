"""
需求：定义代理技能，描述代理可执行的具体功能
思路步骤：
1. 创建代理技能实例，包含技能名称、描述、使用示例和输入输出模式
2. 输出技能对象及其字典表示用于调试和序列化
"""

from python_a2a import  AgentSkill
# 定义一个代理技能
ticket_skill = AgentSkill(
    name="book_ticket",
    description="预订火车票的技能",
    examples=["预订从上海到北京的火车票"],
    input_modes=["text/plain"],
    output_modes=["text/plain"]
)

print(ticket_skill)
print(ticket_skill.to_dict())

# AgentSkill(
#   name='book_ticket',
#   description='预订火车票的技能',
#   id='612606cd-b963-4441-b94d-19a2e12d7c0d',
#   tags=[],
#   examples=['预订从上海到北京的火车票'],
#   input_modes=['text/plain'],
#   output_modes=['text/plain']
#   )
# {'id': '612606cd-b963-4441-b94d-19a2e12d7c0d', 'name': 'book_ticket', 'description': '预订火车票的技能', 'tags': [], 'examples': ['预订从上海到北京的火车票'], 'inputModes': ['text/plain'], 'outputModes': ['text/plain']}