#!/usr/bin/env python3
"""调试连板计算问题"""
import os
os.environ['LD_LIBRARY_PATH'] = '/home/lixiang/anaconda3/lib'

try:
    import akshare as ak
    import pandas as pd
    from datetime import datetime, timedelta
    import time

    print("="*70)
    print("调试连板计算问题")
    print("="*70)
    print()

    # 获取某只近期涨停股的历史数据测试
    # 先获取今日涨停股
    import requests
    import json

    url = 'http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    params = {
        'page': 1,
        'num': 80,
        'sort': 'changepercent',
        'asc': 0,
        'node': 'hs_a'
    }

    print("获取今日涨停股...")
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    data = json.loads(resp.text)
    df = pd.DataFrame(data)

    # 筛选涨停股
    df_zt = df[df['changepercent'] >= 9.5]
    df_zt = df_zt[~df_zt['name'].str.contains('ST|退', na=False)]

    print(f"今日涨停股: {len(df_zt)}只\n")

    if len(df_zt) > 0:
        # 取第一只测试
        test_stock = df_zt.iloc[0]
        code = test_stock['symbol'].replace('sh', '').replace('sz', '').replace('bj', '')
        name = test_stock['name']
        change_pct = test_stock['changepercent']

        print(f"测试股票: {name}({code}) 今日涨幅: {change_pct}%\n")

        # 获取最近15天数据
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')

        print(f"AKShare请求日期范围: {start_date} ~ {end_date}\n")

        df_hist = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq"
        )

        if not df_hist.empty:
            print(f"获取到 {len(df_hist)} 条历史数据\n")
            print("最近10天数据:")
            print(df_hist.head(10)[['日期', '收盘', '涨跌幅', '最高', '最低']].to_string(index=False))
            print()

            # 手动计算连板
            print("手动计算连板:")
            continuous_days = 0
            for idx, row in df_hist.iterrows():
                pct = row['涨跌幅']
                date = row['日期']

                # 判断是否涨停
                is_limit_up = False
                if abs(pct - 10) < 0.5:
                    is_limit_up = True
                    reason = "主板涨停"
                elif abs(pct - 20) < 0.5:
                    is_limit_up = True
                    reason = "创业板/科创板涨停"
                elif abs(pct - 30) < 0.5:
                    is_limit_up = True
                    reason = "北交所涨停"
                elif pct > 40:
                    is_limit_up = True
                    reason = "新股/特殊"

                if is_limit_up:
                    continuous_days += 1
                    status = "✓"
                else:
                    status = "✗"

                print(f"  {date}: {pct:+.2f}% {status} ({reason if is_limit_up else '未涨停'})")

                # 只在遇到第一个非涨停时停止
                if not is_limit_up and continuous_days == 0:
                    break

            print(f"\n连续涨停天数: {continuous_days}板")

            # 再测试几只股票
            print(f"\n{'='*70}")
            print("测试多只涨停股的连板情况:")
            print(f"{'='*70}")

            for i in range(min(10, len(df_zt))):
                stock = df_zt.iloc[i]
                code = stock['symbol'].replace('sh', '').replace('sz', '').replace('bj', '')
                name = stock['name']
                change_pct = stock['changepercent']

                df_hist = ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    adjust="qfq"
                )

                if not df_hist.empty:
                    continuous = 0
                    for _, row in df_hist.iterrows():
                        pct = row['涨跌幅']
                        if abs(pct - 10) < 0.5 or abs(pct - 20) < 0.5 or abs(pct - 30) < 0.5 or pct > 40:
                            continuous += 1
                        else:
                            break

                    print(f"  {name}({code}): {change_pct:+.2f}% -> {continuous}板")

                time.sleep(0.5)  # 避免请求过快

except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()