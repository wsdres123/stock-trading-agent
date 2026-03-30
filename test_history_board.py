#!/usr/bin/env python3
"""测试基于历史数据的连板计算"""
import os
os.environ['LD_LIBRARY_PATH'] = '/home/lixiang/anaconda3/lib'

from test_agent_knowledge import calculate_continuous_limit_up_days_from_history, get_limit_up_data_by_date

print("="*70)
print("测试基于历史数据的连板计算")
print("="*70)
print()

# 检查可用的历史数据
from datetime import datetime, timedelta

today = datetime.now()
print("可用的历史涨停数据日期:")
for i in range(7):
    date_obj = today - timedelta(days=i)
    if date_obj.weekday() < 5:  # 工作日
        date_str = date_obj.strftime('%Y%m%d')
        codes = get_limit_up_data_by_date(date_str)
        print(f"  {date_str}: {len(codes)}只涨停股")
print()

# 测试几只股票
test_stocks = [
    ("002565", "顺灏股份"),
    ("300085", "银之杰"),
]

for code, name in test_stocks:
    print(f"{name}({code}): {calculate_continuous_limit_up_days_from_history(code)}板")

print()
print("="*70)