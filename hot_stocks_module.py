"""
热股榜数据获取和赚钱效应分析模块

支持多个数据源：
- 新浪财经热股排行（基于成交额、涨幅）
- 东方财富热股榜
- 自建热度算法（综合成交额、涨幅、换手率等）
"""
import requests
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd


# ==================== 配置 ====================
HOT_STOCKS_CACHE_DIR = "./data/hot_stocks_history"
CACHE_DURATION = 300  # 缓存时间（秒），默认5分钟


# ==================== 数据源1：新浪财经热股排行 ====================
def fetch_sina_hot_stocks_by_amount(top_n: int = 50) -> pd.DataFrame:
    """从新浪财经获取按成交额排序的热股

    参数：
    - top_n: 获取前N只股票

    返回：
    - DataFrame: 包含股票代码、名称、成交额等信息
    """
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from test_agent_knowledge import fetch_sina_stock_data

        # 获取按成交额排序的数据
        df = fetch_sina_stock_data(sort_field='amount', num=top_n, asc=0)

        if df.empty:
            return pd.DataFrame()

        # 添加热度排名和热度值
        df['热度排名'] = range(1, len(df) + 1)
        df['热度值'] = df['成交额']  # 以成交额作为热度值

        # 添加成交额(亿)列 - 确保存在
        if '成交额' in df.columns:
            df['成交额(亿)'] = df['成交额'] / 100000000
        else:
            df['成交额(亿)'] = 0

        # 添加数据源标记
        df['数据源'] = '新浪财经_成交额'

        return df

    except Exception as e:
        print(f"获取新浪热股榜失败: {e}")
        return pd.DataFrame()


def fetch_sina_hot_stocks_by_change(top_n: int = 50) -> pd.DataFrame:
    """从新浪财经获取按涨跌幅排序的热股

    参数：
    - top_n: 获取前N只股票

    返回：
    - DataFrame: 包含股票代码、名称、涨跌幅等信息
    """
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from test_agent_knowledge import fetch_sina_stock_data

        # 获取按涨跌幅排序的数据
        df = fetch_sina_stock_data(sort_field='changepercent', num=top_n, asc=0)

        if df.empty:
            return pd.DataFrame()

        # 添加热度排名和热度值
        df['热度排名'] = range(1, len(df) + 1)
        df['热度值'] = df['涨跌幅']  # 以涨跌幅作为热度值

        # 添加成交额(亿)列 - 确保存在
        if '成交额' in df.columns:
            df['成交额(亿)'] = df['成交额'] / 100000000
        else:
            df['成交额(亿)'] = 0

        # 添加数据源标记
        df['数据源'] = '新浪财经_涨跌幅'

        return df

    except Exception as e:
        print(f"获取新浪涨幅榜失败: {e}")
        return pd.DataFrame()


