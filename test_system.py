#!/usr/bin/env python3
"""
测试脚本 - 验证系统基本功能
"""
import os
import sys

def test_imports():
    """测试模块导入"""
    print("=" * 70)
    print("【步骤1】测试模块导入")
    print("=" * 70)

    try:
        from enhanced_rag import EnhancedRAG
        print("✅ enhanced_rag.py 导入成功")
    except Exception as e:
        print(f"❌ enhanced_rag.py 导入失败: {e}")
        return False

    try:
        from trading_loss_rag import TradingLossRAG
        print("✅ trading_loss_rag.py 导入成功")
    except Exception as e:
        print(f"❌ trading_loss_rag.py 导入失败: {e}")
        return False

    try:
        from image_analyzer import ImageAnalyzer
        print("✅ image_analyzer.py 导入成功")
    except Exception as e:
        print(f"❌ image_analyzer.py 导入失败: {e}")
        return False

    try:
        from test_agent_with_image import initialize_systems, build_agent_with_image
        print("✅ test_agent_with_image.py 导入成功")
    except Exception as e:
        print(f"❌ test_agent_with_image.py 导入失败: {e}")
        return False

    return True


def test_api_key():
    """测试API Key"""
    print("\n" + "=" * 70)
    print("【步骤2】检查API Key")
    print("=" * 70)

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("❌ 未设置 DASHSCOPE_API_KEY 环境变量")
        print("\n请执行：")
        print("  export DASHSCOPE_API_KEY='your-api-key'")
        return False

    print(f"✅ DASHSCOPE_API_KEY 已设置 (长度: {len(api_key)})")
    return True


def test_knowledge_folder():
    """测试知识库文件夹"""
    print("\n" + "=" * 70)
    print("【步骤3】检查知识库文件夹")
    print("=" * 70)

    from pathlib import Path

    ku_dir = Path("./ku")
    if not ku_dir.exists():
        print("❌ ku/ 文件夹不存在")
        return False

    print("✅ ku/ 文件夹存在")

    # 统计文件
    txt_files = list(ku_dir.glob("*.txt"))
    docx_files = list(ku_dir.glob("*.docx"))

    print(f"  - .txt 文件: {len(txt_files)}个")
    print(f"  - .docx 文件: {len(docx_files)}个")

    if len(txt_files) + len(docx_files) == 0:
        print("⚠️  警告：ku/ 文件夹中没有知识文档")
        return False

    # 显示前几个文件
    all_files = txt_files + docx_files
    print("\n  前5个文件：")
    for f in all_files[:5]:
        print(f"    - {f.name}")

    return True


def test_basic_functionality():
    """测试基本功能（不需要API）"""
    print("\n" + "=" * 70)
    print("【步骤4】测试基本功能")
    print("=" * 70)

    # 测试文档加载
    try:
        from trading_loss_rag import TradingLossRAG

        print("测试文档加载...")
        rag = TradingLossRAG(api_key="dummy-key", folder_path="./ku")
        docs = rag.load_documents(max_files=3)

        if docs:
            print(f"✅ 成功加载 {len(docs)} 个文档")
            print(f"  第一个文档来源: {docs[0].metadata.get('source', 'unknown')}")
        else:
            print("❌ 未加载到文档")
            return False

    except Exception as e:
        print(f"❌ 文档加载测试失败: {e}")
        return False

    return True


def test_full_system():
    """测试完整系统（需要API Key）"""
    print("\n" + "=" * 70)
    print("【步骤5】测试完整系统")
    print("=" * 70)

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("⚠️  跳过（需要API Key）")
        return True

    try:
        from test_agent_with_image import initialize_systems

        print("初始化系统...")
        success = initialize_systems(api_key)

        if success:
            print("✅ 系统初始化成功")
        else:
            print("❌ 系统初始化失败")
            return False

    except Exception as e:
        print(f"❌ 系统测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("🧪 智能股票分析Agent - 系统测试")
    print("=" * 70)

    results = []

    # 测试1：模块导入
    results.append(("模块导入", test_imports()))

    # 测试2：API Key
    results.append(("API Key", test_api_key()))

    # 测试3：知识库
    results.append(("知识库", test_knowledge_folder()))

    # 测试4：基本功能
    results.append(("基本功能", test_basic_functionality()))

    # 测试5：完整系统（可选）
    if results[-1][1]:  # 如果前面的测试都通过
        results.append(("完整系统", test_full_system()))

    # 总结
    print("\n" + "=" * 70)
    print("📊 测试结果总结")
    print("=" * 70)

    passed = 0
    failed = 0

    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}  {test_name}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\n总计: {passed}个通过, {failed}个失败")

    if failed == 0:
        print("\n🎉 所有测试通过！系统已就绪。")
        print("\n可以运行：")
        print("  python3 test_agent_with_image.py")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查上述错误信息。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
