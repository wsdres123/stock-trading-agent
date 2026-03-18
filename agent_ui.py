"""
智能股票分析Agent - Web UI版本
支持：
1. 文字对话交互
2. 图片拖拽上传分析
3. 实时数据查询
4. 知识库问答
"""
import os
import gradio as gr
from typing import List, Tuple, Optional
import base64
from pathlib import Path

# 设置API Key
os.environ['DASHSCOPE_API_KEY'] = os.environ.get('DASHSCOPE_API_KEY', 'sk-54458b944b704de582533e1aa7290fca')

# 导入必需模块
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferWindowMemory

# 导入功能模块
from image_analyzer import ImageAnalyzer
from trading_loss_rag import TradingLossRAG
from test_agent_knowledge import (
    fetch_sina_stock_data,
    fetch_limit_up_stocks,
    analyze_continuous_limit_up,
    patched_subtract_client_response,
)

# 应用补丁
ChatTongyi.subtract_client_response = patched_subtract_client_response

# 全局变量
AGENT_EXECUTOR = None
IMAGE_ANALYZER = None
TRADING_RAG = None
MEMORY = None


def initialize_agent():
    """初始化Agent系统"""
    global AGENT_EXECUTOR, IMAGE_ANALYZER, TRADING_RAG, MEMORY

    if AGENT_EXECUTOR is not None:
        return True

    try:
        api_key = os.environ.get('DASHSCOPE_API_KEY')

        print("🚀 初始化Agent系统...")

        # 初始化知识库
        print("📚 加载知识库...")
        TRADING_RAG = TradingLossRAG(api_key=api_key, folder_path="./ku")
        if not TRADING_RAG.build_enhanced_index():
            print("⚠️ 知识库加载失败，但系统将继续运行")

        # 初始化图片分析器
        print("📸 初始化图片分析器...")
        IMAGE_ANALYZER = ImageAnalyzer(api_key=api_key)

        # 定义工具
        @tool
        def search_trading_knowledge(query: str) -> str:
            """从交易知识库中搜索相关信息。适用于：交易策略、市场情绪、打板战法、龙头股特征等知识性问题"""
            if TRADING_RAG is None:
                return "知识库未加载"
            return TRADING_RAG.search_with_reasoning(query)

        @tool
        def get_limit_up_stocks() -> str:
            """获取今日涨停股票列表，包括涨停原因、封单金额等信息"""
            return fetch_limit_up_stocks()

        @tool
        def get_stock_info(stock_code: str) -> str:
            """获取指定股票的实时行情数据，参数为股票代码（如'sh600000'或'sz000001'）"""
            return fetch_sina_stock_data(stock_code)

        @tool
        def analyze_continuous_boards() -> str:
            """分析连板股票梯队情况，包括各个高度的连板股数量和代表股票"""
            return analyze_continuous_limit_up()

        @tool
        def analyze_image(image_path: str, question: str) -> str:
            """分析图片内容并回答问题。用于分析截图、图表、K线图等"""
            if IMAGE_ANALYZER is None:
                return "图片分析器未初始化"
            return IMAGE_ANALYZER.analyze_image_with_description(image_path, question, "")

        # 创建工具列表
        tools = [
            search_trading_knowledge,
            get_limit_up_stocks,
            get_stock_info,
            analyze_continuous_boards,
            analyze_image,
        ]

        # 初始化LLM
        print("🤖 初始化语言模型...")
        llm = ChatTongyi(
            model_name="qwen-plus",
            dashscope_api_key=api_key,
            temperature=0.3,
            streaming=False,
        )

        # 创建提示模板
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一位专业的股票交易分析师助手，精通短线交易策略和市场分析。

核心能力：
1. 📊 实时数据分析 - 涨停股、连板梯队、个股行情
2. 📚 知识库查询 - 交易策略、打板战法、市场情绪判断
3. 📸 图片分析 - 识别和分析交易截图、K线图、复盘笔记
4. 💡 专业建议 - 结合知识库给出操作建议和风险提示

工作原则：
- 回答简洁专业，直接给出结论
- 准确引用数据和知识库内容
- 涉及风险时明确警示
- 不展示冗长的思考过程

可用工具：
- search_trading_knowledge: 搜索交易知识（策略、情绪、战法等）
- get_limit_up_stocks: 获取今日涨停股
- get_stock_info: 查询个股行情
- analyze_continuous_boards: 分析连板梯队
- analyze_image: 分析图片内容

