"""
图片文字识别和分析模块
支持：
1. 识别图片中的文字（OCR）
2. 理解图片内容
3. 结合用户描述给出分析
"""
import os
import base64
from pathlib import Path
from typing import Dict, Any, Optional

from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.messages import HumanMessage


class ImageAnalyzer:
    """图片识别和分析器"""

    def __init__(self, api_key: str):
        self.api_key = api_key

        # 初始化视觉理解模型
        self.vision_llm = ChatTongyi(
            model_name="qwen-vl-plus",  # 通义千问视觉模型
            dashscope_api_key=api_key,
            streaming=False,
        )

        # 初始化文本模型用于深度分析
        self.text_llm = ChatTongyi(
            model_name="qwen-plus",
            dashscope_api_key=api_key,
            temperature=0.1,
            streaming=False,
        )

    def read_image_as_base64(self, image_path: str) -> str:
        """读取图片并转换为base64编码

        参数：
        - image_path: 图片路径

        返回：base64编码的图片数据
        """
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
                base64_image = base64.b64encode(image_data).decode('utf-8')
                return base64_image
        except Exception as e:
            raise Exception(f"读取图片失败: {str(e)}")

    def recognize_text_from_image(self, image_path: str) -> str:
        """从图片中识别文字（OCR）

        参数：
        - image_path: 图片路径（支持本地路径和URL）

        返回：识别出的文字内容
        """
        try:
            # 判断是本地文件还是URL
            if image_path.startswith('http://') or image_path.startswith('https://'):
                # URL格式
                image_url = image_path
            else:
                # 本地文件 - 检查文件是否存在
                if not Path(image_path).exists():
                    return f"❌ 图片文件不存在: {image_path}"

                # 对于通义千问，本地文件需要转换为URL或base64
                # 这里我们直接使用本地路径（通义千问支持）
                image_url = f"file://{os.path.abspath(image_path)}"

            # 构建视觉理解请求
            message = HumanMessage(
                content=[
                    {
                        "image": image_url
                    },
                    {
                        "text": "请识别这张图片中的所有文字内容，按原样输出，不要遗漏任何信息。"
                    }
                ]
            )

            # 调用视觉模型
            response = self.vision_llm.invoke([message])

            # 处理返回内容
            if isinstance(response.content, list):
                # 如果返回的是列表格式 [{'text': '...'}]
                recognized_text = response.content[0].get('text', str(response.content))
            else:
                recognized_text = response.content

            return recognized_text

        except Exception as e:
            error_msg = f"❌ 图片识别失败: {str(e)}"
            print(error_msg)
            return error_msg

    def analyze_image_with_description(
        self,
        image_path: str,
        user_description: str,
        knowledge_context: str = ""
    ) -> str:
        """分析图片内容并结合用户描述给出回答

        参数：
        - image_path: 图片路径
        - user_description: 用户对图片的描述或问题
        - knowledge_context: 可选的知识库上下文

        返回：综合分析结果
        """
        print(f"\n🔍 正在分析图片...")

        # 1. 识别图片中的文字
        recognized_text = self.recognize_text_from_image(image_path)

        if recognized_text.startswith("❌"):
            return recognized_text

        # 2. 使用视觉模型理解图片
        try:
            if image_path.startswith('http://') or image_path.startswith('https://'):
                image_url = image_path
            else:
                image_url = f"file://{os.path.abspath(image_path)}"

            vision_message = HumanMessage(
                content=[
                    {
                        "image": image_url
                    },
                    {
                        "text": f"这是一张关于股票交易的图片。\n\n用户描述：{user_description}\n\n请简要描述图片的主要内容和关键信息。"
                    }
                ]
            )

            vision_response = self.vision_llm.invoke([vision_message])

            # 处理返回内容
            if isinstance(vision_response.content, list):
                image_understanding = vision_response.content[0].get('text', str(vision_response.content))
            else:
                image_understanding = vision_response.content

        except Exception as e:
            image_understanding = "（图片理解失败，仅使用文字识别结果）"
            print(f"⚠️  图片理解失败: {str(e)}")

        # 3. 综合分析
        analysis_prompt = f"""你是一位专业的股票交易分析师。现在需要分析一张图片的内容。

【图片中的文字】
{recognized_text}

【图片内容理解】
{image_understanding}

【用户的问题/描述】
{user_description}

【知识库背景】
{knowledge_context if knowledge_context else "（无额外知识库内容）"}

请基于以上信息，直接给出简洁专业的分析和回答。

要求：
- 直接给出结论，不要展示分析思考过程
- 准确引用图片中的具体数据
- 回答要简洁明了，重点突出
- 给出可操作的建议
- 如果涉及风险，要明确指出
- 避免冗长的逐步推理，直接说重点
- 控制回答长度在300-500字以内
"""

        try:
            from langchain_core.prompts import ChatPromptTemplate

            prompt = ChatPromptTemplate.from_messages([
                ("system", "你是一位专业的股票交易分析师，擅长解读各种交易数据和图表。"),
                ("human", analysis_prompt)
            ])

            response = self.text_llm.invoke(prompt.format_messages())
            analysis = response.content

            return analysis

        except Exception as e:
            return f"❌ 分析失败: {str(e)}"

    def quick_ocr(self, image_path: str) -> Dict[str, str]:
        """快速OCR识别（仅提取文字）

        参数：
        - image_path: 图片路径

        返回：包含文字内容的字典
        """
        text = self.recognize_text_from_image(image_path)

        return {
            "image_path": image_path,
            "recognized_text": text,
            "char_count": len(text) if not text.startswith("❌") else 0
        }


def test_image_analyzer():
    """测试图片分析功能"""
    print("=" * 70)
    print("🖼️  图片识别与分析 - 测试")
    print("=" * 70)

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("\n⚠️  警告：未检测到 DASHSCOPE_API_KEY 环境变量")
        return

    analyzer = ImageAnalyzer(api_key=api_key)

    # 测试1：快速OCR
    print("\n【测试1】快速文字识别")
    print("请将要识别的图片路径输入：")
    image_path = input("图片路径: ").strip()

    if not image_path:
        print("未输入图片路径，使用默认测试")
        return

    result = analyzer.quick_ocr(image_path)
    print(f"\n识别结果：")
    print(f"文件: {result['image_path']}")
    print(f"字符数: {result['char_count']}")
    print(f"\n文字内容：")
    print("-" * 70)
    print(result['recognized_text'])
    print("-" * 70)

    # 测试2：综合分析
    print("\n【测试2】图片综合分析")
    print("请描述您的问题或需求：")
    description = input("描述: ").strip()

    if description:
        analysis = analyzer.analyze_image_with_description(
            image_path=image_path,
            user_description=description
        )

        print(f"\n分析结果：")
        print("=" * 70)
        print(analysis)
        print("=" * 70)


if __name__ == "__main__":
    test_image_analyzer()
