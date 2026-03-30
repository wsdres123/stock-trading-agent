#!/usr/bin/env python3
"""测试单只股票的连板计算"""
import os
os.environ['LD_LIBRARY_PATH'] = '/home/lixiang/anaconda3/lib'
os.environ['DASHSCOPE_API_KEY'] = 'sk-54458b944b704de582533e1aa7290fca'

from test_agent_knowledge import calculate_continuous_limit_up_days

print("="*70)
print("测试单只股票的连板计算")
print("="*70)
print()

# 测试几只股票
test_stocks = [
    ("002565", "顺灏股份"),  # 今日涨停
    ("300085", "银之杰"),   # 今日涨停
    ("600036", "招商银行"),  # 大盘股，应该不会涨停
]

for code, name in test_stocks:
    print(f"\n测试: {name}({code})")
    print("-"*70)
    board_days = calculate_continuous_limit_up_days(code)
    print(f"结果: {board_days}板")
    print()

print("="*70)