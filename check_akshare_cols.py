#!/usr/bin/env python3
"""检查akshare返回的列名"""
import os
os.environ['LD_LIBRARY_PATH'] = '/home/lixiang/anaconda3/lib'

try:
    import akshare as ak
    import pandas as pd
    from datetime import datetime, timedelta

    # 使用一个已知的股票代码测试
    symbol = "600036"  # 招商银行
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')

    print(f"测试股票: {symbol}")
    print(f"日期范围: {start_date} ~ {end_date}\n")

    df = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust="qfq"
    )

    print("返回的列名:")
    print(df.columns.tolist())
    print()

    print("最近5行数据:")
    print(df.head(5).to_string())

except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()