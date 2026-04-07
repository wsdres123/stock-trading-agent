#!/usr/bin/env python3
"""
接力情况快速查询工具（绕过Agent，直接返回数据）
用于在Agent出现streaming bug时作为备选方案
"""
import json
import os
from datetime import datetime


def get_board_data():
    """获取今日连板梯队数据"""
    today = datetime.now().strftime('%Y%m%d')
    cache_file = f'./data/limit_up_history/{today}_board_cache.json'

    if not os.path.exists(cache_file):
        print("❌ 今日连板数据尚未生成")
        print("   请先运行: python3 generate_board_ladder.py")
        return None

    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        return cache_data.get('summary', '')
    except Exception as e:
        print(f"❌ 读取数据失败: {e}")
        return None


def main():
    """主函数"""
    print("=" * 70)
    print("📊 今日接力情况（直接数据，无需Agent）")
    print("=" * 70)
    print()

    data = get_board_data()

    if data:
        print(data)
        print()
        print("=" * 70)
        print("✅ 数据获取成功")
        print()
        print("💡 提示:")
        print("   - 这是直接从缓存读取的真实数据")
        print("   - 如果Agent出现streaming bug，可以用这个脚本")
        print("   - 数据每30分钟更新一次")
        print("=" * 70)
    else:
        print("❌ 无法获取数据")


if __name__ == "__main__":
    main()
