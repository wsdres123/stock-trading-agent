#!/bin/bash

# 快速启动指南

echo "============================================================"
echo "🚀 智能股票分析Agent - 快速启动"
echo "============================================================"
echo ""

# 步骤1：检查API Key
echo "【步骤1】检查API Key"
if [ -z "$DASHSCOPE_API_KEY" ]; then
    echo "❌ 未设置 DASHSCOPE_API_KEY"
    echo ""
    echo "请执行以下命令设置API Key："
    echo ""
    echo "  export DASHSCOPE_API_KEY='your-api-key'"
    echo ""
    echo "获取API Key："
    echo "  https://dashscope.console.aliyun.com/"
    echo ""
    exit 1
else
    echo "✅ API Key已设置"
fi

echo ""

# 步骤2：运行系统测试
echo "【步骤2】运行系统测试"
echo ""
python3 test_system.py

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ 系统测试未完全通过"
    echo "请检查上述错误信息"
    echo ""
    exit 1
fi

echo ""
echo "============================================================"
echo "✅ 系统测试通过！"
echo "============================================================"
echo ""
echo "现在可以启动Agent："
echo ""
echo "  ./start_agent.sh"
echo ""
echo "或直接运行："
echo ""
echo "  python3 test_agent_with_image.py"
echo ""
