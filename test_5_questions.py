#!/usr/bin/env python3
"""
5个测试问题 - 验证轻量级工具完整功能
"""
import subprocess
import sys

test_questions = [
    ("今天接力情况", ["6连板", "津药药业", "2连板"]),
    ("今天情绪如何", ["情绪", "涨停", "最高板"]),
    ("今日涨停股", ["涨停股", "成交额"]),
    ("最高板是多少", ["6连板", "津药药业"]),
    ("2连板有哪些", ["2连板", "新能泰山", "光莆股份"]),
]

print("=" * 70)
print("🧪 自动化测试 - 5个问题")
print("=" * 70)
print()

all_passed = True
results = []

for idx, (question, expected_keywords) in enumerate(test_questions, 1):
    print(f"【测试 {idx}/5】{question}")
    print("-" * 70)

    try:
        # 运行查询
        result = subprocess.run(
            ['python3', 'simple_query.py', question],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            print(f"  ❌ 执行失败: {result.stderr}")
            all_passed = False
            results.append((question, False, "执行失败"))
            continue

        output = result.stdout

        # 检查关键词
        missing_keywords = []
        for keyword in expected_keywords:
            if keyword not in output:
                missing_keywords.append(keyword)

        if missing_keywords:
            print(f"  ⚠️  缺少关键词: {', '.join(missing_keywords)}")
            print(f"  输出前200字符: {output[:200]}...")
            all_passed = False
            results.append((question, False, f"缺少: {missing_keywords}"))
        else:
            print(f"  ✅ 通过 - 包含所有关键词")
            results.append((question, True, "通过"))

        # 显示响应摘要
        lines = output.strip().split('\n')
        if len(lines) > 5:
            print(f"  📝 响应摘要（前3行）:")
            for line in lines[:3]:
                if line.strip():
                    print(f"     {line.strip()[:60]}")

    except subprocess.TimeoutExpired:
        print(f"  ❌ 超时（>10秒）")
        all_passed = False
        results.append((question, False, "超时"))
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        all_passed = False
        results.append((question, False, str(e)))

    print()

# 总结
print("=" * 70)
print("📊 测试总结")
print("=" * 70)
print()

passed_count = sum(1 for _, passed, _ in results if passed)
print(f"通过率: {passed_count}/{len(test_questions)} ({passed_count/len(test_questions)*100:.0f}%)")
print()

for idx, (question, passed, note) in enumerate(results, 1):
    status = "✅" if passed else "❌"
    print(f"{status} {idx}. {question}: {note}")

print()

if all_passed:
    print("🎉 所有测试通过！系统可以交付使用")
    print()
    print("使用方法:")
    print("  python3 simple_query.py")
    print()
    sys.exit(0)
else:
    print("⚠️  部分测试失败，需要修复")
    sys.exit(1)
