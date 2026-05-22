"""
需求：实现A2A票务代理服务器，处理火车票预订任务
思路步骤：
1. 定义代理卡片，包含代理名称、描述、URL和技能信息
2. 创建自定义A2AServer子类，继承基础服务器功能
3. 实现handle_task方法处理传入的票务预订任务
4. 使用Agent网络和大模型智能决定是否调用天气工具
5. 根据任务内容和天气情况生成相应的预订结果
6. 更新任务状态和artifacts，返回处理结果
7. 启动服务器监听指定端口
"""

import requests
import json
from python_a2a import A2AServer, run_server, AgentCard, AgentSkill, TaskStatus, TaskState, A2AClient, Task, Message, MessageRole, TextContent
import uuid
from time import sleep

ticket_card = AgentCard(
    name="TicketAgentServer",
    description="一个可以预订票务的专家 Agent，会根据大模型智能判断是否需要调用天气工具来辅助决策。",
    url="http://127.0.0.1:5009",
    version="1.0.0",
    skills=[
        AgentSkill(name="book_ticket", description="预订票务"),
        AgentSkill(name="check_weather_condition", description="检查天气条件以决定是否处理票务"),
        AgentSkill(name="use_weather_agent", description="调用天气代理获取天气信息", examples=["需要获取天气信息来辅助票务决策"])
    ]
)