请根据用户问题选择合适的工具并给出专业回答。"""),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        # 创建Agent
        agent = create_tool_calling_agent(llm, tools, prompt)

        # 创建记忆
        MEMORY = ConversationBufferWindowMemory(
            memory_key="chat_history",
            return_messages=True,
            k=5
        )

        # 创建执行器
        AGENT_EXECUTOR = AgentExecutor(
            agent=agent,
            tools=tools,
            memory=MEMORY,
            verbose=False,
            handle_parsing_errors=True,
            max_iterations=5,
        )

        print("✅ Agent系统初始化完成")
        return True

    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def process_message(message: str, history: List[Tuple[str, str]], image_path: Optional[str] = None) -> Tuple[List[Tuple], str]:
    """处理用户消息

    参数：
    - message: 用户消息
    - history: 对话历史
    - image_path: 图片路径（如果上传了图片）

    返回：
    - 更新后的对话历史
    - 清空的输入框
    """
    if not message and not image_path:
        return history, ""

    # 确保Agent已初始化
    if AGENT_EXECUTOR is None:
        if not initialize_agent():
            return history + [(message or "上传了图片", "❌ 系统初始化失败，请检查配置")], ""

    try:
        # 构建用户输入
        if image_path:
            # 有图片：分析图片
            user_input = f"请分析这张图片"
            if message:
                user_input = f"{message}"

            # 显示图片在对话中
            user_message = message if message else "上传了一张图片"
            history.append((user_message, None))

            # 调用图片分析
            response = IMAGE_ANALYZER.analyze_image_with_description(
                image_path=image_path,
                user_description=user_input,
                knowledge_context=""
            )
        else:
            # 纯文字对话
            history.append((message, None))
            result = AGENT_EXECUTOR.invoke({"input": message})
            response = result.get("output", "抱歉，没有获取到回答")

        # 更新历史
        history[-1] = (history[-1][0], response)

    except Exception as e:
        error_msg = f"❌ 处理失败: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        history[-1] = (history[-1][0], error_msg)

    return history, ""


def create_ui():
    """创建Gradio UI界面"""

    # 自定义股票交易风格主题
    custom_theme = gr.themes.Monochrome(
        primary_hue="slate",
        neutral_hue="slate",
        font=gr.themes.GoogleFont("Inter"),
    ).set(
        body_background_fill="#0a0a0a",
        body_background_fill_dark="#0a0a0a",
        button_primary_background_fill="#2563eb",
        button_primary_background_fill_hover="#1e40af",
        button_primary_text_color="white",
        block_label_text_color="#e5e7eb",
        block_title_text_color="#f3f4f6",
        input_background_fill="#ffffff",
        input_background_fill_dark="#ffffff",
    )

    with gr.Blocks(
        title="智能股票分析系统",
        theme=custom_theme,
        css="""
        .gradio-container {
            max-width: 1400px !important;
            font-family: 'Inter', sans-serif;
        }

        /* 顶部标题栏 */
        .header-box {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            padding: 1.5rem;
            border-radius: 8px;
            border-left: 4px solid #2563eb;
            margin-bottom: 1.5rem;
        }

        /* 状态指示器 */
        .status-indicator {
            display: inline-block;
            width: 8px;
            height: 8px;
            background: #10b981;
            border-radius: 50%;
            margin-right: 6px;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        /* 快捷按钮 */
        .quick-btn {
            background: #1f2937;
            border: 1px solid #374151;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            margin: 0.25rem;
            cursor: pointer;
            transition: all 0.3s;
        }

        .quick-btn:hover {
            background: #374151;
            border-color: #2563eb;
        }

        /* 聊天框样式 */
        .message {
            border-radius: 8px;
            padding: 1rem;
        }

        /* 按钮组 */
        .button-row {
            gap: 0.5rem;
        }

        /* 图片上传区域优化 */
        .image-upload-area {
            border: 2px dashed #2563eb !important;
            border-radius: 8px !important;
            background: #1f2937 !important;
            padding: 1rem !important;
            transition: all 0.3s ease !important;
            min-height: 120px !important;
        }

        .image-upload-area:hover {
            border-color: #3b82f6 !important;
            background: #374151 !important;
        }

        /* 自定义图片上传样式 */
        [data-testid="image"] {
            border: 2px dashed #2563eb !important;
            border-radius: 8px !important;
            background: rgba(37, 99, 235, 0.05) !important;
            transition: all 0.3s ease !important;
            min-height: 120px !important;
        }

        [data-testid="image"]:hover {
            border-color: #3b82f6 !important;
            background: rgba(59, 130, 246, 0.15) !important;
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
        }

        /* 图片上传提示文字样式 */
        [data-testid="image"] .wrap {
            background: transparent !important;
        }

        [data-testid="image"] label {
            color: #3b82f6 !important;
            font-weight: 600 !important;
            font-size: 0.95rem !important;
        }

        /* 拖拽时高亮 */
        [data-testid="image"].dragging {
            border-color: #10b981 !important;
            background: rgba(16, 185, 129, 0.1) !important;
        }

        /* 输入框样式优化 */
        textarea, input[type="text"] {
            background-color: #ffffff !important;
            color: #1f2937 !important;
        }

        textarea::placeholder, input::placeholder {
            color: #9ca3af !important;
            opacity: 1;
        }

        /* 聊天框消息样式 */
        .user-message {
            background: #2563eb !important;
            color: white !important;
        }
        """
    ) as demo:

        # 顶部标题
        with gr.Group():
            gr.HTML("""
            <div class="header-box">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h1 style="margin: 0; color: #f3f4f6; font-size: 1.5rem; font-weight: 600;">
                            📈 智能股票分析系统
                        </h1>
                        <p style="margin: 0.5rem 0 0 0; color: #9ca3af; font-size: 0.875rem;">
                            实时数据 · 智能分析 · 图片识别 · 知识问答
                        </p>
                    </div>
                    <div style="text-align: right;">
                        <div style="color: #10b981; font-size: 0.875rem; font-weight: 500;">
                            <span class="status-indicator"></span>系统在线
                        </div>
                        <div style="color: #6b7280; font-size: 0.75rem; margin-top: 0.25rem;">
                            知识库已加载 · 图片识别就绪
                        </div>
                    </div>
                </div>
            </div>
            """)

        with gr.Row():
            # 主对话区
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    label="",
                    height=550,
                    show_copy_button=True,
                    avatar_images=(None, "🤖"),
                    bubble_full_width=False,
                )

                # 输入区域
                msg = gr.Textbox(
                    label="",
                    placeholder="💬 输入您的问题...",
                    lines=1,
                    max_lines=3,
                )

                # 图片上传区域 - 单独一行更显眼
                with gr.Row():
                    image_input = gr.Image(
                        label="📸 图片上传（支持拖拽）",
                        type="filepath",
                        sources=["upload", "clipboard"],
                        height=120,
                        elem_classes="image-upload-area",
                    )

                with gr.Row(elem_classes="button-row"):
                    send_btn = gr.Button("📤 发送", variant="primary", scale=2, size="lg")
                    clear_btn = gr.Button("🗑️ 清空", variant="secondary", scale=1, size="lg")

            # 右侧功能区
            with gr.Column(scale=1):
                gr.Markdown("""
                ### 快速查询
                """)

                with gr.Group():
                    quick_q1 = gr.Button("📊 今日涨停", size="sm")
                    quick_q2 = gr.Button("🔥 连板梯队", size="sm")
                    quick_q3 = gr.Button("💹 市场情绪", size="sm")
                    quick_q4 = gr.Button("📉 回撤分析", size="sm")

                gr.Markdown("""
                ---
                ### 知识库
                """)

                gr.Markdown("""
                <div style="font-size: 0.875rem; color: #9ca3af;">
                • 打板战法<br>
                • 情绪周期<br>
                • 龙头特征<br>
                • 风控原则
                </div>
                """)

                gr.Markdown("""
                ---
                ### 使用说明
                """)

                gr.Markdown("""
                <div style="font-size: 0.875rem; color: #9ca3af;">
                <b>💬 文字查询</b><br>
                在输入框输入问题<br><br>

                <b>📸 图片分析</b><br>
                • 拖拽图片到上传区域<br>
                • 点击上传区域选择文件<br>
                • 粘贴剪贴板图片<br><br>

                <b>🔄 组合查询</b><br>
                上传图片 + 输入问题
                </div>
                """)

        # 事件绑定
        def submit_message(message, history, image):
            return process_message(message, history, image)

        def clear_chat():
            global MEMORY
            if MEMORY:
                MEMORY.clear()
            return [], None, ""

        def quick_query(query_text):
            def inner(history):
                return history + [(query_text, None)], query_text
            return inner

        # 发送按钮
        send_btn.click(
            fn=lambda msg, history, image: (process_message(msg, history, image)[0], "", None),
            inputs=[msg, chatbot, image_input],
            outputs=[chatbot, msg, image_input],
        )

        # 回车发送
        msg.submit(
            fn=lambda msg, history, image: (process_message(msg, history, image)[0], "", None),
            inputs=[msg, chatbot, image_input],
            outputs=[chatbot, msg, image_input],
        )

        # 清空对话
        clear_btn.click(
            fn=clear_chat,
            inputs=None,
            outputs=[chatbot, image_input, msg],
        )

        # 快捷按钮
        quick_q1.click(
            fn=lambda h: (h + [("今天涨停股有哪些？", None)], "今天涨停股有哪些？"),
            inputs=[chatbot],
            outputs=[chatbot, msg],
        ).then(
            fn=submit_message,
            inputs=[msg, chatbot, image_input],
            outputs=[chatbot, msg],
        )

        quick_q2.click(
            fn=lambda h: (h + [("连板梯队情况如何？", None)], "连板梯队情况如何？"),
            inputs=[chatbot],
            outputs=[chatbot, msg],
        ).then(
            fn=submit_message,
            inputs=[msg, chatbot, image_input],
            outputs=[chatbot, msg],
        )

        quick_q3.click(
            fn=lambda h: (h + [("当前市场情绪如何？", None)], "当前市场情绪如何？"),
            inputs=[chatbot],
            outputs=[chatbot, msg],
        ).then(
            fn=submit_message,
            inputs=[msg, chatbot, image_input],
            outputs=[chatbot, msg],
        )

        quick_q4.click(
            fn=lambda h: (h + [("为什么会大幅回撤？", None)], "为什么会大幅回撤？"),
            inputs=[chatbot],
            outputs=[chatbot, msg],
        ).then(
            fn=submit_message,
            inputs=[msg, chatbot, image_input],
            outputs=[chatbot, msg],
        )

    return demo


if __name__ == "__main__":
    print("=" * 70)
    print("🚀 启动智能股票分析Agent Web UI")
    print("=" * 70)
    print()

    # 初始化Agent
    print("正在初始化系统...")
    if not initialize_agent():
        print("❌ 系统初始化失败")
        exit(1)

    print()
    print("✅ 系统初始化完成")
    print()
    print("=" * 70)
    print("🌐 启动Web界面...")
    print("=" * 70)
    print()

    # 创建并启动UI
    demo = create_ui()

    # 导入必要的模块用于打开浏览器
    import subprocess
    import threading

    # 定义延迟打开浏览器的函数
    def open_browser():
        import time
        import os
        print("⏱️  等待3秒后自动打开浏览器...")
        time.sleep(3)  # 等待3秒让Gradio完全启动
        print("🌐 正在打开浏览器...")
        try:
            url = 'http://127.0.0.1:7860'

            # 保存原始的LD_LIBRARY_PATH
            original_ld_path = os.environ.get('LD_LIBRARY_PATH', '')

            # 临时清除LD_LIBRARY_PATH，避免anaconda库冲突
            if 'LD_LIBRARY_PATH' in os.environ:
                del os.environ['LD_LIBRARY_PATH']

            print(f"📍 DISPLAY环境变量: {os.environ.get('DISPLAY', '未设置')}")

            # 使用os.system打开浏览器
            result = os.system(f'xdg-open {url} >/dev/null 2>&1 &')

            # 恢复LD_LIBRARY_PATH
            if original_ld_path:
                os.environ['LD_LIBRARY_PATH'] = original_ld_path

            if result == 0:
                print("✅ 浏览器已打开！")
            else:
                print("⚠️  无法自动打开浏览器，请手动访问: http://127.0.0.1:7860")
        except Exception as e:
            print(f"❌ 打开浏览器时出错: {e}")
            print("请手动访问: http://127.0.0.1:7860")

    # 在单独的线程中打开浏览器
    print("🚀 启动浏览器打开任务...")
    threading.Thread(target=open_browser, daemon=True).start()

    demo.launch(
        server_name="0.0.0.0",  # 允许局域网访问
        server_port=7860,
        share=False,  # 设置为True可生成公网链接
        show_error=True,
        inbrowser=False,  # 不使用Gradio自带的，用我们自己的方法
    )