# ==================== 数据源2：东方财富热股榜 ====================
def fetch_eastmoney_hot_stocks(top_n: int = 50) -> pd.DataFrame:
    """从东方财富获取热股榜（关注榜、讨论榜等）

    数据来源：
    - 主力热股: https://push2.eastmoney.com/api/qt/clist/get
    - 自选热股: https://push2.eastmoney.com/api/qt/clist/get
    - 涨幅榜: https://push2.eastmoney.com/api/qt/clist/get

    参数：
    - top_n: 获取前N只股票

    返回：
    - DataFrame: 包含股票代码、名称、热度等信息
    """
    try:
        # 东方财富主力热股接口
        url = "https://push2.eastmoney.com/api/qt/clist/get"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com/',
        }

        # 主力净流入排序
        params = {
            'pn': '1',
            'pz': str(top_n),
            'po': '1',
            'np': '1',
            'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
            'fltt': '2',
            'invt': '2',
            'fid': 'f62',  # f62=主力净流入
            'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',  # A股所有板块
            'fields': 'f12,f13,f14,f2,f3,f5,f6,f60,f62,f152,f184,f204,f205,f124,f1,f15',
        }

        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("rc") != 0:
            print(f"东方财富API返回错误: {data.get('rt')}")
            return pd.DataFrame()

        # 解析数据
        diff_list = data.get("data", {}).get("diff", [])

        if not diff_list:
            return pd.DataFrame()

        # 构建DataFrame
        stocks = []
        for i, item in enumerate(diff_list):
            code = item.get('f12', '')
            market = item.get('f13', '')
            name = item.get('f14', '')
            price = item.get('f2', 0)
            change_percent = item.get('f3', 0)
            change_amount = item.get('f4', 0)
            turnover = item.get('f5', 0)  # 成交额（元）
            turnover_rate = item.get('f8', 0)  # 换手率%
            volume = item.get('f5_old', 0)  # 成交量（手）
            high = item.get('f15', 0)
            low = item.get('f16', 0)
            open_price = item.get('f17', 0)
            yesterday_close = item.get('f18', 0)
            main_inflow = item.get('f62', 0)  # 主力净流入

            # 热度值：基于主力净流入和成交额
            heat_value = main_inflow if main_inflow > 0 else turnover / 100000000

            stocks.append({
                '代码': f"{market}{code}" if market else code,
                'code': code,
                '名称': name,
                '最新价': price,
                '涨跌幅': change_percent,
                '涨跌额': change_amount,
                '成交额': turnover,
                '成交额(亿)': turnover / 100000000,
                '成交量': volume * 100 if volume else 0,
                '换手率': turnover_rate,
                '今开': open_price,
                '昨收': yesterday_close,
                '最高': high,
                '最低': low,
                '主力净流入(万)': main_inflow / 10000,
                '热度排名': i + 1,
                '热度值': heat_value,
                '数据源': '东方财富_主力流入',
            })

        df = pd.DataFrame(stocks)
        return df

    except Exception as e:
        print(f"获取东方财富热股榜失败: {e}")
        return pd.DataFrame()


# ==================== 数据源3：同花顺热股榜 ====================
def fetch_10jqka_hot_stocks(top_n: int = 50) -> pd.DataFrame:
    """从同花顺获取热股榜（如果接口可用）

    注意：同花顺接口较为复杂，可能需要逆向分析
    本函数提供基础框架，实际使用时需要根据接口情况调整

    参数：
    - top_n: 获取前N只股票

    返回：
    - DataFrame: 包含股票代码、名称、热度等信息
    """
    try:
        # 同花顺热股排行榜URL示例（可能需要更新）
        # 通常需要逆向分析JS逻辑获取真实API
        url = "http://t.10jqka.com.cn/hotStock/list"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://t.10jqka.com.cn/',
        }

        params = {
            'page': '1',
            'size': str(top_n),
        }

        # 尝试请求
        resp = requests.get(url, params=params, headers=headers, timeout=10)

        if resp.status_code != 200:
            print(f"同花顺API状态码: {resp.status_code}")
            return pd.DataFrame()

        # 解析返回数据（具体格式取决于实际接口）
        # 这里提供基础框架，需要根据实际情况调整
        try:
            data = resp.json()
            # 解析并构建DataFrame
            # ...
        except json.JSONDecodeError:
            # 可能返回的是HTML，需要解析
            print("同花顺返回HTML格式，需要进一步解析")
            return pd.DataFrame()

        return pd.DataFrame()

    except Exception as e:
        print(f"获取同花顺热股榜失败: {e}")
        print("提示：同花顺接口可能需要逆向分析，建议使用新浪或东方财富接口")
        return pd.DataFrame()


