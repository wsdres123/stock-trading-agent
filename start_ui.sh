#!/bin/bash
# 智能股票分析Agent Web UI启动脚本

# 设置库路径
export LD_LIBRARY_PATH=/home/lixiang/anaconda3/lib:$LD_LIBRARY_PATH

# 设置API Key
export DASHSCOPE_API_KEY='sk-54458b944b704de582533e1aa7290fca'

echo "========================================================================"
echo "           🚀 智能股票分析Agent - Web UI版本"
echo "========================================================================"
echo ""
echo "功能特点："
echo "  ✅ 对话交互 - 实时问答"
echo "  ✅ 图片分析 - 拖拽上传"
echo "  ✅ 实时数据 - 涨停股、连板、行情"
echo "  ✅ 知识库 - 21个交易文档"
echo ""
echo "========================================================================"
echo ""

# 检查Python
python_cmd="python3"
if ! command -v python3 &> /dev/null; then
    python_cmd="python"
fi

# 检查Gradio是否安装
echo "🔍 检查依赖..."
$python_cmd -c "import gradio" 2>/dev/null
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ 未安装Gradio，正在安装..."
    echo ""
    pip install gradio -i https://pypi.tuna.tsinghua.edu.cn/simple
    if [ $? -ne 0 ]; then
        echo ""
        echo "❌ Gradio安装失败"
        echo "请手动安装: pip install gradio"
        exit 1
    fi
fi

echo "✅ 依赖检查完成"
echo ""
echo "========================================================================"
echo "🌐 启动Web界面..."
echo "========================================================================"
echo ""
echo "启动后将自动打开浏览器，或访问："
echo "  本地: http://127.0.0.1:7860"
echo "  局域网: http://你的IP:7860"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""
echo "========================================================================"
echo ""

# 启动UI（Python代码会自动打开浏览器）
$python_cmd agent_ui.py
