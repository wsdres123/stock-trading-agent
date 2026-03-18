#!/bin/bash
# 测试连板梯队功能

export LD_LIBRARY_PATH=/home/lixiang/anaconda3/lib:$LD_LIBRARY_PATH
export DASHSCOPE_API_KEY='sk-54458b944b704de582533e1aa7290fca'

python3 << 'EOF'
import os
import sys
from test_agent_knowledge import analyze_continuous_limit_up

print("=" * 70)
print("测试连板梯队功能（查询所有非ST涨停股）")
print("=" * 70)
print()

try:
    result = analyze_continuous_limit_up()
    print()
    print(result)
    print()
    print("=" * 70)
    print("✅ 测试完成！")
    print("=" * 70)

except Exception as e:
    print(f"❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF
