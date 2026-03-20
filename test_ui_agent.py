"""测试UI中的Agent功能"""
import os
os.environ['DASHSCOPE_API_KEY'] = os.environ.get('DASHSCOPE_API_KEY', 'sk-54458b944b704de582533e1aa7290fca')

from agent_ui import initialize_agent

print("初始化Agent...")
if not initialize_agent():
    print("初始化失败")
    exit(1)

# 直接导入agent_ui模块来获取全局变量
import agent_ui

print("\n测试1: 今日涨停")
result1 = agent_ui.AGENT_EXECUTOR.invoke({"input": "今天涨停股有哪些？"})
print(f"结果1: {result1.get('output', 'FAIL')[:500]}...")

print("\n测试2: 连板梯队")
result2 = agent_ui.AGENT_EXECUTOR.invoke({"input": "连板梯队情况如何？"})
print(f"结果2: {result2.get('output', 'FAIL')[:500]}...")

print("\n✅ 测试通过")