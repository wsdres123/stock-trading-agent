#!/bin/bash
# 快速验证情绪分析修复

echo "======================================================================"
echo "快速验证情绪分析修复"
echo "======================================================================"
echo ""

# 设置环境
export DASHSCOPE_API_KEY=sk-54458b944b704de582533e1aa7290fca
export LD_LIBRARY_PATH=/home/lixiang/anaconda3/lib:$LD_LIBRARY_PATH

echo "[1/2] 检查代码修复..."
if grep -q "_analyze_market_sentiment_impl()" /home/lixiang/langchain/stock-trading-agent/test_agent_knowledge.py; then
    echo "✅ 代码已修复：_analyze_market_sentiment_impl() 调用已更新"
else
    echo "❌ 代码未修复：请检查test_agent_knowledge.py"
    exit 1
fi

echo ""
echo "[2/2] 测试pandas导入..."
python3 -c "import pandas; print('✅ pandas导入成功')" 2>/dev/null || echo "❌ pandas导入失败"

echo ""
echo "======================================================================"
echo "✅ 验证完成"
echo "======================================================================"
echo ""
echo "现在可以启动agent_ui.py进行完整测试："
echo "  ./start_agent.sh"
echo ""
echo "在浏览器中输入：今天情绪如何"
echo "======================================================================"
