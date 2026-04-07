"""
生成正确的连板梯队数据（不依赖复杂库）
"""
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict


def get_limit_up_codes_by_date(date_str: str) -> set:
    """获取指定日期的涨停股代码集合"""
    try:
        file_path = f'./data/limit_up_history/{date_str}.json'
        if not os.path.exists(file_path):
            return set()

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        codes = set()
        for stock in data.get('stocks', []):
            code = stock.get('code', '')
            if code:
                codes.add(code)
        return codes
    except:
        return set()


def calculate_continuous_boards(symbol: str) -> int:
    """计算连板天数"""
    today = datetime.now()
    continuous_days = 0

    for i in range(15):  # 检查最近15天
        date_obj = today - timedelta(days=i)
        if date_obj.weekday() >= 5:  # 跳过周末
            continue

        date_str = date_obj.strftime('%Y%m%d')
        limit_up_codes = get_limit_up_codes_by_date(date_str)

        if not limit_up_codes:
            continue  # 跳过节假日（无数据文件的工作日），继续往前查

        if symbol in limit_up_codes:
            continuous_days += 1
        else:
            break

    return continuous_days


def generate_board_ladder():
    """生成连板梯队数据"""
    today = datetime.now().strftime('%Y%m%d')
    today_file = f'./data/limit_up_history/{today}.json'

    if not os.path.exists(today_file):
        print(f"❌ 今日数据文件不存在: {today_file}")
        return None

    print("📊 正在分析今日涨停股的连板情况...")

    with open(today_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    stocks = data.get('stocks', [])
    print(f"  - 今日涨停股总数: {len(stocks)}")

    # 计算每只股票的连板天数
    board_groups = defaultdict(list)
    all_stock_info = []

    for idx, stock in enumerate(stocks, 1):
        code = stock.get('code', '')
        name = stock.get('名称', '')
        amount = stock.get('成交额(亿)', 0)
        pct = stock.get('涨跌幅', 0)

        if not code:
            continue

        boards = calculate_continuous_boards(code)

        stock_info = {
            'code': code,
            'name': name,
            'boards': boards,
            'amount': amount,
            'pct': pct
        }

        all_stock_info.append(stock_info)
        board_groups[boards].append(stock_info)

        if idx % 10 == 0:
            print(f"  - 已分析 {idx}/{len(stocks)}...")

    print(f"  ✅ 分析完成！\n")

    # 生成格式化输出
    summary_lines = []
    summary_lines.append(f"📊 今日涨停股共 {len(stocks)} 只（已过滤ST股）")
    summary_lines.append("")
    summary_lines.append("💹 涨停梯队：")
    summary_lines.append("")

    # 按连板天数降序显示
    for boards in sorted(board_groups.keys(), reverse=True):
        stocks_in_group = board_groups[boards]
        count = len(stocks_in_group)

        # 按成交额排序
        stocks_in_group.sort(key=lambda x: x['amount'], reverse=True)

        if boards >= 2:
            board_label = f"{boards}连板" if boards > 1 else "首板"
            summary_lines.append(f"【{board_label}】({count}只)：")

            # 显示所有高板股票（2连板以上）
            for s in stocks_in_group:
                summary_lines.append(
                    f"  {s['name']}({s['code']}) "
                    f"{s['pct']:.2f}% "
                    f"成交额{s['amount']:.2f}亿 "
                    f"[{boards}连板]"
                )

            summary_lines.append("")
        else:
            # 首板只显示前20只
            summary_lines.append(f"【首板】({count}只，显示前20只)：")
            for s in stocks_in_group[:20]:
                summary_lines.append(
                    f"  {s['name']}({s['code']}) "
                    f"{s['pct']:.2f}% "
                    f"成交额{s['amount']:.2f}亿 "
                    f"[首板]"
                )

            if count > 20:
                summary_lines.append(f"  ... 还有 {count - 20} 只首板股")

    summary = "\n".join(summary_lines)

    # 保存到缓存
    cache_file = f'./data/limit_up_history/{today}_board_cache.json'
    cache_data = {
        'summary': summary,
        'timestamp': datetime.now().timestamp(),
        'board_groups': {str(k): len(v) for k, v in board_groups.items()},
        'total': len(stocks)
    }

    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)

    print(f"✅ 连板梯队数据已保存到: {cache_file}\n")

    return summary


def main():
    """主函数"""
    print("=" * 70)
    print("生成今日连板梯队")
    print("=" * 70)
    print()

    summary = generate_board_ladder()

    if summary:
        print("=" * 70)
        print("连板梯队详情")
        print("=" * 70)
        print()
        print(summary)
        print()
        print("=" * 70)


if __name__ == "__main__":
    main()