# ==================== 自建热度算法（综合多种因素） ====================
def calculate_hotness_score(
    amount: float,
    change_percent: float,
    turnover_rate: float,
    is_limit_up: bool = False,
    continuous_boards: int = 0
) -> float:
    """计算股票热度综合得分

    参数：
    - amount: 成交额（亿元）
    - change_percent: 涨跌幅（百分比）
    - turnover_rate: 换手率（百分比）
    - is_limit_up: 是否涨停
    - continuous_boards: 连板数

    返回：
    - 热度得分（0-100）
    """
    score = 0

    # 1. 成交额得分（0-40分）
    if amount >= 20:
        score += 40
    elif amount >= 10:
        score += 30
    elif amount >= 5:
        score += 20
    elif amount >= 2:
        score += 10

    # 2. 涨幅得分（0-30分）
    if is_limit_up:
        score += 30
    elif change_percent >= 9:
        score += 25
    elif change_percent >= 7:
        score += 20
    elif change_percent >= 5:
        score += 15
    elif change_percent > 0:
        score += 10 * (change_percent / 5)

    # 3. 换手率得分（0-20分）
    if turnover_rate >= 20:
        score += 20
    elif turnover_rate >= 15:
        score += 15
    elif turnover_rate >= 10:
        score += 10
    elif turnover_rate >= 5:
        score += 5

    # 4. 连板加分（最多10分）
    if continuous_boards >= 5:
        score += 10
    elif continuous_boards >= 3:
        score += 8
    elif continuous_boards >= 2:
        score += 5

    return min(score, 100)  # 最高100分


def fetch_composite_hot_stocks(top_n: int = 50) -> pd.DataFrame:
    """获取综合热股榜（自建热度算法）

    结合：
    1. 成交额排序
    2. 涨跌幅排序
    3. 自定义热度算法

    参数：
    - top_n: 获取前N只股票

    返回：
    - DataFrame: 包含股票代码、名称、综合热度得分等信息
    """
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from test_agent_knowledge import fetch_sina_stock_data, fetch_limit_up_stocks

        # 获取足够的数据样本
        df_all = fetch_sina_stock_data(sort_field='amount', num=200, asc=0)

        if df_all.empty:
            return pd.DataFrame()

        # 获取涨停股列表，标记涨停股
        try:
            df_limit_up = fetch_limit_up_stocks()
            limit_up_codes = df_limit_up['code'].tolist() if not df_limit_up.empty else []
        except:
            limit_up_codes = []

        # 计算综合热度得分
        df_all['热度得分'] = df_all.apply(
            lambda row: calculate_hotness_score(
                amount=row.get('成交额(亿)', 0),
                change_percent=row.get('涨跌幅', 0),
                turnover_rate=row.get('换手率', 0),
                is_limit_up=row.get('code', '') in limit_up_codes,
                continuous_boards=row.get('连板数', 0) if '连板数' in row else 0
            ),
            axis=1
        )

        # 按热度得分排序，取前N只
        df_hot = df_all.sort_values('热度得分', ascending=False).head(top_n).copy()
        df_hot['热度排名'] = range(1, len(df_hot) + 1)
        df_hot['数据源'] = '综合热度算法'

        return df_hot

    except Exception as e:
        print(f"获取综合热股榜失败: {e}")
        return pd.DataFrame()


# ==================== 数据缓存 ====================
def load_hot_stocks_cache(cache_file: str) -> Optional[pd.DataFrame]:
    """加载热股榜缓存数据

    参数：
    - cache_file: 缓存文件路径

    返回：
    - DataFrame 或 None
    """
    try:
        cache_path = Path(cache_file)
        if not cache_path.exists():
            return None

        # 检查缓存是否过期
        cache_time = cache_path.stat().st_mtime
        if time.time() - cache_time > CACHE_DURATION:
            return None

        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        df = pd.DataFrame(data.get('stocks', []))
        return df

    except Exception as e:
        print(f"加载缓存失败: {e}")
        return None


def save_hot_stocks_cache(df: pd.DataFrame, cache_file: str, source: str):
    """保存热股榜缓存数据

    参数：
    - df: 热股榜数据
    - cache_file: 缓存文件路径
    - source: 数据源名称
    """
    try:
        cache_path = Path(cache_file)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source': source,
            'count': len(df),
            'stocks': df.to_dict('records')
        }

        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"保存缓存失败: {e}")


