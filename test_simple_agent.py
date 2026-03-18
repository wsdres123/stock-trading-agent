#!/usr/bin/env python3
"""简化的Agent测试 - 跳过知识库初始化"""
import os
os.environ['LD_LIBRARY_PATH'] = '/home/lixiang/anaconda3/lib'
os.environ['DASHSCOPE_API_KEY'] = 'sk-54458b944b704de582533e1aa7290fca'

from langchain_community.chat_models.tongyi import ChatTongyi
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import tool

# 定义简单工具
@tool
def get_test_data() -> str:
    """获取测试数据"""
    return "这是测试数据"

# 构建Agent
llm = ChatTongyi(
    model_name="qwen-turbo",
    temperature=0.1,
    streaming=False
)

tools = [get_test_data]

prompt = ChatPromptTemplate.from_messages([
    ("system", "你是助手，获取数据后立即回答，最多调用1次工具"),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad")
])

agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    max_iterations=5,
    handle_parsing_errors=True
)

print("="*70)
print("测试简化Agent")
print("="*70)

try:
    result = agent_executor.invoke({"input": "给我一些数据"})
    print("\n✅ 成功:")
    print(result['output'])
except Exception as e:
    print(f"\n❌ 失败: {e}")
    import traceback
    traceback.print_exc()
