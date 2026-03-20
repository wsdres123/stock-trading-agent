#!/usr/bin/env python3
"""
热股榜功能直接测试脚本
"""
import sys
from pathlib import Path

# 确保正确导入项目中的模块
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入模块
import hot_stocks_module

print("=" * 60)
print("热股榜模块测试")
print("=" * 60)

# 测试1：新浪财经热股榜（成交额）
print("\n【测试1】获取新浪财经热股榜（按成交额）...")
try:
    df, source_name = hot_stocks_module.get_hot_stocks(source='sina_amount', top_n=10)
    if not df.empty:
        print(f"✓ 成功获取 {len(df)} 只股票")
        print(f"  数据源: {source_name}")
        print("\n  前3名:")
        cols = ['代码', '名称', '涨跌幅', '成交额(亿)', '热度排名']
        available_cols = [col for col in cols if col in df.columns]
        print(df[available_cols].head(3).to_string(index=False))
    else:
        print("✗ 获取失败: 返回空数据")
except Exception as e:
    print(f"✗ 异常: {e}")

# 测试2：新浪财经热股榜（涨跌幅）
print("\n" + "-" * 60)
print("【测试2】获取新浪财经热股榜（按涨跌幅）...")
try:
    df, source_name = hot_stocks_module.get_hot_stocks(source='sina_change', top_n=10)
    if not df.empty:
        print(f"✓ 成功获取 {len(df)} 只股票")
        print(f"  数据源: {source_name}")
        print("\n  前3名:")
        cols = ['代码', '名称', '涨跌幅', '成交额(亿)', '热度排名']
        available_cols = [col for col in cols if col in df.columns]
        print(df[available_cols].head(3).to_string(index=False))
    else:
        print("✗ 获取失败: 返回空数据")
except Exception as e:
    print(f"✗ 异常: {e}")

# 测试3：东方财富热股榜
print("\n" + "-" * 60)
print("【测试3】获取东方财富热股榜...")
try:
    df, source_name = hot_stocks_module.get_hot_stocks(source='eastmoney', top_n=10)
    if not df.empty:
        print(f"✓ 成功获取 {len(df)} 只股票")
        print(f"  数据源: {source_name}")
        print("\n  前3名:")
        cols = ['代码', '名称', '涨跌幅', '成交额(亿)', '主力净流入(万)', '热度排名']
        available_cols = [col for col in cols if col in df.columns]
        print(df[available_cols].head(3).to_string(index=False))
    else:
        print("✗ 获取失败: 返回空数据")
except Exception as e:
    print(f"✗ 异常: {e}")

# 测试4：赚钱效应分析
print("\n" + "-" * 60)
print("【测试4】赚钱效应分析...")
try:
    df, _ = hot_stocks_module.get_hot_stocks(source='sina_amount', top_n=30)
    if not df.empty:
        analysis = hot_stocks_module.analyze_profit_effect(df)

        if analysis.get('status') == 'success':
            print(f"✓ 分析完成")
            print(f"  等级: {analysis['赚钱效应评级']['等级']}")
            print(f"  描述: {analysis['赚钱效应评级']['描述']}")
            print(f"\n  基础统计:")
            print(f"    平均涨幅: {analysis['基础统计']['平均涨幅']:.2f}%")
            print(f"    涨停数量: {analysis['基础统计']['涨停股票数']}只")
            print(f"  操作建议:")
            for i, suggestion in enumerate(analysis['操作建议'][:3], 1):
                print(f"    {i}. {suggestion}")
        else:
            print(f"✗ 分析失败: {analysis.get('message', '未知错误')}")
    else:
        print("✗ 分析失败: 无法获取热股榜数据")
except Exception as e:
    print(f"✗ 异常: {e}")

# 测试5：综合热度算法
print("\n" + "-" * 60)
print("【测试5】综合热度算法...")
try:
    df, source_name = hot_stocks_module.get_hot_stocks(source='composite', top_n=10)
    if not df.empty:
        print(f"✓ 成功计算 {len(df)} 只股票的综合热度")
        print(f"  数据源: {source_name}")
        print("\n  前3名:")
        cols = ['代码', '名称', '涨跌幅', '成交额(亿)', '热度得分', '热度排名']
        available_cols = [col for col in cols if col in df.columns]
        print(df[available_cols].head(3).to_string(index=False))
    else:
        print("✗ 计算失败: 返回空数据")
except Exception as e:
    print(f"✗ 异常: {e}")

# 测试6：数据缓存功能
print("\n" + "-" * 60)
print("【测试6】数据缓存功能...")
try:
    # 第一次请求（应该从API获取）
    print("  第一次请求（从API获取）...")
    df1, _ = hot_stocks_module.get_hot_stocks(source='sina_amount', top_n=10, use_cache=True)

    # 第二次请求（应该从缓存读取）
    print("  第二次请求（从缓存读取）...")
    df2, _ = hot_stocks_module.get_hot_stocks(source='sina_amount', top_n=10, use_cache=True)

    if not df1.empty and not df2.empty and len(df1) == len(df2):
        print("✓ 缓存功能正常工作")
    else:
        print("✗ 缓存功能异常")
except Exception as e:
    print(f"✗ 异常: {e}")

print("\n" + "=" * 60)
print("测试完成!")
print("=" * 60)