def get_hot_stocks(
    source: str = 'sina_amount',
    top_n: int = 50,
    use_cache: bool = True
) -> Tuple[pd.DataFrame, str]:
    """获取热股榜数据（集成所有数据源）

    参数：
    - source: 数据源，可选：
      - 'sina_amount': 新浪财经（按成交额）
      - 'sina_change': 新浪财经（按涨跌幅）
      - 'eastmoney': 东方财富热股榜
      - '10jqka': 同花顺热股榜（实验性）
      - 'composite': 综合热度算法
    - top_n: 获取前N只
    - use_cache: 是否使用缓存

    返回：
    - (DataFrame, source_name): 热股榜数据和数据源名称
    """
    # 确定缓存文件路径
    today = datetime.now().strftime('%Y%m%d')
    cache_file = f"{HOT_STOCKS_CACHE_DIR}/hot_stocks_{source}_{today}.json"

    # 尝试从缓存加载
    if use_cache:
        df_cached = load_hot_stocks_cache(cache_file)
        if df_cached is not None and not df_cached.empty:
            source_name = {
                'sina_amount': '新浪财经成交额榜',
                'sina_change': '新浪财经涨幅榜',
                'eastmoney': '东方财富热股榜',
                '10jqka': '同花顺热股榜',
                'composite': '综合热度榜'
            }.get(source, source)
            return df_cached, source_name

    # 根据数据源选择获取方式
    fetch_functions = {
        'sina_amount': fetch_sina_hot_stocks_by_amount,
        'sina_change': fetch_sina_hot_stocks_by_change,
        'eastmoney': fetch_eastmoney_hot_stocks,
        '10jqka': fetch_10jqka_hot_stocks,
        'composite': fetch_composite_hot_stocks,
    }

    fetch_func = fetch_functions.get(source, fetch_sina_hot_stocks_by_amount)
    df = fetch_func(top_n)

    if df.empty:
        return pd.DataFrame(), f"数据获取失败: {source}"

    # 保存缓存
    if use_cache:
        source_display = {
            'sina_amount': '新浪财经成交额榜',
            'sina_change': '新浪财经涨幅榜',
            'eastmoney': '东方财富热股榜',
            '10jqka': '同花顺热股榜',
            'composite': '综合热度榜'
        }.get(source, source)
        save_hot_stocks_cache(df, cache_file, source_display)

    source_name = {
        'sina_amount': '新浪财经成交额榜',
        'sina_change': '新浪财经涨幅榜',
        'eastmoney': '东方财富热股榜',
        '10jqka': '同花顺热股榜',
        'composite': '综合热度榜'
    }.get(source, source)

    return df, source_name


