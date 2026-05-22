"""
需求：定义代理卡片和技能，描述代理的能力和服务接口
思路步骤：
1. 创建不同的代理技能，包括技能名称、描述、使用示例和输入输出模式
2. 定义代理卡片，包含代理基本信息、URL、版本和技能列表
3. 输出代理卡片的字典表示用于序列化
"""

from python_a2a import AgentCard, AgentSkill
# 创建一个代理技能
ticket_skill = AgentSkill(
    name="book_ticket",
    description="预订火车票的技能",
    examples=["预订从上海到北京的火车票"],
    input_modes=["text/plain"],  # text/html
    output_modes=["text/plain"]
)

info_skill1 = AgentSkill(
    name="view",
    description="查询景点",
    examples=["帮我看下北京的著名景点"],
    input_modes=["text/plain"],  # text/html
    output_modes=["text/plain"]
)

# Agent具有哪些能力，其实代表着Agent能够使用哪些工具。
# 比如在这个Agent底层的MCP中封装了订票的功能，那这个Agent就有了这个订票能力。

# 创建代理卡片
agent_card = AgentCard(
    name="TicketAgent",
    description="一个可以预订票务 和 查询景点的 agent",
    url="http://127.0.0.1:5009",
    version="1.0.0",
    skills=[ticket_skill,info_skill1],
    capabilities={"streaming": True}
)
# 打印代理卡片的字典表示（用于序列化）
# print(agent_card)
print(agent_card.to_dict())