#!/usr/bin/env python3
"""
最终验证脚本 - 确认所有修复已生效
"""
import os
import sys

print("=" * 70)
print("🔍 最终验证 - 接力数据修复")
print("=" * 70)
print()

all_passed = True

# ========== 测试1: 数据文件存在性 ==========
print("【测试1】数据文件完整性")
print("-" * 70)

from datetime import datetime
today = datetime.now().strftime('%Y%m%d')

files_to_check = [
    (f'./data/limit_up_history/{today}.json', '今日涨停股原始数据'),
    (f'./data/limit_up_history/{today}_board_cache.json', '今日连板梯队缓存'),
    ('./show_board_direct.py', '直接数据脚本'),
    ('./test_agent_knowledge.py', 'Agent主程序'),
    ('./generate_board_ladder.py', '数据生成脚本'),
]

for file_path, desc in files_to_check:
    if os.path.exists(file_path):
        print(f"  ✅ {desc}: {file_path}")
    else:
        print(f"  ❌ {desc}缺失: {file_path}")
        all_passed = False

print()

# ========== 测试2: 数据准确性 ==========
print("【测试2】数据准确性验证")
print("-" * 70)

import json

cache_file = f'./data/limit_up_history/{today}_board_cache.json'

if os.path.exists(cache_file):
    with open(cache_file, 'r', encoding='utf-8') as f:
        cache_data = json.load(f)

    summary = cache_data.get('summary', '')

    checks = [
        ("包含6连板", "6连板" in summary),
        ("包含津药药业", "津药药业" in summary),
        ("包含2连板", "2连板" in summary),
        ("不包含中化岩土", "中化岩土" not in summary),
        ("不包含虚假4连板", "【4连板】" not in summary),
    ]

    for check_name, result in checks:
        status = "✅" if result else "❌"
        print(f"  {status} {check_name}")
        if not result:
            all_passed = False
else:
    print("  ❌ 缓存文件不存在")
    all_passed = False

print()

# ========== 测试3: 直接数据脚本 ==========
print("【测试3】直接数据脚本功能")
print("-" * 70)

import subprocess

try:
    result = subprocess.run(
        ['python3', 'show_board_direct.py'],
        capture_output=True,
        text=True,
        timeout=5
    )

    if result.returncode == 0:
        output = result.stdout
        if '津药药业' in output and '6连板' in output:
            print("  ✅ 脚本运行成功，数据正确")
        else:
            print("  ⚠️  脚本运行但数据异常")
            all_passed = False
    else:
        print(f"  ❌ 脚本运行失败: {result.stderr}")
        all_passed = False
except Exception as e:
    print(f"  ❌ 测试失败: {e}")
    all_passed = False

print()

# ========== 测试4: 重试机制代码检查 ==========
print("【测试4】重试机制代码验证")
print("-" * 70)

with open('./test_agent_knowledge.py', 'r', encoding='utf-8') as f:
    agent_code = f.read()

retry_checks = [
    ("包含重建Agent逻辑", "build_chat_agent()" in agent_code and "current_agent = build_chat_agent()" in agent_code),
    ("包含Fallback方案", "使用备用方案直接获取数据" in agent_code),
    ("包含延迟机制", "time.sleep" in agent_code),
    ("包含重试计数", "max_retries" in agent_code and "for attempt in range" in agent_code),
]

for check_name, result in retry_checks:
    status = "✅" if result else "❌"
    print(f"  {status} {check_name}")
    if not result:
        all_passed = False

print()

# ========== 测试5: LLM配置检查 ==========
print("【测试5】LLM配置验证（streaming禁用）")
print("-" * 70)

llm_checks = [
    ("streaming=False", "streaming=False" in agent_code),
    ("incremental_output=False", "incremental_output=False" in agent_code),
    ("model_kwargs stream禁用", '"stream": False' in agent_code or "'stream': False" in agent_code),
]

for check_name, result in llm_checks:
    status = "✅" if result else "❌"
    print(f"  {status} {check_name}")
    if not result:
        all_passed = False

print()

# ========== 最终总结 ==========
print("=" * 70)
print("📊 验证总结")
print("=" * 70)
print()

if all_passed:
    print("🎉 所有测试通过！")
    print()
    print("✅ 数据准确性: 已验证")
    print("✅ 直接数据脚本: 可用")
    print("✅ 自动重试机制: 已实现")
    print("✅ Fallback方案: 已集成")
    print("✅ Streaming禁用: 已配置")
    print()
    print("🚀 推荐使用方法:")
    print()
    print("   【方案1 - 最稳定】直接查看数据（无streaming bug）")
    print("   $ python3 show_board_direct.py")
    print()
    print("   【方案2 - AI分析】使用Agent（自动重试+fallback）")
    print("   $ python test_agent_knowledge.py")
    print("   > 今天接力情况")
    print()
    print("   如果Agent卡住超过10秒，按Ctrl+C退出，使用方案1")
    print()
else:
    print("⚠️  部分测试未通过，请检查上述失败项")
    print()

print("=" * 70)
print()

sys.exit(0 if all_passed else 1)
