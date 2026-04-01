#!/bin/bash
# 启动agent_ui.py的脚本
# 确保使用最新的代码和正确的环境变量

echo "======================================================================"
echo "启动智能股票分析Agent Web UI"
echo "======================================================================"
echo ""

# 设置API KEY
export DASHSCOPE_API_KEY=sk-54458b944b704de582533e1aa7290fca

# 设置库路径（修复GLIBCXX依赖问题）
export LD_LIBRARY_PATH=/home/lixiang/anaconda3/lib:$LD_LIBRARY_PATH
echo "✅ 已设置库路径: $LD_LIBRARY_PATH"
echo ""

# 检查是否有旧进程在运行
OLD_PID=$(ps aux | grep "python.*agent_ui.py" | grep -v grep | awk '{print $2}')
if [ ! -z "$OLD_PID" ]; then
    echo "⚠️  检测到旧进程正在运行 (PID: $OLD_PID)"
    echo "正在终止旧进程..."
    kill -9 $OLD_PID
    sleep 2
    echo "✅ 旧进程已终止"
    echo ""
fi

echo "🚀 启动新的Agent UI进程..."
echo ""
python agent_ui.py
