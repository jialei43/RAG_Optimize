"""
需求：实现AI代理路由功能，根据用户查询智能分配到合适的代理
思路步骤：
1. 初始化配置和网络连接
2. 创建代理网络并注册可用的代理节点
3. 初始化大语言模型客户端
4. 创建路由器实例并执行查询路由
5. 返回最匹配的代理名称及置信度
"""

from python_a2a import AIAgentRouter, AgentNetwork
from langchain_openai import ChatOpenAI
from agent_learn.config import Config

conf=Config()

# 创建网络
network = AgentNetwork(name="MyNetwork")
network.add("TicketAgent", "http://127.0.0.1:5010")

# 创建模型
llm = ChatOpenAI(base_url=conf.base_url,
                 api_key=conf.api_key,
                 model=conf.model_name,
                 temperature=0.1)

# 创建路由器
router = AIAgentRouter(llm_client=llm, agent_network=network)
agent_name, confidence = router.route_query("预订火车票")
print(agent_name, confidence)