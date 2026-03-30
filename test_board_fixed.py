#!/usr/bin/env python3
"""测试连板计算修复后"""
import os
import json
from datetime import datetime, timedelta

# 直接定义修复后的函数
_BOARD_DAYS_CACHE = {}

def get_limit_up_data_by_date(date_str: str) -> set:
    """获取指定日期的涨停股代码集合"""
    try:
        cache_dir = './data/limit_up_history'
        file_path = os.path.join(cache_dir, f'{date_str}.json')

        if not os.path.exists(file_path):
            return set()

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        codes = set()
        for stock in data.get('stocks', []):
            # 兼容两种数据格式：新格式有'code'字段，旧格式从'代码'字段提取
            code = stock.get('code', '')
            if not code:
                # 尝试从'代码'字段提取（可能包含sh/sz/bj前缀）
                full_code = stock.get('代码', '')
                code = full_code.replace('sh', '').replace('sz', '').replace('bj', '')
            if code:
                codes.add(code)

        return codes
    except Exception as e:
        print(f"[DEBUG] 读取{date_str}涨停数据失败: {e}")
        return set()


def calculate_continuous_limit_up_days_from_history(symbol: str) -> int:
    """利用涨停历史数据计算连板天数"""
    try:
        # 检查缓存
        if symbol in _BOARD_DAYS_CACHE:
            return _BOARD_DAYS_CACHE[symbol]

        # 获取所有可用的历史涨停数据日期（最近10天）
        cache_dir = './data/limit_up_history'
        today = datetime.now()

        # 收集所有可用的交易日文件
        available_dates = []
        for i in range(10):  # 检查最近10天
            date_obj = today - timedelta(days=i)
            if date_obj.weekday() >= 5:  # 跳过周末
                continue
            date_str = date_obj.strftime('%Y%m%d')
            file_path = os.path.join(cache_dir, f'{date_str}.json')
            if os.path.exists(file_path):
                available_dates.append(date_str)

        # 按日期降序排列（从最近到最远）
        available_dates.sort(reverse=True)

        if not available_dates:
            return 0

        # 从最近一天开始检查连续涨停
        continuous_days = 0

        for date_str in available_dates:
            limit_up_codes = get_limit_up_data_by_date(date_str)

            if symbol in limit_up_codes:
                continuous_days += 1
            else:
                # 遇到第一个非涨停就停止（因为已经按日期降序）
                break

        # 缓存结果
        _BOARD_DAYS_CACHE[symbol] = continuous_days
        return continuous_days

    except Exception as e:
        print(f"[DEBUG] 从历史数据计算连板失败({symbol}): {e}")
        import traceback
        traceback.print_exc()
        return 0


print("="*70)
print("测试华电辽能(600396)连板计算")
print("="*70)
print()

# 先查看可用日期
cache_dir = './data/limit_up_history'
today = datetime.now()
available_dates = []
for i in range(10):
    date_obj = today - timedelta(days=i)
    if date_obj.weekday() >= 5:
        continue
    date_str = date_obj.strftime('%Y%m%d')
    file_path = os.path.join(cache_dir, f'{date_str}.json')
    if os.path.exists(file_path):
        available_dates.append(date_str)

available_dates.sort(reverse=True)
print(f"可用交易日(降序): {available_dates}")
print()

for date_str in available_dates:
    codes = get_limit_up_data_by_date(date_str)
    is_limit = '600396' in codes
    print(f"{date_str}: {'涨停 ✓' if is_limit else '非涨停 ✗'} (共{len(codes)}只涨停股)")

print()
boards = calculate_continuous_limit_up_days_from_history('600396')
print(f"华电辽能(600396): {boards}板")
print()

# 测试其他股票
test_stocks = [
    ('002310', '东方新能'),
    ('603687', '大胜达'),
    ('002150', '正泰电源'),
]

for code, name in test_stocks:
    boards = calculate_continuous_limit_up_days_from_history(code)
    print(f"{name}({code}): {boards}板")

print()
print("="*70)
