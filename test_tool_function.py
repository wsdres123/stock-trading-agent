#!/usr/bin/env python3
"""
快速测试 get_continuous_limit_up_leaders 工具函数
验证是否返回正确的连板数据
"""
import sys
import os

# 设置环境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入函数
from test_agent_knowledge import analyze_continuous_limit_up

print("=" * 70)
print("测试 analyze_continuous_limit_up 函数")
print("=" * 70)
print()

try:
    print("正在调用 analyze_continuous_limit_up()...")
    result = analyze_continuous_limit_up()

    print("\n" + "=" * 70)
    print("返回结果:")
    print("=" * 70)
    print(result)
    print("=" * 70)
    print()

    # 验证关键词
    checks = [
        ("包含6连板", "6连板" in result),
        ("包含津药药业", "津药药业" in result),
        ("包含2连板", "2连板" in result),
        ("不包含错误的'最高1板'", "最高板=1板" not in result and "最高1板" not in result),
    ]

    print("数据验证:")
    all_passed = True
    for check_name, passed in checks:
        status = "✅" if passed else "❌"
        print(f"  {status} {check_name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("🎉 测试通过！函数返回正确数据")
        sys.exit(0)
    else:
        print("⚠️  测试失败，数据仍然不正确")
        sys.exit(1)

except Exception as e:
    print(f"\n❌ 错误: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
