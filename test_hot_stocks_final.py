#!/usr/bin/env python3
"""
热股榜功能测试脚本
测试热股榜模块和Agent工具的集成
"""
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

print("=" * 60)
print("热股榜功能测试")
print("=" * 60)

# 测试1：模块导入
print("\n【测试1】模块导入...")
try:
    import hot_stocks_module
    print("✓ hot_stocks_module导入成功")
except Exception as e:
    print(f"✗ 导入失败: {e}")
    sys.exit(1)

# 测试2：获取热股榜（成交额）
print("\n【测试2】获取热股榜（成交额）...")
try:
    df, source_name = hot_stocks_module.get_hot_stocks(source='sina_amount', top_n=10, use_cache=False)
    if not df.empty:
        print(f"✓ 成功获取 {len(df)} 只股票")
        print(f"  数据源: {source_name}")
        print("\n  前5名:")
        cols = ['代码', '名称', '涨跌幅', '成交额(亿)', '热度排名']
        available_cols = [col for col in cols if col in df.columns]
        print(df[available_cols].head(5).to_string(index=False))
    else:
        print("✗ 获取失败: 返回空数据")
except Exception as e:
    print(f"✗ 异常: {e}")
    import traceback
    traceback.print_exc()

# 测试3：获取热股榜（涨跌幅）
print("\n" + "-" * 60)
print("【测试3】获取热股榜（涨跌幅）...")
try:
    df, source_name = hot_stocks_module.get_hot_stocks(source='sina_change', top_n=5, use_cache=False)
    if not df.empty:
        print(f"✓ 成功获取 {len(df)} 只股票")
        print(f"  数据源: {source_name}")
        cols = ['代码', '名称', '涨跌幅', '热度排名']
        available_cols = [col for col in cols if col in df.columns]
        print(df[available_cols].to_string(index=False))
    else:
        print("✗ 获取失败: 返回空数据")
except Exception as e:
    print(f"✗ 异常: {e}")

# 测试4：赚钱效应分析
print("\n" + "-" * 60)
print("【测试4】赚钱效应分析...")
try:
    df, _ = hot_stocks_module.get_hot_stocks(source='sina_amount', top_n=30, use_cache=True)
    if not df.empty:
        analysis = hot_stocks_module.analyze_profit_effect(df)
        if analysis.get('status') == 'success':
            print(f"✓ 分析完成")
            print(f"  等级: {analysis['赚钱效应评级']['等级']}")
            print(f"  描述: {analysis['赚钱效应评级']['描述']}")
            print(f"\n  基础统计:")
            print(f"    平均涨幅: {analysis['基础统计']['平均涨幅']:.2f}%")
            print(f"    涨停数量: {analysis['基础统计']['涨停股票数']}只")

            if '成交额分析' in analysis:
                print(f"  成交额分析: {analysis['成交额分析']['总成交额(亿)']:.2f}亿")
        else:
            print(f"✗ 分析失败: {analysis.get('message', '未知错误')}")
    else:
        print("✗ 分析失败: 无法获取热股榜数据")
except Exception as e:
    print(f"✗ 异常: {e}")

# 测试5：缓存功能
print("\n" + "-" * 60)
print("【测试5】数据缓存功能...")
try:
    # 使用缓存
    df1, _ = hot_stocks_module.get_hot_stocks(source='sina_amount', top_n=10, use_cache=True)
    df2, _ = hot_stocks_module.get_hot_stocks(source='sina_amount', top_n=10, use_cache=True)

    if not df1.empty and not df2.empty and len(df1) == len(df2):
        print("✓ 缓存功能正常")
    else:
        print("✗ 缓存功能异常")
except Exception as e:
    print(f"✗ 异常: {e}")

# 测试6：Agent工具集成
print("\n" + "-" * 60)
print("【测试6】Agent工具集成...")
try:
    from test_agent_knowledge import get_hot_stocks_ranking, analyze_profit_effect

    # 测试 get_hot_stocks_ranking
    result1 = get_hot_stocks_ranking.invoke({'source': 'sina_amount', 'top_n': 5})
    if '热股榜' in result1:
        print("✓ get_hot_stocks_ranking 工具成功")
    else:
        print("✗ get_hot_stocks_ranking 工具失败")

    # 测试 analyze_profit_effect
    result2 = analyze_profit_effect.invoke({'source': 'sina_amount', 'top_n': 20})
    if '赚钱效应' in result2:
        print("✓ analyze_profit_effect 工具成功")
        # 提取等级信息
        if '等级:' in result2:
            grade = result2.split('等级: ')[1].split('\n')[0]
            print(f"\n  赚钱效应等级: {grade}")
    else:
        print("✗ analyze_profit_effect 工具失败")

except Exception as e:
    print(f"✗ Agent工具测试失败: {e}")

print("\n" + "=" * 60)
print("测试完成!")
print("=" * 60)
print("\n功能说明:")
print("  - 热股榜模块: hot_stocks_module.py")
print("  - Agent工具: get_hot_stocks_ranking, analyze_profit_effect")
print("  - 使用方法: 直接在Agent对话中提问即可")
print("\n示例问题:")
print("  '今天的热门股如何？'")
print("  '今天的赚钱效应怎么样？'")
print("  '市场现在适合操作吗？'")