# ==================== 赚钱效应分析 ====================
def analyze_profit_effect(df_hot: pd.DataFrame) -> Dict[str, Any]:
    """分析市场赚钱效应

    基于热股榜数据分析市场的赚钱效应强度、板块分布、连板情况等

    参数：
    - df_hot: 热股榜数据

    返回：
    - 分析结果字典
    """
    if df_hot.empty:
        return {
            'status': 'error',
            'message': '热股榜数据为空'
        }

    result = {
        'status': 'success',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_count': len(df_hot),
    }

    # 1. 基础统计
    result['基础统计'] = {
        '平均涨幅': float(df_hot['涨跌幅'].mean()),
        '最大涨幅': float(df_hot['涨跌幅'].max()),
        '最小涨幅': float(df_hot['涨跌幅'].min()),
        '上涨股票数': int((df_hot['涨跌幅'] > 0).sum()),
        '下跌股票数': int((df_hot['涨跌幅'] < 0).sum()),
        '涨停股票数': int((df_hot['涨跌幅'] >= 9.9).sum()),
    }

    # 2. 成交额分析
    if '成交额(亿)' in df_hot.columns:
        result['成交额分析'] = {
            '总成交额(亿)': float(df_hot['成交额(亿)'].sum()),
            '平均成交额(亿)': float(df_hot['成交额(亿)'].mean()),
            '最大成交额(亿)': float(df_hot['成交额(亿)'].max()),
            '成交额>10亿的股票数': int((df_hot['成交额(亿)'] > 10).sum()),
            '成交额>5亿的股票数': int((df_hot['成交额(亿)'] > 5).sum()),
        }

    # 3. 换手率分析
    if '换手率' in df_hot.columns:
        result['换手率分析'] = {
            '平均换手率': float(df_hot['换手率'].mean()),
            '换手率>10%的股票数': int((df_hot['换手率'] > 10).sum()),
            '换手率>20%的股票数': int((df_hot['换手率'] > 20).sum()),
        }

    # 4. 连板分析（如果有的话）
    if '连板数' in df_hot.columns:
        max_boards = df_hot['连板数'].max()
        result['连板分析'] = {
            '最高连板': int(max_boards),
            '5板以上': int((df_hot['连板数'] >= 5).sum()),
            '3-4板': int((df_hot['连板数'] >= 3) & (df_hot['连板数'] <= 4)).sum(),
            '2板': int((df_hot['连板数'] == 2).sum()),
            '首板': int((df_hot['连板数'] == 1).sum()),
        }

    # 5. 赚钱效应强度评级
    profit_effect_level = calculate_profit_effect_level(df_hot)
    result['赚钱效应评级'] = profit_effect_level

    # 6. 提交建议
    result['操作建议'] = get_trading_suggestion(profit_effect_level, df_hot)

    return result


def calculate_profit_effect_level(df_hot: pd.DataFrame) -> Dict[str, str]:
    """计算赚钱效应强度等级

    参数：
    - df_hot: 热股榜数据

    返回：
    - 包含等级和描述的字典
    """
    # 关键指标
    avg_change = df_hot['涨跌幅'].mean()
    positive_count = (df_hot['涨跌幅'] > 0).sum()
    limit_up_count = (df_hot['涨跌幅'] >= 9.9).sum()

    # 判断等级
    if limit_up_count >= 30 and avg_change > 7:
        level = "极强"
        description = "市场赚钱效应极强，涨停板众多，平均涨幅较高，适合积极参与"
    elif limit_up_count >= 15 and avg_change > 5:
        level = "强"
        description = "市场赚钱效应较强，涨停板较多，适合激进操作"
    elif limit_up_count >= 8 and avg_change > 3:
        level = "中等"
        description = "市场赚钱效应中等，有一定机会，需精选个股"
    elif positive_count >= len(df_hot) * 0.6 and avg_change > 0:
        level = "一般"
        description = "市场赚钱效应一般，多数股票上涨，但涨幅有限"
    else:
        level = "弱"
        description = "市场赚钱效应弱，机会较少，建议谨慎或观望"

    return {
        '等级': level,
        '描述': description
    }


def get_trading_suggestion(level: Dict[str, str], df_hot: pd.DataFrame) -> List[str]:
    """根据赚钱效应等级给出操作建议

    参数：
    - level: 赚钱效应等级
    - df_hot: 热股榜数据

    返回：
    - 建议列表
    """
    level_name = level['等级']
    suggestions = []

    if level_name == "极强":
        suggestions = [
            "市场情绪高涨，可以积极参与打板",
            "关注连板股的接力机会",
            "前排高涨幅股可以考虑激进操作",
            "注意控制仓位，避免过度追高",
            "关注板块效应，主流板块优先"
        ]
    elif level_name == "强":
        suggestions = [
            "市场情绪较好，可以适当参与",
            "关注前排强势股和连板股",
            "可以尝试打板或低吸",
            "注意筛选优质个股，避免杂毛",
            "控制风险，设置止损"
        ]
    elif level_name == "中等":
        suggestions = [
            "市场情绪一般，精选个股操作",
            "关注成交额大、走势稳健的股票",
            "低吸优于追涨",
            "控制仓位，不宜重仓",
            "观望等待更好的机会"
        ]
    elif level_name == "一般":
        suggestions = [
            "市场赚钱效应有限，谨慎操作",
            "仅关注少数确定性机会",
            "严格风控，设置止损",
            "建议空仓或轻仓观望",
            "等待市场情绪回暖"
        ]
    else:  # 弱
        suggestions = [
            "市场赚钱效应弱，建议观望",
            "避免盲目追涨杀跌",
            "如果参与，务必严格止损",
            "空仓观望是最佳选择",
            "耐心等待情绪反转"
        ]

    return suggestions


