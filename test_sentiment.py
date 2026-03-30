#!/usr/bin/env python3
"""测试深度市场情绪分析功能"""
import os
os.environ['DASHSCOPE_API_KEY'] = os.environ.get('DASHSCOPE_API_KEY', 'sk-54458b944b704de582533e1aa7290fca')

from test_agent_knowledge import analyze_market_sentiment

print("="*70)
print("📊 测试深度市场情绪分析功能")
print("="*70)
print()

try:
    result = analyze_market_sentiment.invoke({})
    print(result)
    print()
    print("="*70)
    print("✅ 测试完成！")
    print("="*70)
except Exception as e:
    print(f"❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()
