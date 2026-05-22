"""
需求：实现反射模式，让AI能够根据反馈改进回答质量
思路步骤：
1. 创建大语言模型实例，配置API参数
2. 构建初始响应链，用于生成初次回答
3. 构建反思链，用于根据用户反馈优化回答
4. 实现完整的反射流程，包括初答、反馈接收和优化
5. 测试反射模式对回答质量的提升效果
"""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from agent_learn.config import Config

conf = Config()

# 1. 创建大语言模型实例，配置API参数
llm = ChatOpenAI(base_url=conf.base_url,
                 api_key=conf.api_key,
                 model=conf.model_name,
                 temperature=0.1)

# 2. 构建初始响应链，用于生成初次回答
initial_response_prompt = ChatPromptTemplate.from_template(
    "请根据以下问题给出你的初步回答: {question}"
)
initial_response_chain = initial_response_prompt | llm | StrOutputParser()

# 4.构建反思链，用于根据用户反馈优化回答
reflection_prompt = ChatPromptTemplate.from_template(
    """你是一个专业的、善于反思的AI助手。你之前给出了以下回答：
---
{previous_response}
---
现在，你收到了用户对你的回答给出的反馈：
---
{user_feedback}
---
请根据用户的反馈，认真反思你之前的回答，并生成一个更准确、更完善的新回答。
新回答:"""
)
reflection_chain = reflection_prompt | llm | StrOutputParser()


#4. 实现完整的反射流程，包括初答、反馈接收和优化
def reflect_and_refine(query: str):
    """模拟一个完整的反射过程，从初始响应到优化后的响应。"""

    print("--- 启动反射模式 ---")
    print(f"用户查询: {query}")

    # LLM 生成初步响应
    print("\n生成初步响应...")
    initial_response = initial_response_chain.invoke({"question": query})
    print(f"LLM 初步响应:\n{initial_response}")

    feedback = input("请输入反馈：")

    # 模拟用户反馈
    print(f"\n用户反馈:\n{feedback}")

    # LLM 进行反思，并生成新的回答
    print("\nLLM 正在反思并生成新响应...")
    refined_response = reflection_chain.invoke({
        "previous_response": initial_response,
        "user_feedback": feedback
    })

    print("\n--- LLM 经过反思后的新响应 ---")
    print(refined_response)

    return refined_response


# 5. 测试反射模式对回答质量的提升效果
if __name__ == "__main__":
    # 模拟用户查询
    initial_question = "我的邻居姓王，给他的儿子起个名字"
    # 模拟用户反馈，指出初步回答的不足
    # user_feedback_text = "你的回答太简单了，请更详细地解释一下 LangChain 的核心概念，比如 Agent 和 Chain 的区别。"
    # 运行反射过程
    reflect_and_refine(initial_question)