# ==================== 数据持久化 ====================
def save_hot_stocks_history(df: pd.DataFrame, source: str = 'sina_amount'):
    """保存热股榜历史数据

    参数：
    - df: 热股榜数据
    - source: 数据源
    """
    try:
        # 创建目录
        cache_dir = Path(HOT_STOCKS_CACHE_DIR)
        cache_dir.mkdir(parents=True, exist_ok=True)

        # 生成文件名
        today = datetime.now().strftime('%Y%m%d')
        timestamp = datetime.now().strftime('%H%M%S')
        filename = f"hot_stocks_{source}_{today}_{timestamp}.json"
        filepath = cache_dir / filename

        # 构建保存数据
        data = {
            'date': today,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source': source,
            'count': len(df),
            'stocks': df.to_dict('records')
        }

        # 保存
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"热股榜历史数据已保存: {filepath}")

    except Exception as e:
        print(f"保存热股榜历史数据失败: {e}")


def load_hot_stocks_history(date: str = None, source: str = 'sina_amount') -> Optional[pd.DataFrame]:
    """加载热股榜历史数据

    参数：
    - date: 日期（格式: YYYYMMDD），None表示今天
    - source: 数据源

    返回：
    - DataFrame 或 None
    """
    try:
        if date is None:
            date = datetime.now().strftime('%Y%m%d')

        cache_dir = Path(HOT_STOCKS_CACHE_DIR)

        # 查找匹配的文件（可能有多个时间版本）
        pattern = f"hot_stocks_{source}_{date}_*.json"
        files = list(cache_dir.glob(pattern))

        if not files:
            return None

        # 取最新的文件
        latest_file = max(files, key=lambda x: x.stat().st_mtime)

        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        df = pd.DataFrame(data.get('stocks', []))
        return df

    except Exception as e:
        print(f"加载热股榜历史数据失败: {e}")
        return None


# ==================== 主函数示例 ====================
if __name__ == "__main__":
    print("热股榜数据获取和赚钱效应分析模块\n")
    print("=" * 60)

    # 测试各个数据源
    sources = ['sina_amount', 'sina_change', 'eastmoney', 'composite']

    for source in sources:
        print(f"\n[{source.upper()}] 测试获取热股榜...")
        df, source_name = get_hot_stocks(source=source, top_n=20)

        if not df.empty:
            print(f"✓ 成功获取 {len(df)} 只股票")
            print(f"  来源: {source_name}")
            print(f"\n  前5名:")
            print(df[['代码', '名称', '涨跌幅', '成交额(亿)', '热度排名']].head())

            # 分析赚钱效应
            analysis = analyze_profit_effect(df)
            print(f"\n  赚钱效应: {analysis['赚钱效应评级']['等级']} - {analysis['赚钱效应评级']['描述']}")
            print(f"  基础统计: 涨停{analysis['基础统计']['涨停股票数']}只, 平均涨幅{analysis['基础统计']['平均涨幅']:.2f}%")

            # 保存历史数据
            save_hot_stocks_history(df, source)
        else:
            print(f"✗ 获取失败")

        print("-" * 60)

    print("\n测试完成!")
