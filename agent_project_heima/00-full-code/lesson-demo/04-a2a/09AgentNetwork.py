"""
需求：实现代理网络管理，支持多代理注册与调用
思路步骤：
1. 创建代理网络实例并命名
2. 向网络中添加不同类型的代理节点
3. 提供获取特定代理的方法
4. 支持通过代理网络调用具体代理服务
"""

from python_a2a import AgentNetwork

network = AgentNetwork(name="MyNetwork")

network.add("TicketAgent", "http://127.0.0.1:5010")
# 还能添加多个不同的Agent。

#  TODO network：本质是一个字典，记录agent名和AgentCard的映射


print(f"agent network-->{network.agent_cards}")
# 拿取AgentCard的作用？
#


# {'TicketAgent':
#   AgentCard(
#       name='TicketAgentServer',
#       description='票务代理',
#       url='http://127.0.0.1:5010', version='1.0.0', authentication=None, capabilities={'google_a2a_compatible': True, 'parts_array_format': True, 'pushNotifications': False, 'stateTransitionHistory': False, 'streaming': True},
#       default_input_modes=['text/plain'],
#       default_output_modes=['text/plain'],
#       skills=[AgentSkill(name='book_ticket', description='预订票务', id='74e8baeb-bd77-4449-b34f-a3d72b514796', tags=[], examples=[], input_modes=['text/plain'], output_modes=['text/plain'])],
#       provider=None,
#       documentation_url=None)
#   }
#
print('*'*80)
#
# 调用
# get_agent 返回的是agent的client对象
client = network.get_agent("TicketAgent")
print(client.ask("预订一张从北京到上海的火车票"))