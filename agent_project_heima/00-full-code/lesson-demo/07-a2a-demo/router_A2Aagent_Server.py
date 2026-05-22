"""
需求：实现A2A代理服务器，将LangChain LLM转换为A2A兼容的服务
思路步骤：
1. 创建LangChain大语言模型实例，配置API参数
2. 将LLM转换为A2A服务器实例
3. 启动A2A服务器并监听指定端口
4. 使用异步方式运行服务器程序
"""

from langchain_openai import ChatOpenAI
from python_a2a import run_server
from python_a2a.langchain import to_a2a_server
import asyncio
from agent_learn.config import Config

conf = Config()

async def main():
    # 创建LangChain LLM
    llm = ChatOpenAI(base_url=conf.base_url,
                     api_key=conf.api_key,
                     model=conf.model_name,
                     temperature=0.1,
                     streaming=True)
    # 转换为A2A服务器
    llm_server = to_a2a_server(llm)
    print(llm_server.agent_card)
    # 启动服务器
    run_server(llm_server, port=5555)

if __name__ == '__main__':
    asyncio.run(main())