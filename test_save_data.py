#!/usr/bin/env python3
"""测试涨停股数据保存功能"""
import os
import sys

# 设置库路径
os.environ['LD_LIBRARY_PATH'] = '/home/lixiang/anaconda3/lib:' + os.environ.get('LD_LIBRARY_PATH', '')
os.environ['DASHSCOPE_API_KEY'] = 'sk-54458b944b704de582533e1aa7290fca'

from test_agent_knowledge import fetch_limit_up_stocks

print("=" * 70)
print("测试涨停股数据保存功能")
print("=" * 70)
print()

try:
    print("📊 正在获取今日涨停股数据...")
    df = fetch_limit_up_stocks()

    if df.empty:
        print("⚠️  今日暂无涨停股数据")
    else:
        print(f"✅ 获取到 {len(df)} 只涨停股")
        print()
        print("前5只涨停股:")
        for idx, row in df.head(5).iterrows():
            print(f"  {row['名称']}({row['代码']}) {row['涨跌幅']:.2f}%")

    print()
    print("=" * 70)
    print("✅ 测试完成！")
    print("=" * 70)
    print()
    print("查看保存的数据:")
    print("  ls -lh data/limit_up_history/")

except Exception as e:
    print(f"❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
