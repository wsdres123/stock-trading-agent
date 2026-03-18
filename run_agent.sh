#!/bin/bash
# 智能股票分析Agent启动脚本

# 设置库路径，使用anaconda的libstdc++
export LD_LIBRARY_PATH=/home/lixiang/anaconda3/lib:$LD_LIBRARY_PATH

# 设置API密钥（已配置）
export DASHSCOPE_API_KEY='sk-54458b944b704de582533e1aa7290fca'

# 显示菜单
show_menu() {
    clear
    echo "========================================================================"
    echo "                    🚀 智能股票分析Agent - 功能菜单"
    echo "========================================================================"
    echo ""
    echo "请选择功能："
    echo ""
    echo "  1. 🌐 Web UI界面 - 拖拽图片、对话交互（推荐） ⭐"
    echo "  2. 💬 命令行对话 - 涨停股查询、知识问答、实时数据"
    echo "  3. 📸 图片识别 - 快速图片文字识别和分析"
    echo "  4. 🧪 系统测试 - 检查系统状态和功能"
    echo "  5. ❌ 退出"
    echo ""
    echo "========================================================================"
    echo ""
}

# Web UI界面
run_web_ui() {
    clear
    echo "========================================================================"
    echo "🌐 启动Web UI界面"
    echo "========================================================================"
    echo ""
    echo "功能说明："
    echo "  ✅ 可视化聊天界面"
    echo "  ✅ 拖拽上传图片 - 无需输入路径"
    echo "  ✅ 实时对话交互"
    echo "  ✅ 所有功能集成（涨停股、知识库、图片分析）"
    echo ""
    echo "使用方法："
    echo "  1. 启动后会在浏览器中自动打开"
    echo "  2. 在输入框输入问题"
    echo "  3. 直接拖拽图片到图片区域"
    echo "  4. 点击发送按钮"
    echo ""
    echo "访问地址："
    echo "  本地: http://127.0.0.1:7860"
    echo "  局域网: http://你的IP:7860"
    echo ""
    echo "========================================================================"
    echo ""
    echo "正在启动..."
    echo ""

    # 检查Gradio
    python3 -c "import gradio" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "⚠️  未安装Gradio，正在安装..."
        pip install gradio -q
        if [ $? -ne 0 ]; then
            echo "❌ Gradio安装失败"
            echo "请手动安装: pip install gradio"
            echo ""
            read -p "按回车键返回菜单..."
            return
        fi
    fi

    # 启动UI（Python代码会自动打开浏览器）
    python3 agent_ui.py
}

# 完整版Agent（命令行）
run_complete_agent() {
    clear
    echo "========================================================================"
    echo "🚀 启动命令行对话Agent"
    echo "========================================================================"
    echo ""
    echo "功能说明："
    echo "  ✅ 涨停股查询 - 实时涨停数据"
    echo "  ✅ 知识库问答 - 交易策略、市场情绪、风控原则"
    echo "  ✅ 连板梯队分析"
    echo "  ✅ 个股行情查询"
    echo ""
    echo "使用示例："
    echo "  💬 今天涨停股有哪些？"
    echo "  💬 如何判断市场情绪周期？"
    echo "  💬 为什么会大幅回撤？"
    echo ""
    echo "========================================================================"
    echo ""
    python3 test_agent_knowledge.py
}

# 图片识别功能
run_image_recognition() {
    clear
    echo "========================================================================"
    echo "📸 图片识别功能"
    echo "========================================================================"
    echo ""
    echo "功能说明："
    echo "  ✅ OCR文字识别 - 提取图片中的所有文字"
    echo "  ✅ 图片内容理解 - 理解图表、K线、涨停板等"
    echo "  ✅ 知识库结合分析 - 结合交易知识给出专业分析"
    echo ""
    echo "支持格式：.png, .jpg, .jpeg, .bmp, .gif"
    echo ""
    echo "========================================================================"
    echo ""
    echo "请输入图片路径（支持相对路径和绝对路径）："
    echo "  示例1: ~/Desktop/screenshot.png"
    echo "  示例2: ./涨停板.jpg"
    echo "  示例3: /home/user/chart.png"
    echo ""
    read -p "图片路径: " image_path

    if [ -z "$image_path" ]; then
        echo ""
        echo "❌ 错误：未输入图片路径"
        echo ""
        read -p "按回车键返回菜单..."
        return
    fi

    # 展开波浪号
    image_path="${image_path/#\~/$HOME}"

    # 检查文件是否存在
    if [ ! -f "$image_path" ]; then
        echo ""
        echo "❌ 错误：文件不存在 - $image_path"
        echo ""
        read -p "按回车键返回菜单..."
        return
    fi

    echo ""
    read -p "请输入您的问题或描述（可选，直接回车则只识别文字）: " question

    # 调用Python脚本
    python3 -c "
from image_analyzer import ImageAnalyzer
import sys

try:
    analyzer = ImageAnalyzer(api_key='$DASHSCOPE_API_KEY')
    image_path = '$image_path'
    question = '''$question'''

    if not question.strip():
        # 只识别文字
        print()
        print('📝 识别结果：')
        print('='*70)
        result = analyzer.recognize_text_from_image(image_path)
        print(result)
        print('='*70)
    else:
        # 深度分析
        result = analyzer.analyze_image_with_description(image_path, question, '')
        print()
        print('🔍 分析结果：')
        print('='*70)
        print(result)
        print('='*70)
except Exception as e:
    print()
    print(f'❌ 错误: {e}')
    sys.exit(1)
"

    echo ""
    read -p "按回车键返回菜单..."
}

# 系统测试
run_system_test() {
    clear
    echo "========================================================================"
    echo "🧪 系统测试"
    echo "========================================================================"
    echo ""
    python3 test_system.py
    echo ""
    echo "========================================================================"
    echo ""
    read -p "按回车键返回菜单..."
}

# 主循环
while true; do
    show_menu
    read -p "请输入选项 [1-5]: " choice

    case $choice in
        1)
            run_web_ui
            ;;
        2)
            run_complete_agent
            ;;
        3)
            run_image_recognition
            ;;
        4)
            run_system_test
            ;;
        5)
            clear
            echo ""
            echo "感谢使用智能股票分析Agent！📈"
            echo ""
            exit 0
            ;;
        *)
            echo ""
            echo "❌ 无效选项，请输入 1-5"
            sleep 2
            ;;
    esac
done
