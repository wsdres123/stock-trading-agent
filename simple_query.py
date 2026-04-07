#!/usr/bin/env python3
"""
轻量级查询工具 - 完全绕过LangChain Agent
直接使用工具函数，无streaming bug
"""
import os
import sys
import json
from datetime import datetime

# 设置路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def get_board_data():
    """获取连板梯队"""
    today = datetime.now().strftime('%Y%m%d')
    cache_file = f'./data/limit_up_history/{today}_board_cache.json'

    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f).get('summary', '数据读取失败')
    return "今日连板数据尚未生成"


def get_sentiment_data():
    """获取市场情绪"""
    today = datetime.now().strftime('%Y%m%d')
    cache_file = f'./data/limit_up_history/{today}_sentiment_cache.json'

    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                summary = data.get('summary', '')
                if summary:
                    return summary
        except:
            pass

    # 如果没有情绪缓存，从连板数据推算
    board_data = get_board_data()
    if board_data and "今日涨停股" in board_data:
        # 简单分析
        if "6连板" in board_data:
            high_board = "6连板"
        elif "5连板" in board_data:
            high_board = "5连板"
        elif "4连板" in board_data:
            high_board = "4连板"
        elif "3连板" in board_data:
            high_board = "3连板"
        elif "2连板" in board_data:
            high_board = "2连板"
        else:
            high_board = "首板为主"

        # 统计涨停股数量
        import re
        match = re.search(r'共 (\d+) 只', board_data)
        total = int(match.group(1)) if match else 0

        sentiment = f"""📊 市场情绪分析（基于连板数据）

🎯 今日最高板: {high_board}

💹 涨停统计: {total}只（已过滤ST）

📈 情绪特征:
"""

        if "6连板" in board_data or "5连板" in board_data:
            sentiment += "  - 市场有高度板，情绪尚可\n"
            sentiment += "  - 存在一定的赚钱效应\n"
        else:
            sentiment += "  - 无高度板，情绪偏弱\n"
            sentiment += "  - 接力意愿较低\n"

        if total > 80:
            sentiment += "  - 涨停家数较多，市场活跃\n"
        elif total > 50:
            sentiment += "  - 涨停家数适中\n"
        else:
            sentiment += "  - 涨停家数偏少，市场谨慎\n"

        sentiment += f"\n{board_data}"
        return sentiment

    return "无法获取情绪数据"


def get_limit_up_stocks():
    """获取涨停股列表"""
    today = datetime.now().strftime('%Y%m%d')
    data_file = f'./data/limit_up_history/{today}.json'

    if not os.path.exists(data_file):
        return "今日涨停股数据尚未生成"

    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    stocks = data.get('stocks', [])
    if not stocks:
        return "今日暂无涨停股"

    result = [f"📊 今日涨停股共 {len(stocks)} 只\n"]
    result.append("成交额前20只:\n")

    for idx, stock in enumerate(stocks[:20], 1):
        name = stock.get('名称', '')
        code = stock.get('code', '')
        pct = stock.get('涨跌幅', 0)
        amount = stock.get('成交额(亿)', 0)
        result.append(f"{idx:2d}. {name}({code}) {pct:6.2f}% 成交额{amount:8.2f}亿")

    return '\n'.join(result)


def search_knowledge(query: str):
    """搜索知识库"""
    try:
        from trading_loss_rag import TradingLossRAG

        api_key = os.environ.get("DASHSCOPE_API_KEY")
        if not api_key:
            return "❌ 未设置DASHSCOPE_API_KEY"

        # 使用缓存的RAG实例
        if not hasattr(search_knowledge, 'rag'):
            print("  初始化知识库...")
            rag = TradingLossRAG(api_key=api_key, folder_path="./ku")
            if not rag.build_enhanced_index():
                return "❌ 知识库初始化失败"
            search_knowledge.rag = rag

        return search_knowledge.rag.search_with_reasoning(query)
    except Exception as e:
        return f"❌ 知识库查询失败: {e}"


def process_query(query: str) -> str:
    """处理用户查询（直接路由，无LLM）"""
    query_lower = query.lower()

    # 1. 接力/连板相关
    if any(kw in query_lower for kw in ['接力', '连板', '最高板', '梯队']):
        print("  → 检测到连板查询，直接获取数据...")
        return get_board_data()

    # 2. 情绪相关
    if any(kw in query_lower for kw in ['情绪', '氛围', '赚钱效应']):
        print("  → 检测到情绪查询，分析市场情绪...")
        return get_sentiment_data()

    # 3. 涨停股列表
    if any(kw in query_lower for kw in ['涨停股', '涨停', '涨停榜']):
        print("  → 检测到涨停股查询...")
        return get_limit_up_stocks()

    # 4. 知识库查询
    if any(kw in query_lower for kw in ['如何', '什么是', '怎么', '为什么', '模式', '战法', '竞价', '周期']):
        print("  → 检测到策略问题，查询知识库...")
        return search_knowledge(query)

    # 5. 默认：尝试智能判断
    print("  → 未匹配到明确类型，尝试综合查询...")

    # 如果包含"今天"，优先返回情绪+连板
    if "今天" in query or "今日" in query:
        sentiment = get_sentiment_data()
        return sentiment

    # 其他情况，查询知识库
    return search_knowledge(query)


def main():
    """主函数 - 交互模式"""
    print("=" * 70)
    print("💡 轻量级查询工具（无streaming bug）")
    print("=" * 70)
    print()
    print("支持的查询类型:")
    print("  1. 接力情况/连板梯队: 今天接力情况、最高板、连板梯队")
    print("  2. 市场情绪: 今天情绪如何、市场氛围、赚钱效应")
    print("  3. 涨停股: 今日涨停股、涨停榜")
    print("  4. 知识库: 如何判断情绪、短线模式、竞价技巧等")
    print()
    print("输入 'q' 或 'exit' 退出")
    print("=" * 70)

    while True:
        try:
            query = input("\n💬 你的问题: ").strip()

            if query.lower() in ['q', 'quit', 'exit', '退出']:
                print("\n👋 再见！")
                break

            if not query:
                continue

            print("\n⚡ 处理中...\n")

            result = process_query(query)

            print("─" * 70)
            print(result)
            print("─" * 70)

        except KeyboardInterrupt:
            print("\n\n👋 再见！")
            break
        except Exception as e:
            print(f"\n❌ 错误: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    # 如果有命令行参数，直接查询
    if len(sys.argv) > 1:
        query = ' '.join(sys.argv[1:])
        print(f"查询: {query}\n")
        print(process_query(query))
    else:
        main()
