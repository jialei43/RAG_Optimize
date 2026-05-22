from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage

from agent_learn.config import Config

conf = Config()


# todo: 第一步：定义工具函数
def add(a: int, b: int) -> int:
    """
    将数字a与数字b相加
    Args:
        a: 第一个数字
        b: 第二个数字
    """
    return a + b


def multiply(a: int, b: int) -> int:
    """
    将数字a与数字b相乘
    Args:
        a: 第一个数字
        b: 第二个数字
    """
    return a * b



# 定义 JSON 格式的工具 schema
tools = [
    {
        "type": "function",
        "function": {
            "name": "add",
            "description": "将数字a与数字b相加",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {
                        "type": "integer",
                        "description": "第一个数字"
                    },
                    "b": {
                        "type": "integer",
                        "description": "第二个数字"
                    }
                },
                "required": ["a", "b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "multiply",
            "description": "将数字a与数字b相乘",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {
                        "type": "integer",
                        "description": "第一个数字"
                    },
                    "b": {
                        "type": "integer",
                        "description": "第二个数字"
                    }
                },
                "required": ["a", "b"]
            }
        }
    }
]

# todo: 第二步：初始化模型
llm = ChatOpenAI(base_url=conf.base_url,
                 api_key=conf.api_key,
                 model=conf.model_name,
                 temperature=0.1)
# 绑定工具，允许模型自动选择工具
llm_with_tools = llm.bind_tools(tools, tool_choice="auto")



# todo: 第三步：调用回复
query = "2+1等于多少？"
messages = [HumanMessage(query)]

try:
    # todo: 第一次调用
    # llm_with_tools -> langchain的chat模型， [SystemMessage, HumanMessage]
    # ai_msg : AiMessage
    ai_msg = llm_with_tools.invoke(messages)
    messages.append(ai_msg)
    print(f"\n第一轮调用后结果：\n{messages}")

    # 处理工具调用
    # 判断消息中是否有tool_calls，以判断工具是否被调用
    # if ai_msg.get('tool_calls') :
    # 'tool_calls': [{'id': '019d18b718f59210f595d356a503b9b9', 'function': {'arguments': '{"a": 2, "b": 1}', 'name': 'add'}, 'type': 'function'}]
    if hasattr(ai_msg, 'tool_calls') and ai_msg.tool_calls:
        # [{'id': '019d18b718f59210f595d356a503b9b9', 'function': {'arguments': '{"a": 2, "b": 1}', 'name': 'add'}, 'type': 'function'}]
        for tool_call in ai_msg.tool_calls:
            # 'function': {'arguments': '{"a": 2, "b": 1}', 'name': 'add'}
            # todo: 处理工具调用
            # tool_call["name"] -> 'add'
            # 定义一个字段，把工具名和具体的函数关联起来
            tool_dict = {"add": add, "multiply": multiply}
            # 从大模型的返回结果中获取要调用的工具名
            tool_name = tool_call["name"].lower()
            # 选择要调用的函数
            selected_tool = tool_dict[tool_name]
            # selected_tool: add函数
            # 从大模型的返回结果中获取调用工具的参数名和参数值
            # TODO '{"a": 2, "b": 1}
            arguments = tool_call["args"]
            # add(1,2)
            # add(a=1,b=2)
            # **{'a':1, 'b':2}
            tool_output = selected_tool(**arguments)
            messages.append(ToolMessage(content=tool_output, tool_call_id=tool_call["id"]))
        print(f"\n第二轮  message中增加tool_output 之后：\n{messages}")

        # todo: 第二次调用，将工具结果传回模型以生成最终回答
        final_response = llm_with_tools.invoke(messages)
        print(f"\n最终模型响应：\n{final_response.content}")
    else:
        print("模型未生成工具调用，直接返回文本:")
        print(ai_msg.content)
except Exception as e:
    print(f"模型调用失败: {str(e)}")