class TicketServer(A2AServer):
    def __init__(self):
        super().__init__(agent_card=ticket_card)
        
        # 创建一个Agent网络用于内部工具调用
        from python_a2a import AgentNetwork, AIAgentRouter
        self.network = AgentNetwork(name="InternalToolNetwork")
        self.network.add("WeatherAgent", "http://127.0.0.1:5008")
        
        # 创建AI路由器用于智能决定是否调用天气工具
        self.router = AIAgentRouter(
            llm_client=A2AClient("http://localhost:5555"),  # 使用相同的LLM服务
            agent_network=self.network
        )

    def should_check_weather(self, query):
        """
        使用大模型智能判断是否需要检查天气
        """
        try:
            # 构建一个提示，询问是否需要检查天气
            decision_prompt = f"""
            分析以下用户请求，判断是否需要获取天气信息来辅助票务决策：
            用户请求："{query}"
            
            回答格式：
            决定：[是/否]
            理由：[简短理由]
            
            注意：如果请求涉及旅行计划、户外活动或用户明确提到天气相关问题，则应检查天气。
            """
            
            # 使用LLM客户端进行决策
            llm_client = A2AClient("http://localhost:5555")
            message = Message(
                content=TextContent(text=decision_prompt),
                role=MessageRole.USER
            )
            task = Task(
                id="decision-task-" + str(uuid.uuid4()),
                message=message.to_dict()
            )
            
            result = llm_client.send_task(task)
            sleep(1)  # 等待处理
            
            # 解析LLM的决策结果
            decision_artifacts = result.artifacts
            if decision_artifacts and len(decision_artifacts) > 0:
                decision_data = decision_artifacts[0].get("parts", [])
                if decision_data and len(decision_data) > 0:
                    decision_text = decision_data[0].get("text", "")
                    print(f"[{self.agent_card.name} 日志] LLM决策结果: {decision_text}")
                    
                    # 解析是否需要检查天气
                    need_weather = "是" in decision_text or "需要" in decision_text
                    return need_weather, decision_text
                else:
                    print(f"[{self.agent_card.name} 日志] 无法解析LLM决策结果")
                    return False, "无法解析决策"
            else:
                print(f"[{self.agent_card.name} 日志] LLM未返回决策结果")
                return False, "无决策结果"
                
        except Exception as e:
            print(f"[{self.agent_card.name} 日志] LLM决策过程出错: {e}")
            # 出错时默认不需要检查天气
            return False, f"决策出错: {e}"

    def get_weather_info(self, city="北京"):
        """
        通过Agent网络调用天气代理获取天气信息
        """
        try:
            print(f"[{self.agent_card.name} 日志] 通过Agent网络调用天气代理检查 {city} 的天气情况...")
            
            # 使用路由器智能选择天气代理
            agent_name, confidence = self.router.route_query(f"查询{city}的天气")
            
            if agent_name and agent_name.lower().startswith('weather'):
                # 获取天气代理客户端
                weather_client = self.network.get_agent(agent_name)
                if weather_client:
                    # 创建查询天气的消息和任务
                    weather_query = f"查询{city}的天气"
                    message = Message(
                        content=TextContent(text=weather_query),
                        role=MessageRole.USER
                    )
                    task = Task(
                        id="weather-task-" + str(uuid.uuid4()),
                        message=message.to_dict()
                    )
                    
                    # 发送任务到天气代理
                    result = weather_client.send_task(task)
                    sleep(2)  # 等待天气代理处理
                    
                    # 解析天气结果
                    weather_artifacts = result.artifacts
                    if weather_artifacts and len(weather_artifacts) > 0:
                        weather_data = weather_artifacts[0].get("parts", [])
                        if weather_data and len(weather_data) > 0:
                            weather_text = weather_data[0].get("text", {})
                            print(f"[{self.agent_card.name} 日志] 从天气代理获取的数据: {weather_text}")
                            
                            # 解析天气信息
                            if isinstance(weather_text, dict):
                                weather_desc = weather_text.get("天气", "未知")
                            else:
                                weather_desc = str(weather_text)
                            
                            # 判断是否晴朗
                            is_sunny = "晴" in weather_desc or "晴天" in weather_desc
                            
                            print(f"[{self.agent_card.name} 日志] {city} 当前天气: {weather_desc}，是否晴朗: {is_sunny}")
                            return is_sunny, {"天气": weather_desc}
                        else:
                            print(f"[{self.agent_card.name} 日志] 无法解析天气代理返回的数据")
                            return True, {"天气": "未知天气", "错误": "无法解析天气数据"}
                    else:
                        print(f"[{self.agent_card.name} 日志] 天气代理未返回有效数据")
                        return True, {"天气": "未知天气", "错误": "天气代理未返回数据"}
                else:
                    print(f"[{self.agent_card.name} 日志] 无法获取天气代理客户端")
                    return True, {"天气": "未知天气", "错误": "无法获取天气代理"}
            else:
                print(f"[{self.agent_card.name} 日志] 未找到合适的天气代理: {agent_name}")
                return True, {"天气": "未知天气", "错误": "未找到天气代理"}
                
        except Exception as e:
            print(f"[{self.agent_card.name} 日志] 调用天气代理失败: {e}")
            return True, {"天气": "未知天气", "错误": f"调用天气代理失败: {e}"}

    def handle_task(self, task):
        print("收到A2A任务的task:=>", task)
        query = (task.message or {}).get("content", {}).get("text", "")
        print(f"[{self.agent_card.name} 日志] 收到 A2A 任务: '{query}'")

        # 检查是否为票务相关任务
        if any(keyword in query for keyword in ["票", "火车", "飞机", "预订", "购买"]):
            # 使用大模型智能判断是否需要检查天气
            need_weather, decision_reason = self.should_check_weather(query)
            
            if need_weather:
                print(f"[{self.agent_card.name} 日志] 根据大模型判断，需要检查天气。理由: {decision_reason}")
                
                # 提取目的地城市用于天气检查
                destination_city = "北京"  # 默认城市
                if "上海" in query and "北京" in query:
                    destination_city = "北京" if "到北京" in query or "北京到" in query else "上海"
                elif "上海" in query:
                    destination_city = "上海"
                elif "北京" in query:
                    destination_city = "北京"
                
                # 通过Agent网络获取天气信息
                is_sunny, weather_info = self.get_weather_info(destination_city)
                
                if is_sunny:
                    print(f"[{self.agent_card.name} 日志] 天气晴朗，允许处理票务预订")
                    if "上海" in query and "北京" in query:
                        # 这里的结果可以来自于 MCP 模块，这里我们直接模拟结果
                        train_result = f"根据天气情况分析，上海到北京的火车票可以预订！  G1001,10车1A。当前天气: {weather_info['天气']}"
                    else:
                        train_result = f"根据天气情况分析，票务预订可以处理... 请输入明确的出发地和目的地。当前天气: {weather_info['天气']}"
                else:
                    print(f"[{self.agent_card.name} 日志] 天气不佳，不建议出行")
                    train_result = f"根据天气分析，当前天气为 {weather_info['天气']}，不建议出行，暂不处理票务预订。"
            else:
                print(f"[{self.agent_card.name} 日志] 根据大模型判断，无需检查天气。理由: {decision_reason}")
                # 直接处理票务预订，不考虑天气
                if "上海" in query and "北京" in query:
                    train_result = "上海到北京的火车票已经预订成功！  G1001,10车1A （未考虑天气因素）"
                else:
                    train_result = "票务预订处理中... 请输入明确的出发地和目的地。（未考虑天气因素）"
        else:
            train_result = "请输入明确的票务预订请求。"

        print(f"[{self.agent_card.name} 日志] 返回结果: {train_result}")
        task.artifacts = [{"parts": [{"type": "text", "text": train_result}]}]
        task.status = TaskStatus(state=TaskState.COMPLETED)
        print(f"[{self.agent_card.name} 日志] 任务处理完毕")
        print(f"[{self.agent_card.name} 日志] 输出结果task: {task}")
        print(f"[{self.agent_card.name} 日志] 输出结果task.artifacts: {task.artifacts}")
        return task


if __name__ == "__main__":
    server = TicketServer()
    print(f"[{server.agent_card.name}] 启动成功，服务地址: {server.agent_card.url}")
    run_server(server, host="127.0.0.1", port=5009)