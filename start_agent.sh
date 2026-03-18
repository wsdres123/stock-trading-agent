#!/bin/bash

# 智能股票分析Agent启动脚本

echo "========================================================================"
echo "🚀 智能股票分析Agent - 完整版"
echo "========================================================================"

# 检查API Key
if [ -z "$DASHSCOPE_API_KEY" ]; then
    echo ""
    echo "❌ 错误：未设置 DASHSCOPE_API_KEY 环境变量"
    echo ""
    echo "请先设置API Key："
    echo "  export DASHSCOPE_API_KEY='your-api-key'"
    echo ""
    echo "获取API Key："
    echo "  https://dashscope.console.aliyun.com/"
    echo ""
    exit 1
fi

echo ""
echo "✅ API Key已设置"
echo ""

# 检查Python版本
python_cmd="python3"
if ! command -v python3 &> /dev/null; then
    python_cmd="python"
fi

echo "使用Python: $python_cmd"
echo ""

# 运行系统
exec $python_cmd test_agent_with_image.py
