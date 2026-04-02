"""
股票实时分析Agent - 带知识库版本
支持从ku文件夹学习交易知识，结合实时数据提供更智能的分析
"""
import os
import time
import requests
import json
from typing import Dict, Any, List, Optional
import pandas as pd
from io import StringIO
from pathlib import Path

from langchain_community.chat_models.tongyi import ChatTongyi
from langchain.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferWindowMemory

# 导入优化的RAG系统
from trading_loss_rag import TradingLossRAG

# 修补 ChatTongyi 的 subtract_client_response 方法以修复索引错误
def patched_subtract_client_response(self, resp: Any, prev_resp: Any) -> Any:
    """Subtract prev response from curr response. 修复原生方法的IndexError"""
    import json

    resp_copy = json.loads(json.dumps(resp))
    choice = resp_copy["output"]["choices"][0]
    message = choice["message"]

    prev_resp_copy = json.loads(json.dumps(prev_resp))
    prev_choice = prev_resp_copy["output"]["choices"][0]
    prev_message = prev_choice["message"]

    message["content"] = message["content"].replace(prev_message["content"], "")

    if message.get("tool_calls"):
        prev_tool_calls = prev_message.get("tool_calls", [])
        for index, tool_call in enumerate(message["tool_calls"]):
            function = tool_call["function"]

            # 修复：添加索引边界检查
            if index < len(prev_tool_calls):
                prev_function = prev_tool_calls[index]["function"]

                if "name" in function:
                    function["name"] = function["name"].replace(
                        prev_function["name"], ""
                    )
                if "arguments" in function:
                    function["arguments"] = function["arguments"].replace(
                        prev_function["arguments"], ""
                    )

    return resp_copy

# 应用补丁 - 注释掉因为导致输出重复
# ChatTongyi.subtract_client_response = patched_subtract_client_response

try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    print("⚠️  警告：akshare未安装，历史数据功能将不可用")


# 全局知识库（使用优化的RAG系统）
TRADING_RAG = None


# -----------------------------
# 知识库构建函数
# -----------------------------
def read_txt_file(file_path: str) -> str:
    """读取txt文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        with open(file_path, 'r', encoding='gbk') as f:
            return f.read()


def read_docx_file(file_path: str) -> str:
    """读取docx文件"""
    try:
        doc = docx.Document(file_path)
        content = []
        for para in doc.paragraphs:
            if para.text.strip():
                content.append(para.text)
        return '\n'.join(content)
    except Exception:
        return ""


def read_xlsx_file(file_path: str) -> str:
    """读取xlsx文件"""
    try:
        df = pd.read_excel(file_path, sheet_name=None)  # 读取所有sheet
        content = []
        for sheet_name, sheet_df in df.items():
            content.append(f"\n=== {sheet_name} ===\n")
            content.append(sheet_df.to_string())
        return '\n'.join(content)
    except Exception:
        return ""


def load_knowledge_from_folder(folder_path: str = "./ku", max_files: int = 10) -> List[Dict[str, str]]:
    """从文件夹加载核心知识文件（快速模式）"""
    documents = []
    folder = Path(folder_path)

    if not folder.exists():
        print(f"⚠️  知识库文件夹不存在: {folder_path}")
        return documents

    print(f"正在加载知识库...", end='', flush=True)

    # 优先加载的核心文件（按重要性排序）
    priority_files = [
        "小明.txt",  # 精华经验总结，必须优先
        "交易原则.txt",
        "战法.txt",
        "刺客交易原则",
        "错题集",
        "情绪流.docx",
        "正道篇",
        "打板",  # 包含"打板"的文件
        "超短",  # 包含"超短"的文件
        "龙头",
        "选股",
    ]

    loaded_files = []
    success_count = 0

    # 先加载优先文件
    for priority in priority_files:
        if success_count >= max_files:
            break
        for file_path in folder.glob("*"):
            if success_count >= max_files:
                break
            if not file_path.is_file():
                continue
            file_name = file_path.name
            # 跳过临时文件
            if file_name.startswith('.~') or file_name.startswith('~$'):
                continue
            if file_path in loaded_files:
                continue
            if priority.lower() not in file_name.lower():
                continue

            content = ""
            try:
                if file_path.suffix == '.txt':
                    content = read_txt_file(str(file_path))
                elif file_path.suffix == '.docx':
                    content = read_docx_file(str(file_path))
                elif file_path.suffix in ['.xlsx', '.xls']:
                    # xlsx文件太大，跳过
                    continue
                else:
                    continue

                if content and len(content.strip()) > 10:
                    documents.append({
                        "content": content,
                        "source": file_name,
                        "path": str(file_path)
                    })
                    loaded_files.append(file_path)
                    success_count += 1
                    print('.', end='', flush=True)
            except Exception:
                pass

    # 如果还没加载够，随机加载其他txt/docx文件
    if success_count < max_files:
        for file_path in folder.glob("*"):
            if success_count >= max_files:
                break
            if not file_path.is_file():
                continue
            file_name = file_path.name
            if file_name.startswith('.~') or file_name.startswith('~$'):
                continue
            if file_path in loaded_files:
                continue
            if file_path.suffix not in ['.txt', '.docx']:
                continue

            content = ""
            try:
                if file_path.suffix == '.txt':
                    content = read_txt_file(str(file_path))
                elif file_path.suffix == '.docx':
                    content = read_docx_file(str(file_path))
                else:
                    continue

                if content and len(content.strip()) > 10:
                    documents.append({
                        "content": content,
                        "source": file_name,
                        "path": str(file_path)
                    })
                    loaded_files.append(file_path)
                    success_count += 1
                    print('.', end='', flush=True)
            except Exception:
                pass

    print(f" ✓ ({success_count}个核心文件)")
    return documents


def build_knowledge_base(api_key: str, folder_path: str = "./ku"):
    """构建向量知识库（使用优化的TradingLossRAG）"""
    global TRADING_RAG

    print("📚 正在初始化知识库...")
    TRADING_RAG = TradingLossRAG(api_key=api_key, folder_path=folder_path)

    if not TRADING_RAG.build_enhanced_index():
        print("❌ 知识库初始化失败")
        TRADING_RAG = None
        return None

    print("✅ 知识库初始化完成！")
    return TRADING_RAG


def get_limit_up_data_by_date(date_str: str) -> set:
    """获取指定日期的涨停股代码集合

    参数：
    - date_str: 日期字符串，格式如 '20260323'

    返回：涨停股代码集合（不含sh/sz/bj前缀）
    """
    try:
        import os
        cache_dir = './data/limit_up_history'
        file_path = os.path.join(cache_dir, f'{date_str}.json')

        if not os.path.exists(file_path):
            return set()

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        codes = set()
        for stock in data.get('stocks', []):
            # 兼容两种数据格式：新格式有'code'字段，旧格式从'代码'字段提取
            code = stock.get('code', '')
            if not code:
                # 尝试从'代码'字段提取（可能包含sh/sz/bj前缀）
                full_code = stock.get('代码', '')
                code = full_code.replace('sh', '').replace('sz', '').replace('bj', '')
            if code:
                codes.add(code)

        return codes

    except Exception as e:
        return set()


def calculate_continuous_limit_up_days_from_history(symbol: str) -> int:
    """利用涨停历史数据计算连板天数（替代AKShare）

    参数：
    - symbol: 股票代码（如 '000001'）

    返回：连续涨停天数
    """
    from datetime import datetime, timedelta

    try:
        # 检查缓存
        if symbol in _BOARD_DAYS_CACHE:
            return _BOARD_DAYS_CACHE[symbol]

        # 获取所有可用的历史涨停数据日期（最近10天）
        import os
        cache_dir = './data/limit_up_history'
        today = datetime.now()

        # 收集所有可用的交易日文件
        available_dates = []
        for i in range(10):  # 检查最近10天
            date_obj = today - timedelta(days=i)
            if date_obj.weekday() >= 5:  # 跳过周末
                continue
            date_str = date_obj.strftime('%Y%m%d')
            file_path = os.path.join(cache_dir, f'{date_str}.json')
            if os.path.exists(file_path):
                available_dates.append(date_str)

        # 按日期降序排列（从最近到最远）
        available_dates.sort(reverse=True)

        if not available_dates:
            return 0

        # 从最近一天开始检查连续涨停
        continuous_days = 0

        for date_str in available_dates:
            limit_up_codes = get_limit_up_data_by_date(date_str)

            if symbol in limit_up_codes:
                continuous_days += 1
            else:
                # 遇到第一个非涨停就停止（因为已经按日期降序）
                break

        # 缓存结果
        _BOARD_DAYS_CACHE[symbol] = continuous_days
        return continuous_days

    except Exception as e:
        return 0


def fetch_historical_kline(symbol: str, days: int = 10):
    """获取股票历史K线数据（使用AKShare）

    参数：
    - symbol: 股票代码（如 '000001' 或 '001896'）
    - days: 获取最近N天的数据

    返回：DataFrame，包含日期、开盘、收盘、最高、最低、成交量、涨跌幅等
    """
    if not HAS_AKSHARE:
        return pd.DataFrame()

    try:
        # 使用akshare获取历史数据
        # 计算起始日期
        end_date = pd.Timestamp.now().strftime('%Y%m%d')
        start_date = (pd.Timestamp.now() - pd.Timedelta(days=days*2)).strftime('%Y%m%d')

        # 调用akshare接口
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq"  # 前复权
        )

        if df.empty:
            return pd.DataFrame()

        # 检查返回的列名，可能是中文也可能是英文
        # akshare返回的列名可能是: '日期', '开盘', '收盘', '最高', '最低', '成交量', '涨跌幅'
        # 或者是: 'date', 'open', 'close', 'high', 'low', 'volume', 'pct_chg'

        # 如果列名是英文，映射为中文
        english_to_chinese = {
            'date': '日期',
            'open': '开盘价',
            'close': '收盘价',
            'high': '最高价',
            'low': '最低价',
            'volume': '成交量',
            'amount': '成交金额',
            'pct_chg': '涨跌幅',
            'chg': '涨跌额',
            'turnover': '换手率'
        }

        # 如果列名中包含英文，进行映射
        if any(col in english_to_chinese for col in df.columns):
            df = df.rename(columns=english_to_chinese)

        # 统一列名（确保中文列名存在）
        column_mapping = {
            '日期': '日期',
            '开盘': '开盘价',
            '收盘': '收盘价',
            '最高': '最高价',
            '最低': '最低价',
            '成交量': '成交量',
            '成交额': '成交金额',
            '涨跌幅': '涨跌幅',
            '涨跌额': '涨跌额',
            '换手率': '换手率'
        }
        df = df.rename(columns=column_mapping)

        # 转换日期格式
        df['日期'] = pd.to_datetime(df['日期'])

        # 按日期降序排列，取最近N天
        df = df.sort_values('日期', ascending=False).head(days)

        return df

    except Exception as e:
        return pd.DataFrame()


def calculate_continuous_limit_up_days(symbol: str) -> int:
    """计算股票连续涨停天数（优先使用历史数据，备用AKShare）

    参数：
    - symbol: 股票代码（如 '000001'）

    返回：连续涨停天数（0表示今天未涨停或不连板）
    """
    # 优先使用历史数据方法（更快更稳定）
    result = calculate_continuous_limit_up_days_from_history(symbol)
    if result > 0:
        return result

    # 如果历史数据方法返回0，尝试AKShare（备用方案）
    if not HAS_AKSHARE:
        return 0

    try:
        # 获取最近10天的K线数据
        df = fetch_historical_kline(symbol, days=10)

        if df.empty:
            return 0

        # 从最近一天开始往回数
        continuous_days = 0
        for _, row in df.iterrows():
            pct = row.get('涨跌幅', 0)

            # 判断是否涨停（主板10%，创业板/科创板20%，北交所30%）
            is_limit_up = False
            if abs(pct - 10) < 0.5:  # 主板涨停
                is_limit_up = True
            elif abs(pct - 20) < 0.5:  # 创业板/科创板涨停
                is_limit_up = True
            elif abs(pct - 30) < 0.5:  # 北交所涨停
                is_limit_up = True
            elif pct > 40:  # 新股或特殊情况
                is_limit_up = True

            if is_limit_up:
                continuous_days += 1
            else:
                break

        # 缓存AKShare的结果
        _BOARD_DAYS_CACHE[symbol] = continuous_days
        return continuous_days

    except Exception as e:
        return 0


def calculate_continuous_limit_up_days_with_retry(symbol: str, max_retries: int = 2) -> int:
    """带重试机制的连板计算（应对AKShare API不稳定）

    参数：
    - symbol: 股票代码
    - max_retries: 最大重试次数，默认2次

    返回：连续涨停天数
    """
    for attempt in range(max_retries + 1):
        try:
            result = calculate_continuous_limit_up_days(symbol)
            if result >= 0:  # 成功（包括0板的情况）
                return result
        except Exception:
            if attempt < max_retries:
                time.sleep(1)  # 重试前等待1秒
                continue
            return 0  # 所有重试失败，返回0
    return 0


def check_yesterday_performance(symbol: str) -> dict:
    """检查股票昨天的表现（用于判断接力效果）
    返回：包含昨天涨跌幅、是否有连板等信息
    """
    if not HAS_AKSHARE:
        return {'change': 0, 'limit_up': False}

    try:
        df = fetch_historical_kline(symbol, days=5)
        if df.empty or len(df) < 2:
            return {'change': 0, 'limit_up': False}

        # 取最近两天（昨天和今天）
        if len(df) >= 2:
            yesterday_row = df.iloc[1]
            yesterday_change = yesterday_row.get('涨跌幅', 0)

            # 判断昨天是否涨停
            is_limit_up = abs(yesterday_change - 10) < 0.5 or abs(yesterday_change - 20) < 0.5

            return {
                'change': yesterday_change,
                'limit_up': is_limit_up,
                'high': yesterday_row.get('最高价', 0),
                'close': yesterday_row.get('收盘价', 0)
            }
    except Exception:
        pass

    return {'change': 0, 'limit_up': False}


def fetch_sina_stock_data(sort_field='amount', page=1, num=100, asc=0, node='hs_a'):
    """从新浪财经获取A股数据（带重试机制）

    参数：
    - sort_field: 排序字段（'amount'=成交额, 'changepercent'=涨跌幅）
    - page: 页码
    - num: 获取数量
    - asc: 排序方式（0=降序，1=升序）
    - node: 数据节点，'hs_a'=A股, 'hsb_jr'=沪深B股, 'index_s'=综合指数等

    注意：新浪API单次最多返回80条左右数据，要获取更多需要分页
    """
    url = 'http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'

    # 添加更真实的Headers，避免被识别为爬虫
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'http://vip.stock.finance.sina.com.cn/',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }

    def _fetch_page_with_retry(page_num, max_retries=3):
        """带重试的分页请求"""
        params = {
            'page': page_num,
            'num': 80,
            'sort': sort_field,
            'asc': asc,  # 使用传入的排序参数
            'node': node  # 使用传入的node参数
        }

        for attempt in range(max_retries):
            try:
                import time
                if attempt > 0:
                    # 重试等待时间递增：2秒、4秒、6秒
                    wait_time = 2 * attempt
                    time.sleep(wait_time)

                resp = requests.get(url, params=params, headers=headers, timeout=10)

                if resp.status_code == 200:
                    data = json.loads(resp.text)
                    return data, None
                elif resp.status_code == 456:
                    # 新浪的反爬虫限流，等待后重试
                    if attempt < max_retries - 1:
                        # 限流错误等待更长时间：3秒、6秒
                        wait_time = 3 * (attempt + 1)
                        print(f"      遇到限流，等待{wait_time}秒后重试...")
                        time.sleep(wait_time)
                        continue
                    else:
                        return None, f"新浪API限流（456），请稍后重试"
                else:
                    return None, f"HTTP状态码: {resp.status_code}"

            except json.JSONDecodeError:
                return None, "API返回数据格式错误"
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    continue
                return None, f"网络请求失败: {str(e)}"

        return None, "重试次数耗尽"

    # 如果请求数量很大，自动分页获取
    if num > 80:
        all_dfs = []
        pages_needed = (num + 79) // 80  # 每页80条

        for p in range(1, min(pages_needed + 1, 64)):  # 最多63页，避免无限循环
            data, error = _fetch_page_with_retry(p)

            if error:
                if p == 1:  # 第一页就失败，抛出异常
                    raise Exception(error)
                else:
                    # 后续页失败，返回已获取的数据
                    break

            if not data or len(data) == 0:
                break

            df_page = pd.DataFrame(data)
            all_dfs.append(df_page)

            # 如果返回的数据少于80条，说明没有更多数据了
            if len(data) < 80:
                break

            # 每次分页后都添加延迟，避免限流（更保守的策略）
            import time
            import random
            # 使用随机延迟1.0-1.5秒，避免固定模式被识别
            delay = random.uniform(1.0, 1.5)
            time.sleep(delay)

        if not all_dfs:
            raise Exception("未获取到任何数据，请稍后重试")

        df = pd.concat(all_dfs, ignore_index=True)
    else:
        # 单页请求
        data, error = _fetch_page_with_retry(page)

        if error:
            raise Exception(error)

        if not data:
            raise Exception("未获取到任何数据")

        df = pd.DataFrame(data)

    # 统一处理列名映射
    column_mapping = {
        'symbol': '代码', 'name': '名称', 'trade': '最新价',
        'pricechange': '涨跌额', 'changepercent': '涨跌幅',
        'buy': '买入', 'sell': '卖出', 'settlement': '昨收',
        'open': '今开', 'high': '最高', 'low': '最低',
        'volume': '成交量', 'amount': '成交额',
        'ticktime': '时间', 'per': '市盈率', 'pb': '市净率',
        'mktcap': '总市值', 'nmc': '流通市值'
    }
    df.rename(columns=column_mapping, inplace=True)

    numeric_cols = ['最新价', '涨跌额', '涨跌幅', '昨收', '今开', '最高', '最低',
                  '成交量', '成交额', '市盈率', '市净率', '总市值', '流通市值']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df


def save_limit_up_data(df_zt):
    """保存涨停股数据到历史文件

    参数：
    - df_zt: 涨停股DataFrame
    """
    try:
        import os
        from datetime import datetime

        # 创建目录
        data_dir = './data/limit_up_history'
        os.makedirs(data_dir, exist_ok=True)

        # 获取今天日期
        today = datetime.now().strftime('%Y%m%d')
        file_path = os.path.join(data_dir, f'{today}.json')

        # 检查今天是否已经保存过
        if os.path.exists(file_path):
            # 已存在则不重复保存
            return

        # 准备数据
        stocks_list = []
        for _, row in df_zt.iterrows():
            stock_data = {
                '代码': row.get('代码', ''),
                'code': row.get('代码', '').replace('sh', '').replace('sz', '').replace('bj', ''),
                '名称': row.get('名称', ''),
                '最新价': float(row.get('最新价', 0)) if pd.notna(row.get('最新价')) else 0,
                '涨跌额': float(row.get('涨跌额', 0)) if pd.notna(row.get('涨跌额')) else 0,
                '涨跌幅': float(row.get('涨跌幅', 0)) if pd.notna(row.get('涨跌幅')) else 0,
                '买入': str(row.get('买入', '')),
                '卖出': str(row.get('卖出', '')),
                '昨收': float(row.get('昨收', 0)) if pd.notna(row.get('昨收')) else 0,
                '今开': float(row.get('今开', 0)) if pd.notna(row.get('今开')) else 0,
                '最高': float(row.get('最高', 0)) if pd.notna(row.get('最高')) else 0,
                '最低': float(row.get('最低', 0)) if pd.notna(row.get('最低')) else 0,
                '成交量': int(row.get('成交量', 0)) if pd.notna(row.get('成交量')) else 0,
                '成交额': float(row.get('成交额', 0)) if pd.notna(row.get('成交额')) else 0,
                '时间': str(row.get('时间', '')),
                '市盈率': float(row.get('市盈率', 0)) if pd.notna(row.get('市盈率')) else 0,
                '市净率': float(row.get('市净率', 0)) if pd.notna(row.get('市净率')) else 0,
                '总市值': float(row.get('总市值', 0)) if pd.notna(row.get('总市值')) else 0,
                '流通市值': float(row.get('流通市值', 0)) if pd.notna(row.get('流通市值')) else 0,
                'turnoverratio': float(row.get('换手率', 0)) if pd.notna(row.get('换手率')) else 0,
                '换手率': float(row.get('换手率', 0)) if pd.notna(row.get('换手率')) else 0,
                '成交额(亿)': float(row.get('成交额(亿)', 0)) if pd.notna(row.get('成交额(亿)')) else 0,
            }
            stocks_list.append(stock_data)

        # 构建保存数据
        save_data = {
            'date': today,
            'count': len(stocks_list),
            'stocks': stocks_list
        }

        # 保存为JSON
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

        print(f"✅ 涨停股数据已保存: {file_path}")

    except Exception as e:
        # 保存失败不影响主流程
        print(f"⚠️  保存数据失败: {e}")


def fetch_limit_up_stocks():
    """获取涨停板数据（从新浪财经筛选，过滤ST股）"""
    try:
        # 获取涨幅排名数据
        df = fetch_sina_stock_data(sort_field='changepercent', num=500)

        # 筛选涨停股（涨幅>=9.5%）
        df_zt = df[df['涨跌幅'] >= 9.5].copy()

        if df_zt.empty:
            return pd.DataFrame()

        # 过滤ST股票（名称中包含ST、*ST、S*ST、SST等）
        df_zt = df_zt[~df_zt['名称'].str.contains('ST|st|退', na=False)]

        # 添加换手率和成交额（亿）
        df_zt['换手率'] = 0  # 新浪API暂无换手率数据
        df_zt['成交额(亿)'] = df_zt['成交额'] / 100000000

        # 自动保存数据到历史文件
        save_limit_up_data(df_zt)

        return df_zt

    except Exception as e:
        raise Exception(f"获取涨停板数据失败: {str(e)}")


def fetch_board_ranking():
    """获取板块涨幅排名（简化版，基于涨停股统计）"""
    try:
        # 暂时返回简化的板块信息
        # TODO: 实现更完善的板块数据获取
        return pd.DataFrame({
            '板块名称': ['电力', 'AI算力', 'PCB', '新能源', '半导体'],
            '涨跌幅': [0, 0, 0, 0, 0],  # 需要实际计算
            '领涨股': ['', '', '', '', ''],
            '领涨股涨幅': [0, 0, 0, 0, 0]
        })
    except Exception as e:
        raise Exception(f"获取板块数据失败: {str(e)}")


def analyze_continuous_limit_up():
    """分析连板股梯队（查询所有非ST涨停股）- 增强版"""
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        from datetime import datetime
        import os

        # 检查今日缓存（缩短到30分钟，避免盘中数据过时）
        today = datetime.now().strftime('%Y%m%d')
        cache_file = f'./data/limit_up_history/{today}_board_cache.json'

        # 如果缓存存在且不超过30分钟，直接使用缓存
        if os.path.exists(cache_file):
            try:
                cache_age = time.time() - os.path.getmtime(cache_file)
                if cache_age < 1800:  # 30分钟
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_data = json.load(f)
                    return cached_data['summary']
            except:
                pass

        df_zt = fetch_limit_up_stocks()

        if df_zt.empty:
            return "今日暂无涨停股数据"

        # 按成交额排序
        df_zt_sorted = df_zt.sort_values('成交额(亿)', ascending=False)
        total_count = len(df_zt_sorted)

        # 关键修改：分析前80只（覆盖更多股票，防止错过新高板）
        results = []
        board_stats = {}
        max_board = 1
        max_board_stocks = []
        failed_count = 0

        # 准备前80只股票数据
        stock_data = []
        for idx, (_, row) in enumerate(df_zt_sorted.head(80).iterrows(), 1):
            name = row['名称']
            code = row.get('代码', '').replace('sh', '').replace('sz', '').replace('bj', '')
            pct = row['涨跌幅']
            amount = row.get('成交额(亿)', 0)
            stock_data.append((idx, name, code, pct, amount))

        # 并发处理
        def process_stock(stock_info):
            idx, name, code, pct, amount = stock_info
            # 增加重试次数，避免API不稳定导致全0
            board_days = calculate_continuous_limit_up_days_with_retry(code, max_retries=3)
            if board_days > 0:
                board_label = f"{board_days}板"
            else:
                board_label = "首板"
                board_days = 0
            return (idx, name, code, pct, amount, board_days, board_label)

        results_dict = {}
        with ThreadPoolExecutor(max_workers=50) as executor:
            future_to_stock = {executor.submit(process_stock, stock): stock for stock in stock_data}
            for future in as_completed(future_to_stock):
                try:
                    idx, name, code, pct, amount, board_days, board_label = future.result()
                    results_dict[idx] = {
                        'text': f"{name}({code}) {pct:.2f}% 成交额{amount:.2f}亿 [{board_label}]",
                        'board_days': board_days,
                        'name': name,
                        'amount': amount
                    }
                    if board_days > 0:
                        board_stats[board_days] = board_stats.get(board_days, 0) + 1
                        if board_days > max_board:
                            max_board = board_days
                            max_board_stocks = [name]
                        elif board_days == max_board and max_board > 1:
                            max_board_stocks.append(name)
                    else:
                        failed_count += 1
                except Exception as e:
                    idx, name, code, pct, amount = future_to_stock[future]
                    print(f"股票 {name} 分析失败: {e}")
                    results_dict[idx] = {
                        'text': f"{name}({code}) {pct:.2f}% 成交额{amount:.2f}亿 [首板]",
                        'board_days': 0,
                        'name': name,
                        'amount': amount
                    }
                    failed_count += 1

        results = [results_dict[i+1]['text'] for i in range(len(stock_data))]

        # 构建简洁summary
        analyzed_count = len([r for r in results if r])
        summary = f"📊 今日涨停股共 {total_count} 只（已过滤ST股），已分析成交额前{analyzed_count}只\n"

        if failed_count > 0:
            summary += f"⚠️  注意: {failed_count}只股票可能是API获取失败被标记为首板\n"

        if board_stats:
            summary += f"\n🔥 最高板: {max_board}板"
            if max_board > 1 and max_board_stocks:
                summary += f"（{', '.join(max_board_stocks[:5])}）"
            summary += "\n"
            summary += f"📈 连板统计: " + ", ".join([f"{k}板×{v}只" for k, v in sorted(board_stats.items(), reverse=True)]) + "\n"

        # 按连板分组
        high_boards = {}
        first_boards = []
        for result in results:
            if "[首板]" in result:
                first_boards.append(result)
            else:
                import re
                match = re.search(r'\[(\d+)板\]', result)
                if match:
                    board_num = int(match.group(1))
                    if board_num not in high_boards:
                        high_boards[board_num] = []
                    high_boards[board_num].append(result)

        # 显示连板
        summary += "\n💹 涨停梯队：\n\n"
        for board_num in sorted(high_boards.keys(), reverse=True):
            stocks = high_boards[board_num]
            # �成交额从高到低排序
            stocks_sorted = sorted(stocks, key=lambda x: float(x.split('成交额')[1].split('亿')[0]) if '成交额' in x else 0, reverse=True)
            summary += f"【{board_num}板】({len(stocks)}只)：\n"
            for stock in stocks_sorted[:15]:  # 每个梯队最多显示15只
                summary += f"  {stock}\n"
            if len(stocks_sorted) > 15:
                summary += f"  ... 还有{len(stocks_sorted)-15}只\n"
            summary += "\n"

        # 显示首板前20只
        if first_boards:
            # 按成交额从高到低排序
            first_boards_sorted = sorted(first_boards, key=lambda x: float(x.split('成交额')[1].split('亿')[0]) if '成交额' in x else 0, reverse=True)
            summary += f"【首板】({len(first_boards)}只，显示前20只)：\n"
            for stock in first_boards_sorted[:20]:
                summary += f"  {stock}\n"
            if len(first_boards_sorted) > 20:
                summary += f"  ... 还有{len(first_boards_sorted)-20}只\n"

        # 保存缓存
        try:
            os.makedirs('./data/limit_up_history', exist_ok=True)
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({'summary': summary, 'timestamp': time.time()}, f, ensure_ascii=False, indent=2)
        except:
            pass

        return summary

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"❌ 分析连板失败: {str(e)}"


# -----------------------------
# 工具函数
# -----------------------------
@tool
def search_knowledge(query: str, top_k: int = 15) -> str:
    """
    从知识库中搜索相关的交易知识和经验。
    适用于回答交易策略、技术分析、情绪判断、选股方法等问题。

    参数：
    - query: 搜索查询，如"如何判断情绪周期"、"打板战法"、"龙头股选择"
    - top_k: 返回最相关的前几条结果，默认15（内部优化，自动匹配文件）

    返回：相关知识的文本内容
    """
    global TRADING_RAG

    if TRADING_RAG is None:
        return "知识库未初始化，无法搜索"

    try:
        # 使用优化的RAG系统，自动文件名匹配 + 增强Prompt
        result = TRADING_RAG.search_with_reasoning(query)
        return result
    except Exception as e:
        return f"搜索失败: {str(e)}"


@tool
def get_market_overview() -> str:
    """获取A股市场概览"""
    try:
        df = fetch_sina_stock_data(num=200)
        cols = ["代码", "名称", "最新价", "涨跌幅", "成交量", "成交额", "总市值", "流通市值"]
        available_cols = [col for col in cols if col in df.columns]
        return df[available_cols].to_csv(index=False)
    except Exception as e:
        return f"获取市场数据失败: {str(e)}"


@tool
def get_top_stocks_by_turnover(top_n: int = 10) -> str:
    """获取今天成交额最大的前N只股票"""
    try:
        df = fetch_sina_stock_data(sort_field='amount', num=top_n)
        cols = ["代码", "名称", "最新价", "涨跌幅", "成交量", "成交额", "总市值"]
        available_cols = [col for col in cols if col in df.columns]
        return df[available_cols].to_csv(index=False)
    except Exception as e:
        return f"获取成交额排名失败: {str(e)}"


@tool
def get_top_stocks_by_pct_change(top_n: int = 10, ascending: bool = False) -> str:
    """获取今天涨跌幅最大的前N只股票"""
    try:
        df = fetch_sina_stock_data(sort_field='changepercent', num=top_n)
        if ascending:
            df = df.iloc[::-1]
        cols = ["代码", "名称", "最新价", "涨跌幅", "成交量", "成交额"]
        available_cols = [col for col in cols if col in df.columns]
        return df[available_cols].to_csv(index=False)
    except Exception as e:
        return f"获取涨跌幅排名失败: {str(e)}"


@tool
def get_stock_quote(symbol: str) -> str:
    """获取指定股票的最新行情

    参数：
    - symbol: 股票代码（如"300476"）或股票名称（如"胜宏科技"）

    返回：股票的详细行情信息
    """
    try:
        # 减少请求量，避免API限流（800只股票已经覆盖大部分活跃股票）
        df = fetch_sina_stock_data(num=800)

        if df.empty:
            return "无法获取市场数据"

        if '代码' not in df.columns:
            return "数据格式错误"

        df['纯代码'] = df['代码'].str.replace('sh', '').str.replace('sz', '').str.replace('bj', '')

        # 先尝试按代码查找
        row = df[df['纯代码'] == symbol]

        # 如果按代码找不到，尝试按名称查找
        if row.empty:
            row = df[df['名称'].str.contains(symbol, case=False, na=False)]

        if row.empty or len(row) == 0:
            return f"未找到 {symbol} 的行情数据"

        # 如果找到多个，取第一个
        r = row.iloc[0]

        # 返回格式化的文本
        result = f"【{r.get('名称', '')}({r.get('纯代码', '')})】\n"
        result += f"最新价: {r.get('最新价', 0)}元\n"
        result += f"涨跌幅: {r.get('涨跌幅', 0):.2f}%\n"
        result += f"成交额: {float(r.get('成交额', 0))/100000000:.2f}亿元\n"
        result += f"总市值: {float(r.get('总市值', 0))/100000000:.2f}亿元\n"
        result += f"今开: {r.get('今开', 0)}元, 最高: {r.get('最高', 0)}元, 最低: {r.get('最低', 0)}元"

        return result
    except Exception as e:
        return f"获取行情失败: {str(e)}"


@tool
def search_stock_by_name(keyword: str) -> str:
    """根据股票名称关键词搜索股票

    返回：股票的基本信息（代码、名称、价格、涨跌幅、成交额）
    """
    try:
        # 先尝试从成交额前800只中搜索（一般的股票都在这个范围内）
        df = fetch_sina_stock_data(num=800)

        if df.empty or '名称' not in df.columns:
            return "无法获取市场数据，请稍后重试"

        df_filtered = df[df["名称"].str.contains(keyword, case=False, na=False)]

        if df_filtered.empty:
            return f"未找到包含'{keyword}'的股票"

        # 格式化为易读的文本
        results = []
        for idx, row in df_filtered.iterrows():
            code = row.get('代码', '')
            name = row.get('名称', '')
            price = row.get('最新价', 0)
            pct = row.get('涨跌幅', 0)
            amount = row.get('成交额', 0) / 100000000  # 转换为亿
            results.append(f"{name}({code}): 价格{price}元, 涨跌幅{pct:.2f}%, 成交额{amount:.2f}亿元")

        return f"找到{len(results)}只股票：\n" + "\n".join(results)
    except Exception as e:
        return f"搜索股票失败: {str(e)}"


@tool
def get_limit_up_stocks(top_n: int = 30) -> str:
    """获取今日涨停股票列表

    参数：
    - top_n: 返回前N只涨停股，默认30

    返回：涨停股详细信息，包括代码、名称、涨幅、成交额、换手率等
    """
    try:
        df = fetch_limit_up_stocks()
        if df.empty:
            return "今日暂无涨停股数据"

        df = df.head(top_n)
        # 检查是否已有成交额(亿)列
        if '成交额(亿)' not in df.columns and '成交额' in df.columns:
            df['成交额(亿)'] = df['成交额'] / 100000000

        cols = ["代码", "名称", "涨跌幅", "成交额(亿)", "最新价"]
        available_cols = [col for col in cols if col in df.columns]
        return df[available_cols].to_csv(index=False)
    except Exception as e:
        return f"获取涨停股失败: {str(e)}"


@tool
def get_board_ranking(top_n: int = 20) -> str:
    """获取板块涨幅排名

    参数：
    - top_n: 返回前N个板块，默认20

    返回：板块涨幅排名，包括板块名称、涨跌幅、领涨股等信息
    """
    try:
        df = fetch_board_ranking()
        if df.empty:
            return "板块数据获取失败"

        df = df.head(top_n)
        cols = ["板块名称", "涨跌幅", "领涨股", "领涨股涨幅"]
        return df[cols].to_csv(index=False)
    except Exception as e:
        return f"获取板块排名失败: {str(e)}"


@tool
def analyze_market_sentiment() -> str:
    """分析当前市场情绪（深度版本）

    分析维度：
    1. 最高板反馈 - 市场高度空间
    2. 接力梯队完整度 - 连板分布健康度
    3. 连板赚钱效应 - 高位接力表现
    4. 大成交赚钱效应 - 热门股赚钱能力
    5. 跌停风险 - 市场亏钱效应

    返回：综合市场情绪报告
    """
    return _analyze_market_sentiment_impl()


def _analyze_market_sentiment_impl() -> str:
    """内部实现函数（不带@tool装饰器，可以被其他函数直接调用）"""
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from datetime import datetime
        import os

        # 检查今日缓存
        today = datetime.now().strftime('%Y%m%d')
        cache_file = f'./data/limit_up_history/{today}_sentiment_cache.json'

        if os.path.exists(cache_file):
            try:
                cache_age = time.time() - os.path.getmtime(cache_file)
                if cache_age < 1800:  # 缓存30分钟
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_data = json.load(f)
                    return cached_data['report']
            except:
                pass

        # ============ 1. 基础数据获取 ============
        # 获取涨停数据
        df_zt = fetch_limit_up_stocks()

        # 获取跌停数据（涨幅<-9.5%）
        df_all = fetch_sina_stock_data(num=5000, sort_field='changepercent')
        df_dt = df_all[df_all['涨跌幅'] <= -9.5] if not df_all.empty else pd.DataFrame()

        # 基础统计
        zt_count = len(df_zt) if not df_zt.empty else 0
        dt_count = len(df_dt) if not df_dt.empty else 0

        if zt_count == 0:
            return "今日暂无涨停股数据，无法分析情绪"

        # ============ 2. 获取热股榜数据（大成交赚钱效应） ============
        df_hot = fetch_sina_stock_data(sort_field='amount', num=100)

        # ============ 3. 分析连板梯队（并发获取前80只） ============
        df_zt_sorted = df_zt.sort_values('成交额(亿)', ascending=False)
        top_80_stocks = df_zt_sorted.head(80)

        stock_data = []
        for _, row in top_80_stocks.iterrows():
            name = row['名称']
            code = row.get('代码', '').replace('sh', '').replace('sz', '').replace('bj', '')
            pct = row['涨跌幅']
            amount = row.get('成交额(亿)', 0)
            stock_data.append((name, code, pct, amount))

        board_stats = {}
        yesterday_limits_count = 0
        today_limits_up_success = 0

        def process_stock_for_sentiment(stock_info):
            name, code, pct, amount = stock_info
            # 获取连板天数（增加重试次数）
            board_days = calculate_continuous_limit_up_days_with_retry(code, max_retries=2)

            # 获取昨天表现（判断接力）
            yesterday_info = check_yesterday_performance(code)

            return (name, code, pct, amount, board_days, yesterday_info)

        results_dict = {}
        with ThreadPoolExecutor(max_workers=80) as executor:
            future_to_stock = {executor.submit(process_stock_for_sentiment, stock): stock for stock in stock_data}
            for future in as_completed(future_to_stock):
                try:
                    name, code, pct, amount, board_days, yesterday_info = future.result()

                    board_label = f"{board_days}板" if board_days > 0 else "首板"
                    results_dict[code] = {
                        'name': name,
                        'pct': pct,
                        'amount': amount,
                        'board_days': board_days,
                        'board_label': board_label,
                        'yesterday_limit_up': yesterday_info['limit_up'],
                        'yesterday_change': yesterday_info['change']
                    }

                    # 统计连板分布
                    if board_days > 0:
                        board_stats[board_days] = board_stats.get(board_days, 0) + 1

                    # 统计昨天涨停、今天继续涨停的（接力成功）
                    if yesterday_info['limit_up'] and pct >= 9.5:
                        today_limits_up_success += 1

                    # 统计昨天涨停数量
                    if yesterday_info['limit_up']:
                        yesterday_limits_count += 1

                except:
                    pass

        # ============ 4. 计算各维度得分 ============

        # ===== 维度1: 最高板反馈得分 (0-100) =====
        max_board = max(board_stats.keys()) if board_stats else 1
        max_board_score = min(100, max_board * 10)  # 最高板*10，最高100分
        # 最高板数量加分
        max_board_count = board_stats.get(max_board, 0)
        max_board_score += min(20, max_board_count * 10)  # 最高板越多，额外加分

        # ===== 维度2: 接力梯队完整度得分 (0-100) =====
        # 检查梯队是否连续（如7板到2板都存在）
        board_levels = sorted(board_stats.keys(), reverse=True)
        relay_score = 0
        if board_levels:
            # 统计连续梯队数量
            continuous_count = 0
            for i in range(len(board_levels)):
                if i == 0 or board_levels[i-1] - board_levels[i] == 1:
                    continuous_count += 1
                else:
                    break
            relay_score = min(100, continuous_count * 20)  # 每个连续梯队20分

            # 2板以上数量加分
            high_board_count = sum([v for k, v in board_stats.items() if k >= 2])
            relay_score += min(30, high_board_count * 5)

        # ===== 维度3: 连板赚钱效应得分 (0-100) =====
        # 接力成功率 = 今天涨停且昨天涨停的数量 / 昨天涨停的数量（在分析样本中）
        relay_success_rate = 0
        if yesterday_limits_count > 0:
            relay_success_rate = today_limits_up_success / yesterday_limits_count
        board_profit_score = min(100, relay_success_rate * 100)

        # 高位连板数量加分
        board_3plus_count = sum([v for k, v in board_stats.items() if k >= 3])
        board_profit_score += min(30, board_3plus_count * 10)

        # ===== 维度4: 大成交赚钱效应得分 (0-100) =====
        # 热股榜前50只的平均涨幅
        top_50_hot = df_hot.head(50)
        avg_change_hot = top_50_hot['涨跌幅'].mean() if not top_50_hot.empty else 0
        volume_profit_score = min(100, avg_change_hot * 5)  # 平均涨幅*5

        # 热股榜涨停数量
        hot_limit_count = (top_50_hot['涨跌幅'] >= 9.5).sum()
        volume_profit_score += min(30, hot_limit_count * 6)

        # 涨停股中大成交额（>5亿）比例
        big_amount_zt = df_zt[df_zt['成交额(亿)'] >= 5]
        big_amount_ratio = len(big_amount_zt) / zt_count if zt_count > 0 else 0
        volume_profit_score += min(30, big_amount_ratio * 100)

        # ===== 维度5: 风险因子 (扣分) =====
        risk_penalty = 0
        # 跌停股过多扣分
        if dt_count > 20:
            risk_penalty += 10
        if dt_count > 50:
            risk_penalty += 20
        if dt_count > 100:
            risk_penalty += 30

        # 涨停股比例过低扣分
        total_stocks = len(df_all) if not df_all.empty else 5000
        zt_ratio = zt_count / total_stocks
        if zt_ratio < 0.005:  # 涨停股占比<0.5%
            risk_penalty += 30

        # ============ 5. 加载昨日数据用于对比 ============
        from datetime import date, timedelta

        # 计算昨日日期
        today_date = datetime.now().date()
        yesterday = today_date - timedelta(days=1)
        # 检查昨日是否为交易日（简化判断，只检查周六日）
        while yesterday.weekday() >= 5:  # 5=周六, 6=周日
            yesterday = yesterday - timedelta(days=1)
        yesterday_str = yesterday.strftime('%Y%m%d')

        yesterday_cache = None
        yesterday_cache_file = f'./data/limit_up_history/{yesterday_str}_sentiment_cache.json'
        if os.path.exists(yesterday_cache_file):
            try:
                with open(yesterday_cache_file, 'r', encoding='utf-8') as f:
                    yesterday_cache = json.load(f)
            except:
                pass

        # 从昨日的报告中提取数据
        yesterday_score = 0
        yesterday_grade = "无数据"
        yesterday_zt_count = 0
        yesterday_max_board = 0
        yesterday_hot_avg = 0

        if yesterday_cache:
            yesterday_score = yesterday_cache.get('score', 0)
            yesterday_grade = yesterday_cache.get('grade', '无')
            # 优先从缓存结构化数据中读取，如果没有则尝试从报告文本解析
            yesterday_zt_count = yesterday_cache.get('zt_count', 0)
            yesterday_max_board = yesterday_cache.get('max_board', 0)
            yesterday_hot_avg = yesterday_cache.get('avg_change_hot', 0)

            # 如果缓存没有结构化数据，尝试从旧格式的报告中提取
            if yesterday_zt_count == 0 or yesterday_max_board == 0 or yesterday_hot_avg == 0:
                yesterday_report = yesterday_cache.get('report', '')
                import re
                zt_match = re.search(r'涨停股:\s*(\d+)只', yesterday_report)
                if zt_match:
                    yesterday_zt_count = int(zt_match.group(1))

                max_board_match = re.search(r'最高(\d+)板', yesterday_report)
                if max_board_match:
                    yesterday_max_board = int(max_board_match.group(1))

                hot_avg_match = re.search(r'热股榜平均涨幅([+-]?\d+\.?\d*)%', yesterday_report)
                if hot_avg_match:
                    yesterday_hot_avg = float(hot_avg_match.group(1))

        # ============ 6. 综合计算 ============
        # 加权综合得分
        total_score = (max_board_score * 0.2 +  # 最高板20%
                      relay_score * 0.25 +       # 梯队完整度25%
                      board_profit_score * 0.25 +  # 连板赚钱效应25%
                      volume_profit_score * 0.3)   # 大成交赚钱效应30%
        total_score = max(0, min(100, total_score - risk_penalty))

        # 综合评级
        grade = "极弱"
        if total_score >= 85:
            grade = "极强"
        elif total_score >= 70:
            grade = "强"
        elif total_score >= 55:
            grade = "偏强"
        elif total_score >= 40:
            grade = "中性偏强"
        elif total_score >= 25:
            grade = "中性"
        elif total_score >= 10:
            grade = "偏弱"
        else:
            grade = "极弱"

        # ============ 7. 构建详细报告 ============
        report = f"{'='*70}\n"
        report += "📊 深度市场情绪分析报告\n"
        report += f"{'='*70}\n\n"

        # 昨日对比模块
        report += f"【昨日对比】📅 {yesterday_str}\n"
        if yesterday_cache:
            # 计算变化
            score_change = total_score - yesterday_score
            score_trend = "📈" if score_change > 0 else "📉" if score_change < 0 else "➡️"

            zt_change = zt_count - yesterday_zt_count
            zt_trend = "📈" if zt_change > 0 else "📉" if zt_change < 0 else "➡️"

            max_board_change = ""
            if max_board > yesterday_max_board:
                max_board_change = "📈 高度提升"
            elif max_board < yesterday_max_board:
                max_board_change = "📉 高度下降"
            else:
                max_board_change = "➡️ 持平"

            hot_avg_change = avg_change_hot - yesterday_hot_avg
            hot_trend = "📈" if hot_avg_change > 0 else "📉" if hot_avg_change < 0 else "➡️"

            report += f"  综合得分: {yesterday_score:.1f} → {total_score:.1f} {score_trend} ({score_change:+.1f})\n"
            report += f"  市场评级: {yesterday_grade} → {grade}\n"
            report += f"  涨停数量: {yesterday_zt_count}只 → {zt_count}只 {zt_trend} ({zt_change:+d}只)\n"
            report += f"  最高连板: {yesterday_max_board}板 → {max_board}板 {max_board_change}\n"
            report += f"  热股平均: {yesterday_hot_avg:+.2f}% → {avg_change_hot:+.2f}% {hot_trend}\n"

            # 市场判断
            if score_change >= 10:
                report += f"  💡 市场明显转强\n"
            elif score_change >= 5:
                report += f"  💡 市场小幅走强\n"
            elif score_change <= -10:
                report += f"  ⚠️  市场明显转弱\n"
            elif score_change <= -5:
                report += f"  ⚠️  市场小幅走弱\n"
            else:
                report += f"  ➡️ 市场保持平稳\n"
        else:
            report += f"  ⚠️  无昨日数据，无法对比\n"
        report += "\n"

        # 综合评级
        report += f"【综合评级】{grade} (得分: {total_score:.1f}/100)\n\n"

        # 市场概览
        report += f"【市场概况】\n"
        report += f"  涨停股: {zt_count}只  |  跌停股: {dt_count}只\n"
        report += f"  赚钱效应: {'强' if zt_count > dt_count * 2 else '弱' if dt_count > zt_count else '中等'}\n\n"

        # 分维度得分
        report += f"【维度得分分析】\n"
        report += f"  🏆 最高板反馈: {max_board_score:.1f}/100 | 最高{max_board}板 ×{max_board_count}只\n"
        report += f"  📊 接力梯队: {relay_score:.1f}/100 | " + ", ".join([f"{k}板×{v}" for k, v in sorted(board_stats.items(), reverse=True)]) + "\n"
        report += f"  💹 连板赚钱: {board_profit_score:.1f}/100 | 接力成功率{relay_success_rate*100:.1f}% ({today_limits_up_success}/{yesterday_limits_count})\n"
        report += f"  💰 大成交赚钱: {volume_profit_score:.1f}/100 | 热股榜平均涨幅{avg_change_hot:+.2f}% | 涨停{hot_limit_count}只\n"
        if risk_penalty > 0:
            report += f"  ⚠️  风险扣分: -{risk_penalty:.1f}\n"
        report += "\n"

        # 最高板分析
        report += f"【最高板反馈】\n"
        max_board_stocks = [(k, code, v['name'], v['amount']) for code, v in results_dict.items()
                           for k in [v['board_days']] if k == max_board and k > 1]
        if max_board_stocks:
            report += f"  最高{max_board}板({len(max_board_stocks)}只):\n"
            for _, code, name, amount in max_board_stocks[:5]:
                report += f"    • {name}({code}) 成交{amount:.2f}亿\n"
        else:
            report += f"  当前最高为{max_board}板（连板梯队偏弱）\n"
        report += "\n"

        # 接力梯队分析
        report += f"【接力梯队完整度】\n"
        # 检查梯队连续性
        missing_boards = []
        for i in range(2, max_board):
            if i not in board_stats:
                missing_boards.append(i)
        if missing_boards:
            report += f"  ⚠️  梯队断层: 缺失{', '.join(map(str, missing_boards))}板\n"
        else:
            report += f"  ✅ 梯队完整: {max_board}板到2板无断层\n"
        report += f"  2板以上共{sum([v for k, v in board_stats.items() if k >= 2])}只\n\n"

        # 连板赚钱效应
        report += f"【连板赚钱效应】\n"
        if 3 in board_stats or 4 in board_stats or 5 in board_stats:
            report += f"  高位连板: "
            high_boards = sorted([k for k in board_stats.keys() if k >= 3], reverse=True)
            report += ", ".join([f"{k}板×{board_stats[k]}" for k in high_boards])
            report += "\n"
        if yesterday_limits_count > 0:
            report += f"  昨日涨停今日继续涨停: {today_limits_up_success}只 ({relay_success_rate*100:.1f}%)\n"
            if relay_success_rate >= 0.7:
                report += f"  💡 接力意愿强，赚钱效应好\n"
            elif relay_success_rate >= 0.4:
                report += f"  💡 接力意愿一般\n"
            else:
                report += f"  ⚠️  接力意愿弱，需谨慎\n"
        report += "\n"

        # 大成交赚钱效应
        report += f"【大成交赚钱效应】\n"
        if not top_50_hot.empty:
            top10_hot = top_50_hot.head(10)
            report += f"  热股榜TOP10:\n"
            for idx, row in top10_hot.iterrows():
                name = row['名称']
                code = row.get('代码', '')
                pct = row['涨跌幅']
                amount = row.get('成交额', 0) / 1e8
                report += f"    {idx+1}. {name}({code}) {pct:+.2f}% 成交{amount:.2f}亿\n"

        if avg_change_hot > 5:
            report += f"\n  💡 热门股表现优异，赚钱效应强\n"
        elif avg_change_hot > 2:
            report += f"\n  💡 热门股表现一般\n"
        else:
            report += f"\n  ⚠️  热门股表现疲软\n"
        report += "\n"

        # 操作建议
        report += f"【操作建议】"
        if total_score >= 70:
            report += f"\n  ✅ 市场情绪偏强，可积极操作\n"
            report += f"     • 聚焦最强主线\n"
            report += f"     • 可考虑接力高位连板\n"
            report += f"     • 大成交额热门股是重点\n"
        elif total_score >= 40:
            report += f"\n  💡 市场情绪中性，适度参与\n"
            report += f"     • 控制仓位\n"
            report += f"     • 谨慎接力\n"
            report += f"     • 关注低位首板\n"
        else:
            report += f"\n  ⚠️  市场情绪偏弱，建议观望\n"
            report += f"     • 降低操作频率\n"
            report += f"     • 避免追高接力\n"
            report += f"     • 等待情绪回暖\n"

        report += f"\n{'='*70}\n"

        # 保存缓存
        try:
            os.makedirs('./data/limit_up_history', exist_ok=True)
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'report': report,
                    'timestamp': time.time(),
                    'score': total_score,
                    'grade': grade,
                    'zt_count': zt_count,
                    'max_board': max_board,
                    'avg_change_hot': avg_change_hot,
                    'max_board_score': max_board_score,
                    'relay_score': relay_score,
                    'board_profit_score': board_profit_score,
                    'volume_profit_score': volume_profit_score
                }, f, ensure_ascii=False, indent=2)
        except:
            pass

        return report

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"深度市场情绪分析失败: {str(e)}"


@tool
def get_continuous_limit_up_leaders() -> str:
    """获取连板股梯队信息

    返回：
    - 最高连板股
    - 连板梯队（准确的连板天数，基于历史K线数据）
    - 首板活跃股
    """
    return analyze_continuous_limit_up()


@tool
def get_stock_history(symbol: str, days: int = 5) -> str:
    """获取股票历史K线数据

    参数：
    - symbol: 股票代码（如 '000001'）或股票名称（如 '平安银行'）
    - days: 获取最近N天的数据，默认5天

    返回：历史K线数据和连板信息
    """
    if not HAS_AKSHARE:
        return "历史数据功能不可用，请安装akshare: pip install akshare"

    try:
        # 如果输入的是股票名称，先搜索代码
        if not symbol.isdigit():
            # 减少请求量，避免API限流
            df_search = fetch_sina_stock_data(num=800)

            if df_search.empty or '名称' not in df_search.columns:
                return f"无法获取市场数据，请稍后重试"

            result = df_search[df_search['名称'].str.contains(symbol, na=False)]

            if result.empty or len(result) == 0:
                return f"未找到股票：{symbol}"

            code_full = result.iloc[0]['代码']
            symbol = code_full.replace('sh', '').replace('sz', '').replace('bj', '')
            stock_name = result.iloc[0]['名称']
        else:
            stock_name = symbol

        # 获取历史K线
        df = fetch_historical_kline(symbol, days=days)

        if df.empty:
            return f"无法获取 {stock_name}({symbol}) 的历史数据"

        # 计算连板天数
        board_days = calculate_continuous_limit_up_days(symbol)

        # 格式化输出
        result = f"【{stock_name}({symbol}) 历史数据】\n\n"

        if board_days > 0:
            result += f"🔥 连板信息: {board_days}板（连续{board_days}天涨停）\n\n"
        else:
            result += f"连板信息: 非连板股\n\n"

        result += "最近K线数据：\n"
        # 选择关键列
        key_cols = ['日期', '收盘价', '涨跌幅', '成交量', '成交金额']
        available_cols = [col for col in key_cols if col in df.columns]
        result += df[available_cols].to_string(index=False)

        return result

    except Exception as e:
        return f"获取历史数据失败: {str(e)}"


# -----------------------------
# 热股榜和赚钱效应分析工具
# -----------------------------
@tool
def get_hot_stocks_ranking(source: str = 'sina_amount', top_n: int = 20) -> str:
    """获取热股榜排行，用于判断市场赚钱效应

    参数：
    - source: 数据源，可选：
      - 'sina_amount': 新浪财经（按成交额） - 推荐
      - 'sina_change': 新浪财经（按涨跌幅）
      - 'eastmoney': 东方财富热股榜（按主力流入）
      - 'composite': 综合热度算法（多维度综合排序）
    - top_n: 获取前N只股票，默认20只

    返回：热股榜排名数据，包括代码、名称、涨跌幅、成交额等
    """
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent))
        import hot_stocks_module

        # 获取热股榜数据
        df, source_name = hot_stocks_module.get_hot_stocks(source=source, top_n=top_n)

        if df.empty:
            return f"获取热股榜失败，请稍后重试"

        # 格式化输出
        result = f"【{source_name} - 热股榜TOP{top_n}】\n\n"

        # 显示前N只股票
        cols_to_show = ['代码', '名称', '最新价', '涨跌幅', '成交额(亿)', '热度排名']
        available_cols = [col for col in cols_to_show if col in df.columns]

        result += df[available_cols].head(top_n).to_string(index=False)
        result += "\n"

        # 计算10只的平均指标
        top_10 = df.head(10)
        avg_change = top_10['涨跌幅'].mean()
        avg_amount = top_10['成交额(亿)'].mean() if '成交额(亿)' in top_10.columns else 0
        limit_up_count = (top_10['涨跌幅'] >= 9.9).sum()

        result += f"\n【前10名统计】\n"
        result += f"平均涨幅: {avg_change:.2f}%\n"
        result += f"平均成交额: {avg_amount:.2f}亿\n"
        result += f"涨停数量: {limit_up_count}只\n"

        return result

    except Exception as e:
        return f"获取热股榜失败: {str(e)}"


@tool
def analyze_profit_effect(source: str = 'sina_amount', top_n: int = 50) -> str:
    """分析市场赚钱效应，基于热股榜数据综合评估

    参数：
    - source: 数据源，可选：
      - 'sina_amount': 新浪财经（按成交额）- 推荐
      - 'sina_change': 新浪财经（按涨跌幅）
      - 'eastmoney': 东方财富热股榜
      - 'composite': 综合热度算法
    - top_n: 分析前N只热股，默认50只

    返回：赚钱效应分析报告，包括等级、描述、基础统计、成交额分析、操作建议等
    """
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent))
        import hot_stocks_module

        # 获取热股榜数据
        df, _ = hot_stocks_module.get_hot_stocks(source=source, top_n=top_n)

        if df.empty:
            return "获取热股榜数据失败，无法分析赚钱效应"

        # 分析赚钱效应
        analysis = hot_stocks_module.analyze_profit_effect(df)

        if analysis.get('status') != 'success':
            return f"赚钱效应分析失败: {analysis.get('message', '未知错误')}"

        # 格式化输出结果
        result = f"【市场赚钱效应分析】\n"
        result += f"分析时间: {analysis.get('timestamp')}\n"
        result += f"分析样本: {analysis.get('total_count')}只热股\n\n"

        # 赚钱效应评级
        profit_rating = analysis.get('赚钱效应评级', {})
        result += f"【赚钱效应等级】\n"
        result += f"等级: {profit_rating.get('等级', '未知')}\n"
        result += f"描述: {profit_rating.get('描述', '无描述')}\n\n"

        # 基础统计
        basic_stats = analysis.get('基础统计', {})
        result += f"【基础统计】\n"
        result += f"平均涨幅: {basic_stats.get('平均涨幅', 0):.2f}%\n"
        result += f"最大涨幅: {basic_stats.get('最大涨幅', 0):.2f}%\n"
        result += f"最小涨幅: {basic_stats.get('最小涨幅', 0):.2f}%\n"
        result += f"上涨股票: {basic_stats.get('上涨股票数', 0)}只\n"
        result += f"下跌股票: {basic_stats.get('下跌股票数', 0)}只\n"
        result += f"涨停股票: {basic_stats.get('涨停股票数', 0)}只\n\n"

        # 成交额分析
        if '成交额分析' in analysis:
            amount_stats = analysis['成交额分析']
            result += f"【成交额分析】\n"
            result += f"总成交额: {amount_stats.get('总成交额(亿)', 0):.2f}亿\n"
            result += f"平均成交额: {amount_stats.get('平均成交额(亿)', 0):.2f}亿\n"
            result += f"成交额>10亿: {amount_stats.get('成交额>10亿的股票数', 0)}只\n"
            result += f"成交额>5亿: {amount_stats.get('成交额>5亿的股票数', 0)}只\n\n"

        # 换手率分析
        if '换手率分析' in analysis:
            turnover_stats = analysis['换手率分析']
            result += f"【换手率分析】\n"
            result += f"平均换手率: {turnover_stats.get('平均换手率', 0):.2f}%\n"
            result += f"换手率>10%: {turnover_stats.get('换手率>10%的股票数', 0)}只\n"
            result += f"换手率>20%: {turnover_stats.get('换手率>20%的股票数', 0)}只\n\n"

        # 连板分析
        if '连板分析' in analysis:
            board_stats = analysis['连板分析']
            result += f"【连板分析】\n"
            result += f"最高连板: {board_stats.get('最高连板', 0)}板\n"
            result += f"5板以上: {board_stats.get('5板以上', 0)}只\n"
            result += f"3-4板: {board_stats.get('3-4板', 0)}只\n"
            result += f"2板: {board_stats.get('2板', 0)}只\n"
            result += f"首板: {board_stats.get('首板', 0)}只\n\n"

        # 操作建议
        suggestions = analysis.get('操作建议', [])
        result += f"【操作建议】\n"
        for i, suggestion in enumerate(suggestions, 1):
            result += f"{i}. {suggestion}\n"

        return result

    except Exception as e:
        return f"赚钱效应分析失败: {str(e)}"


# -----------------------------
# 新增：指数数据和多日分析工具
# -----------------------------


def fetch_index_data(index_codes=['sh000300', 'sz399006', 'bj899050']):
    """获取主要指数数据（直接用新浪实时接口）

    参数：
    - index_codes: 指数代码列表
      - sh000300: 沪深300
      - sz399006: 创业板指
      - bj899050: 北证50
      - sh000001: 上证指数
      - sz399001: 深证成指

    返回：DataFrame 包含指数的名称、最新价、涨跌幅等
    """
    try:
        result = []

        # 定义指数信息映射
        index_info = {
            '000300': {'name': '沪深300', 'sina_id': 's_sh000300'},
            '000001': {'name': '上证指数', 'sina_id': 's_sh000001'},
            '399006': {'name': '创业板指', 'sina_id': 's_sz399006'},
            '399001': {'name': '深证成指', 'sina_id': 's_sz399001'},
            '899050': {'name': '北证50', 'sina_id': 's_bj899050'},
        }

        import time

        for code in index_codes:
            try:
                symbol = code[2:]  # 去掉前缀，只保留数字部分
                info = index_info.get(symbol)
                if not info:
                    continue

                sina_id = info['sina_id']
                name = info['name']

                # 使用新浪实时接口
                url = f'http://hq.sinajs.cn/list={sina_id}'
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://finance.sina.com.cn/',
                }

                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    # 解析响应：var hq_str_s_sh000001="上证指数,3891.8605,-31.4264,-0.80,6067049,..."
                    content = resp.text
                    start = content.find('"')
                    end = content.rfind('"')
                    if start > 0 and end > start:
                        data_str = content[start+1:end]
                        parts = data_str.split(',')

                        if len(parts) >= 4:
                            # 新浪指数数据格式：名称,当前值,涨跌额,涨跌幅,成交量...
                            current = float(parts[1]) if parts[1] else 0
                            change = float(parts[2]) if parts[2] else 0
                            pct_change = float(parts[3]) if parts[3] else 0

                            result.append({
                                '代码': code,
                                '名称': name,
                                '最新价': current,
                                '涨跌幅': pct_change,
                                '涨跌额': change,
                                '今开': 0,  # 新浪指数接口没有开盘价
                                '最高': 0,  # 新浪指数接口没有最高价
                                '最低': 0,  # 新浪指数接口没有最低价
                                '成交量': int(float(parts[4])) if len(parts) > 4 and parts[4] else 0,
                            })
                            continue

                # 如果新浪失败，尝试akshare（如果可用）
                if HAS_AKSHARE:
                    try:
                        import akshare as ak
                        end_date = pd.Timestamp.now().strftime('%Y%m%d')
                        start_date = (pd.Timestamp.now() - pd.Timedelta(days=3)).strftime('%Y%m%d')
                        df_idx = ak.index_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date)

                        if not df_idx.empty:
                            row = df_idx.iloc[-1]
                            if len(df_idx) >= 2:
                                prev_close = df_idx.iloc[-2]['收盘']
                                curr_close = row['收盘']
                                pct_chg = ((curr_close - prev_close) / prev_close) * 100
                            else:
                                pct_chg = 0

                            result.append({
                                '代码': code,
                                '名称': name,
                                '最新价': float(row.get('收盘', 0)),
                                '涨跌幅': pct_chg,
                                '涨跌额': 0,
                                '今开': float(row.get('开盘', 0)),
                                '最高': float(row.get('最高', 0)),
                                '最低': float(row.get('最低', 0)),
                                '成交量': int(row.get('成交量', 0)) if pd.notna(row.get('成交量')) else 0,
                            })
                    except:
                        pass

            except Exception as e:
                print(f"获取指数 {code} 失败: {e}")
                continue

        if result:
            return pd.DataFrame(result)
        else:
            print(f"警告: 所有指数数据获取失败")
            return pd.DataFrame()

    except Exception as e:
        print(f"获取指数数据失败: {e}")
        return pd.DataFrame()


def fetch_index_historical_data(index_code='000300', days=10):
    """获取指数历史K线数据（用于分析周期）

    参数：
    - index_code: 指数代码（如 '000300' 为沪深300）
    - days: 获取天数，默认10天

    返回：DataFrame，包含日期、收盘价、涨跌幅、成交量等
    """
    if not HAS_AKSHARE:
        return pd.DataFrame()

    try:
        import akshare as ak

        # 计算日期范围
        end_date = pd.Timestamp.now().strftime('%Y%m%d')
        start_date = (pd.Timestamp.now() - pd.Timedelta(days=days*2)).strftime('%Y%m%d')

        # 获取指数历史数据
        df = ak.index_zh_a_hist(
            symbol=index_code,
            period="daily",
            start_date=start_date,
            end_date=end_date
        )

        if df.empty:
            return pd.DataFrame()

        # 统一列名
        column_mapping = {
            '日期': '日期',
            '收盘': '收盘价',
            '开盘': '开盘价',
            '最高': '最高价',
            '最低': '最低价',
            '成交量': '成交量',
            '涨跌幅': '涨跌幅'
        }
        df = df.rename(columns=column_mapping)

        # 转换并排序
        df['日期'] = pd.to_datetime(df['日期'])
        df = df.sort_values('日期', ascending=False).head(days)

        return df

    except Exception as e:
        return pd.DataFrame()


def judge_index_cycle(days=10):
    """判断指数周期（A/B/C/D周期）

    判断规则：
    - B周期：指数缩量震荡
    - C周期：指数放量单边上涨（大牛市，普涨，赚钱效应爆炸）
    - D周期：指数单边下跌
    - A周期：
      * 共振A：指数共振上涨，接力空间高度打开，有主线
      * 背离A：指数下跌但情绪活跃，接力空间高度打开

    参数：
    - days: 分析天数，默认10天

    返回：dict，包含周期类型、涨跌幅情况、成交量情况
    """
    try:
        # 获取沪深300作为代表
        df = fetch_index_historical_data('000300', days)

        if df.empty or len(df) < 3:
            return {'cycle': '无法判断', 'reason': '数据不足'}

        df = df.sort_values('日期', ascending=True).reset_index(drop=True)

        # 1. 计算涨跌幅趋势
        overall_change = df['涨跌幅'].sum()
        last_5_change = df['涨跌幅'].tail(5).sum()

        # 2. 判断是否单边下跌（D周期）
        if overall_change < -5 and last_5_change < -3:
            return {
                'cycle': 'D周期',
                'sub_type': '单边下跌周期',
                'overall_change': overall_change,
                'last_5_change': last_5_change,
                'trend': '下跌',
                'reason': f'指数累计{overall_change:.2f}%，最近5日{last_5_change:.2f}%，单边下跌'
            }

        # 3. 判断是否放量单边上涨（C周期）
        # 最近3天均上涨
        last_3_positive = all(df['涨跌幅'].tail(3) > 0)
        # 整体涨幅大
        strong_rise = overall_change > 5 and last_5_change > 3

        if last_3_positive and strong_rise:
            return {
                'cycle': 'C周期',
                'sub_type': '放量上涨大牛市',
                'overall_change': overall_change,
                'last_5_change': last_5_change,
                'trend': '强势上涨',
                'reason': f'指数持续上涨，累计{overall_change:.2f}%，普涨特征明显'
            }

        # 4. 判断缩量震荡（B周期）
        # 涨跌幅都在小范围内
        max_range = df['收盘价'].max() - df['收盘价'].min()
        avg_price = df['收盘价'].mean()
        volatility = (max_range / avg_price) * 100

        if volatility < 5 and abs(overall_change) < 3:
            return {
                'cycle': 'B周期',
                'sub_type': '缩量震荡周期',
                'overall_change': overall_change,
                'last_5_change': last_5_change,
                'trend': '震荡',
                'volatility': volatility,
                'reason': f'波动率{volatility:.2f}%较低，指数缩量震荡'
            }

        # 5. A周期判断（需要配合情绪数据）
        # 默认根据指数情况判断共振A或背离A
        if overall_change > 0:
            return {
                'cycle': 'A周期（共振A）',
                'sub_type': '指数共振上涨周期',
                'overall_change': overall_change,
                'last_5_change': last_5_change,
                'trend': '震荡上涨',
                'reason': '指数震荡上涨，需关注是否打开接力空间和出现主线'
            }
        else:
            return {
                'cycle': 'A周期（背离A）',
                'sub_type': '指数背离活跃周期',
                'overall_change': overall_change,
                'last_5_change': last_5_change,
                'trend': '震荡偏弱',
                'reason': '指数偏弱但情绪活跃，可能形成背离A（需要配合情绪分析）'
            }

    except Exception as e:
        return {'cycle': '无法判断', 'reason': str(e)}


def analyze_multi_day_sentiment(days=5):
    """分析多日市场情绪趋势

    参数：
    - days: 分析天数，默认5天

    返回：包含多日情绪数据的列表
    """
    try:
        from datetime import datetime, timedelta
        import os

        results = []
        current_date = datetime.now()

        for i in range(days):
            check_date = current_date - timedelta(days=i)
            date_str = check_date.strftime('%Y%m%d')

            # 检查缓存文件
            cache_file = f'./data/limit_up_history/{date_str}_sentiment_cache.json'

            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    results.append({
                        'date': date_str,
                        'score': cache_data.get('score', 0),
                        'grade': cache_data.get('grade', '无'),
                        'zt_count': cache_data.get('zt_count', 0),
                        'max_board': cache_data.get('max_board', 0),
                        'avg_change_hot': cache_data.get('avg_change_hot', 0),
                    })
                except:
                    # 尝试从历史涨停数据计算
                    pass

        return results

    except Exception as e:
        print(f"多日情绪分析失败: {e}")
        return []


def classify_sector_by_name(stock_name):
    """根据股票名称简单分类板块

    参数：
    - stock_name: 股票名称

    返回：板块名称
    """
    # 扩展的关键词匹配（细分概念/题材）
    sector_keywords = {
        # 科技细分
        'AI/算力': ['人工智能', 'AI', '算力', '智能', '大模型', '算法', 'ChatGPT', 'GPT', 'AIGC', '曙光', '寒武纪', '海光'],
        '芯片/半导体': ['芯片', '半导体', 'IC', '集成电路', '芯原', '晶圆', '封测', 'EDA', '光刻', '北方华创', '中微', '兆易', '韦尔', '卓胜微'],
        'CPO/光模块': ['CPO', '光模块', '光通信', '光器件', '光芯片', '激光', '光电', '中际', '天孚', '新易盛', '光迅'],
        '云计算/数据中心': ['云计算', '数据中心', '服务器', 'IDC', '云服务', '浪潮', '宝信'],
        '存储': ['存储', '存储器', 'SSD', '闪存', 'DRAM', 'NAND', '兆易', '江波龙', '佰维'],
        '信创/自主可控': ['信创', '国产', '自主', '安全', '麒麟', '统信', '太极'],
        '通信/5G': ['通信', '5G', '6G', '基站', '天线', '射频', '通讯', '中兴', '烽火', '亨通'],
        '软件/互联网': ['软件', '互联网', '网络', '游戏', '传媒', '影视', '数据', '信息', '用友', '金蝶'],

        # 新能源细分
        '光伏': ['光伏', '太阳能', '逆变器', '硅片', '电池片', '隆基', '通威', '阳光电源', '晶澳', '天合'],
        '风电': ['风电', '风力', '风能', '海上风电', '明阳', '金风', '运达'],
        '储能': ['储能', '锂电池', '钠电池', '电化学', '宁德', '比亚迪电池'],
        '锂电/新能源电池': ['锂电', '锂矿', '锂', '钴', '镍', '正极', '负极', '隔膜', '电解液', '天齐', '赣锋', '恩捷', '璞泰来'],
        '充电桩': ['充电', '充电桩', '快充', '特锐德', '盛弘'],
        '氢能源': ['氢能', '氢燃料', '制氢', '氢气', '燃料电池'],

        # 汽车细分
        '新能源汽车': ['新能源车', '电动车', '比亚迪', '特斯拉', '理想', '蔚来', '小鹏'],
        '智能驾驶': ['自动驾驶', '智驾', '辅助驾驶', 'ADAS', '激光雷达', '毫米波'],
        '汽车零部件': ['汽配', '零部件', '轮胎', '轴承', '齿轮', '底盘'],
        '整车': ['汽车', '整车', '乘用车', '商用车'],

        # 医药细分
        '创新药/生物制药': ['医药', '药业', '制药', '生物制药', '生物药', '生物科技', '创新药', 'CXO', '研发外包', '临床',
                         '康德', '药明', '泰格', '恒瑞', '医学', '药物', '复星医药', '科伦', '华东医药', '丽珠',
                         '康龙', '君实', '信达', '百济', '贝达', '荣昌', '亚盛', '基石', '康宁杰瑞'],
        '医疗器械': ['医疗器械', '器械', '耗材', '影像', '体外诊断', 'IVD', '迈瑞', '诊断', '医疗设备', '骨科',
                   '乐普', '鱼跃', '威高', '微创', '安图', '万孚', '理邦'],
        '疫苗': ['疫苗', '免疫', '预防', '生物制品', '智飞', '沃森', '康泰', '康希诺', '万泰'],
        '中药': ['中药', '中医', '中成药', '片仔癀', '云南白药', '同仁堂', '东阿', '阿胶', '天士力'],
        '原料药/API': ['原料药', 'API', '中间体', '维生素', '特色原料药', '司太立', '普洛', '仙琚'],

        # 消费细分
        '白酒': ['白酒', '酒', '茅台', '五粮液'],
        '食品饮料': ['食品', '饮料', '乳业', '调味品', '零食'],
        '消费电子': ['消费电子', '手机', '耳机', '智能穿戴', '平板'],
        '家电': ['家电', '空调', '冰箱', '洗衣机', '电视'],
        '纺织服装': ['纺织', '服装', '服饰', '面料'],
        '美容护理': ['化妆品', '护肤', '美容', '个护'],

        # 金融
        '券商': ['证券', '券商', '投资'],
        '银行': ['银行', '商业银行', '农商行'],
        '保险': ['保险', '人寿', '财险'],

        # 周期/资源细分
        '贵金属': ['黄金', '白银', '贵金属'],
        '有色金属': ['铜', '铝', '锌', '铅', '锡', '有色'],
        '稀土/稀有金属': ['稀土', '钨', '钼', '锂', '镓', '锗'],
        '煤炭': ['煤炭', '焦煤', '焦炭', '动力煤'],
        '石油石化': ['石油', '石化', '炼化', '油服', '油气'],
        '化工': ['化工', '化学', '化纤', '农化', '橡胶'],

        # 基建/地产
        '房地产': ['地产', '房地产', '物业'],
        '建筑建材': ['建筑', '建材', '水泥', '玻璃', '钢铁', '装修'],
        '基建/工程机械': ['基建', '工程', '机械', '挖掘机', '混凝土'],

        # 公用事业
        '电力': ['电力', '电网', '发电', '供电', '水电', '火电', '核电', '清洁能源'],
        '环保': ['环保', '水处理', '固废', '垃圾', '污水'],

        # 国防军工
        '军工/国防': ['军工', '国防', '航空', '航天', '导弹', '雷达', '卫星'],

        # 新兴产业
        '量子科技': ['量子', '量子计算', '量子通信'],
        '元宇宙/VR/AR': ['元宇宙', 'VR', 'AR', 'XR', '虚拟现实', '增强现实'],
        '区块链': ['区块链', '数字货币', '加密'],
        '卫星互联网': ['卫星', '低轨', '星链', '通信卫星'],
        '机器人': ['机器人', '工业机器人', '人形机器人', '协作机器人'],

        # 其他传统行业
        '农林牧渔': ['农业', '种植', '养殖', '饲料', '渔业', '林业', '农产品'],
        '交运物流': ['交运', '物流', '快递', '航运', '港口', '铁路', '航空'],
        '旅游酒店': ['旅游', '酒店', '景区', '餐饮'],
        '商贸零售': ['零售', '商贸', '百货', '超市', '电商'],
    }

    stock_name_upper = stock_name.upper()

    for sector, keywords in sector_keywords.items():
        for keyword in keywords:
            if keyword in stock_name or keyword.upper() in stock_name_upper:
                return sector

    return '其他'


def analyze_sector_performance(df_zt=None):
    """分析板块表现

    参数：
    - df_zt: 涨停股DataFrame，如果为None则自动获取

    返回：板块分析结果
    """
    try:
        if df_zt is None:
            df_zt = fetch_limit_up_stocks()

        if df_zt.empty:
            return {}

        # 统计各板块涨停数量
        sector_stats = {}
        for _, row in df_zt.iterrows():
            stock_name = row.get('名称', '')
            sector = classify_sector_by_name(stock_name)

            if sector not in sector_stats:
                sector_stats[sector] = {
                    'count': 0,
                    'avg_amount': 0,
                    'stocks': [],
                }

            sector_stats[sector]['count'] += 1
            sector_stats[sector]['avg_amount'] += row.get('成交额(亿)', 0)
            sector_stats[sector]['stocks'].append({
                'name': stock_name,
                'code': row.get('代码', ''),
                'pct': row.get('涨跌幅', 0),
                'amount': row.get('成交额(亿)', 0),
            })

        # 计算平均成交额
        for sector in sector_stats:
            if sector_stats[sector]['count'] > 0:
                sector_stats[sector]['avg_amount'] /= sector_stats[sector]['count']

        # 按涨停数量排序
        sorted_sectors = sorted(
            sector_stats.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )

        return dict(sorted_sectors)

    except Exception as e:
        print(f"板块分析失败: {e}")
        return {}


@tool
def get_market_big_picture(days: int = 5) -> str:
    """获取市场大局观分析（多维度综合分析，使用并行策略加速）

    从以下4个维度分析市场：
    1. 指数表现 - 主要指数（沪深300、创业板指、北证50等）涨跌情况
    2. 中级周期 - 过去N天情绪趋势，判断当前所处周期位置
    3. 市场情绪 - 涨停股数量、梯队完整性、赚钱效应等
    4. 题材板块 - 热门板块分布、领涨股情况

    参数：
    - days: 分析天数，默认5天

    返回：综合市场大局观分析报告
    """
    try:
        from datetime import datetime, timedelta
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import os

        result = f"{'='*70}\n"
        result += f"📊 市场大局观分析（{days}日线）\n"
        result += f"{'='*70}\n\n"

        # ========== 并行获取所有数据 ==========
        # 定义所有数据获取任务
        def fetch_index():
            """获取指数数据"""
            try:
                return fetch_index_data(['sh000300', 'sz399006', 'sh000001', 'sz399001'])
            except Exception as e:
                print(f"指数数据获取异常: {e}")
                return None

        def fetch_cycle():
            """判断指数周期"""
            try:
                return judge_index_cycle(days=10)
            except Exception as e:
                print(f"周期判断异常: {e}")
                return None

        def fetch_multi_sentiment():
            """获取多日情绪"""
            try:
                return analyze_multi_day_sentiment(days)
            except Exception as e:
                print(f"多日情绪分析异常: {e}")
                return None

        def fetch_today_sentiment():
            """获取今日情绪"""
            try:
                return _analyze_market_sentiment_impl()
            except Exception as e:
                print(f"今日情绪分析异常: {e}")
                return None

        def fetch_sectors():
            """获取板块数据"""
            try:
                return analyze_sector_performance()
            except Exception as e:
                print(f"板块分析异常: {e}")
                return None

        # 并行执行所有任务
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_index = executor.submit(fetch_index)
            future_cycle = executor.submit(fetch_cycle)
            future_multi_sentiment = executor.submit(fetch_multi_sentiment)
            future_today_sentiment = executor.submit(fetch_today_sentiment)
            future_sectors = executor.submit(fetch_sectors)

            # 等待所有任务完成
            df_index = future_index.result()
            cycle_info = future_cycle.result()
            sentiment_data = future_multi_sentiment.result()
            today_sentiment = future_today_sentiment.result()
            sector_data = future_sectors.result()

        # ========== 1. 指数分析 + 周期判断 ==========
        result += f"【一、指数表现】\n"
        try:
            if df_index is not None and not df_index.empty:
                for _, row in df_index.iterrows():
                    name = row.get('名称', '')
                    pct = row.get('涨跌幅', 0)
                    change_sign = '+' if pct > 0 else ''
                    result += f"  {name:<8} {change_sign}{pct:.2f}%\n"

                # 判断整体指数环境
                avg_index_change = df_index['涨跌幅'].mean()
                if avg_index_change > 1:
                    result += f"\n  💡 指数环境: 强势上涨\n"
                elif avg_index_change > 0:
                    result += f"\n  💡 指数环境: 稳健偏强\n"
                elif avg_index_change > -1:
                    result += f"\n  ➡️  指数环境: 震荡整理\n"
                else:
                    result += f"\n  ⚠️  指数环境: 弱势调整\n"

            else:
                result += f"  暂无指数数据\n"
        except Exception as e:
            result += f"  指数数据获取失败: {str(e)}\n"
        result += "\n"

        # ========== 周期判断（A/B/C/D周期）==========
        result += f"【指数周期判断（A/B/C/D周期）】\n"
        try:
            if cycle_info:
                result += f"  当前周期: {cycle_info.get('cycle', '未知')}\n"
                result += f"  周期类型: {cycle_info.get('sub_type', '未知')}\n"
                result += f"  判断依据: {cycle_info.get('reason', '未知')}\n"

                # 根据周期给出简要说明
                cycle = cycle_info.get('cycle', '')
                if 'C周期' in cycle:
                    result += f"\n  💰 C周期特点: 普涨，大牛市，赚钱效应爆炸\n"
                elif 'A周期' in cycle and '共振' in cycle:
                    result += f"\n  🚀 共振A特点: 接力空间高度打开，有主线\n"
                elif 'A周期' in cycle and '背离' in cycle:
                    result += f"\n  🔄 背离A特点: 指数下跌但情绪活跃，接力空间高度打开\n"
                elif 'B周期' in cycle:
                    result += f"\n  📊 B周期特点: 缩量震荡\n"
                elif 'D周期' in cycle:
                    result += f"\n  📉 D周期特点: 单边下跌\n"
            else:
                result += f"  周期判断数据不可用\n"

        except Exception as e:
            result += f"  周期判断失败: {str(e)}\n"
        result += "\n"

        # ========== 2. 中级周期分析 ==========
        result += f"【二、中级周期（{days}天情绪趋势）】\n"

        if sentiment_data and len(sentiment_data) >= 2:
            # 按日期正序排列
            sentiment_data_sorted = sorted(sentiment_data, key=lambda x: x['date'])

            result += f"  日期        得分    评级    涨停数   最高板\n"
            for day_data in sentiment_data_sorted:
                score = day_data['score']
                grade = day_data['grade']
                zt = day_data['zt_count']
                board = day_data['max_board']
                result += f"  {day_data['date']}  {score:6.1f}  {grade:<6}  {zt}只    {board}板\n"

            # 判断周期位置
            if len(sentiment_data_sorted) >= 3:
                recent_trend = [d['score'] for d in sentiment_data_sorted[-3:]]
                if all(recent_trend[i] < recent_trend[i+1] for i in range(len(recent_trend)-1)):
                    cycle_phase = "📈 上升周期"
                    trend_desc = "情绪持续升温，赚钱效应增强"
                elif all(recent_trend[i] > recent_trend[i+1] for i in range(len(recent_trend)-1)):
                    cycle_phase = "📉 下降周期"
                    trend_desc = "情绪持续降温，风险上升"
                else:
                    cycle_phase = "↔️ 震荡周期"
                    trend_desc = "情绪摇摆，方向不明"

                result += f"\n  周期位置: {cycle_phase}\n"
                result += f"  趋势判断: {trend_desc}\n"
        else:
            result += f"  数据不足，需要至少{days}天的历史数据\n"
        result += "\n"

        # ========== 3. 市场情绪 ==========
        result += f"【三、市场情绪（今日）】\n"
        try:
            if today_sentiment:
                # 提取关键信息
                import re
                zt_match = re.search(r'涨停股:\s*(\d+)只', today_sentiment)
                dt_match = re.search(r'跌停股:\s*(\d+)只', today_sentiment)
                max_board_match = re.search(r'最高(\d+)板', today_sentiment)
                grade_match = re.search(r'综合评级[】\s]*(\S+)', today_sentiment)
                score_match = re.search(r'得分:\s*([\d.]+)', today_sentiment)

                if zt_match:
                    result += f"  涨停/跌停: {zt_match.group(1)}只 / "
                    if dt_match:
                        result += f"{dt_match.group(1)}只\n"
                    else:
                        result += "未知\n"

                if grade_match and score_match:
                    result += f"  综合评级: {grade_match.group(1)} ({score_match.group(1)}/100)\n"

                if max_board_match:
                    result += f"  最高连板: {max_board_match.group(1)}板\n"

                # 昨日对比
                yest_match = re.search(r'得分: ([\d.]+) → ([\d.]+)', today_sentiment)
                if yest_match and len(yest_match.groups()) == 2:
                    yest_score = float(yest_match.group(1))
                    today_score = float(yest_match.group(2))
                    diff = today_score - yest_score
                    if diff > 10:
                        result += f"  对比昨日: 明显转强 (+{diff:.1f})\n"
                    elif diff > 0:
                        result += f"  对比昨日: 小幅走强 (+{diff:.1f})\n"
                    elif diff < -10:
                        result += f"  对比昨日: 明显转弱 ({diff:.1f})\n"
                    elif diff < 0:
                        result += f"  对比昨日: 小幅走弱 ({diff:.1f})\n"
                    else:
                        result += f"  对比昨日: 持平\n"
            else:
                result += f"  情绪数据不可用\n"

        except Exception as e:
            result += f"  情绪分析失败: {str(e)}\n"
        result += "\n"

        # ========== 4. 题材板块 ==========
        result += f"【四、热门题材板块】\n"
        try:
            if sector_data:
                # 过滤掉"其他"，取前8个有效板块
                filtered_sectors = [s for s in sector_data.keys() if s != '其他']
                top_sectors = filtered_sectors[:8]

                for sector in top_sectors:
                    count = sector_data[sector]['count']
                    avg_amount = sector_data[sector]['avg_amount']
                    result += f"  {sector:<8}: {count}只涨停  平均{avg_amount:.2f}亿\n"

                    # 领涨股展示
                    stocks_sorted = sorted(
                        sector_data[sector]['stocks'],
                        key=lambda x: x['amount'],
                        reverse=True
                    )[:3]
                    if stocks_sorted:
                        result += f"    领涨: {', '.join([s['name'] for s in stocks_sorted])}\n"
            else:
                result += f"  暂无涨停股数据\n"
        except Exception as e:
            result += f"  板块分析失败: {str(e)}\n"
        result += "\n"

        # ========== 5. 综合判断 ==========
        result += f"【五、综合判断与建议】\n"

        # 根据各维度打分
        score_factors = []

        # 指数分
        try:
            if df_index is not None and not df_index.empty:
                avg_index = df_index['涨跌幅'].mean()
                if avg_index > 1:
                    score_factors.append(('指数环境', '强'))
                elif avg_index > 0:
                    score_factors.append(('指数环境', '偏强'))
                elif avg_index > -1:
                    score_factors.append(('指数环境', '中性'))
                else:
                    score_factors.append(('指数环境', '弱'))
        except:
            pass

        # 周期分
        if sentiment_data and len(sentiment_data) >= 2:
            today_score = sentiment_data[-1]['score']
            if today_score >= 75:
                score_factors.append(('情绪周期', '强势'))
            elif today_score >= 60:
                score_factors.append(('情绪周期', '偏强'))
            elif today_score >= 40:
                score_factors.append(('情绪周期', '中性'))
            else:
                score_factors.append(('情绪周期', '弱'))

        # 板块集中度
        try:
            if sector_data:
                top_3_count = sum([sector_data.get(s, {}).get('count', 0) for s in list(sector_data.keys())[:3]])
                total_zt = sum([v['count'] for v in sector_data.values()])
                if total_zt > 0 and top_3_count / total_zt > 0.5:
                    score_factors.append(('板块集中度', '主线清晰'))
                elif total_zt > 0 and top_3_count / total_zt > 0.3:
                    score_factors.append(('板块集中度', '有主线'))
                else:
                    score_factors.append(('板块集中度', '分散'))
        except:
            pass

        if score_factors:
            result += f"  维度评估:\n"
            for factor, level in score_factors:
                result += f"    - {factor}: {level}\n"

            # 综合评级
            strong_count = sum(1 for _, level in score_factors if '强' in level)
            if strong_count >= 2:
                result += f"\n  ✅ 市场整体评级: 强\n"
                result += f"  建议: 积极参与，聚焦主线题材\n"
            elif strong_count >= 1:
                result += f"\n  ➡️  市场整体评级: 中性偏强\n"
                result += f"  建议: 适度参与，控制仓位\n"
            else:
                result += f"\n  ⚠️  市场整体评级: 偏弱\n"
                result += f"  建议: 谨慎观望，等待信号\n"

        result += f"\n{'='*70}\n"

        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"大局观分析失败: {str(e)}"


# -----------------------------
# 构建Agent
# -----------------------------
def build_chat_agent() -> AgentExecutor:
    """构建对话式股票分析Agent - 带知识库和短期记忆"""

    # 使用qwen-plus模型（更强的指令遵循能力）
    llm = ChatTongyi(
        model_name="qwen-plus",
        temperature=0.1,
        dashscope_api_key=os.environ.get("DASHSCOPE_API_KEY"),
        streaming=False,
        incremental_output=False,
        result_format="message",
        max_retries=2
    )

    tools = [
        search_knowledge,  # 知识库搜索
        get_market_overview,  # 市场概览
        get_top_stocks_by_turnover,  # 成交额排名
        get_top_stocks_by_pct_change,  # 涨跌幅排名
        get_stock_quote,  # 个股行情
        search_stock_by_name,  # 股票搜索
        get_limit_up_stocks,  # 涨停股列表
        get_board_ranking,  # 板块涨幅排名
        analyze_market_sentiment,  # 市场情绪分析
        get_continuous_limit_up_leaders,  # 连板梯队（准确连板数据）
        get_stock_history,  # 个股历史K线（使用AKShare）
        get_hot_stocks_ranking,  # 热股榜排行
        analyze_profit_effect,  # 赚钱效应分析
        get_market_big_picture,  # 大局观分析（综合多维度）
    ]

    # 创建短期记忆（保留最近5轮对话）
    memory = ConversationBufferWindowMemory(
        k=5,  # 保留最近5轮对话
        memory_key="chat_history",
        return_messages=True,
        output_key="output"
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "你是A股交易助手。\n\n"
         "【核心原则 - 必须遵守】\n"
         "当调用search_knowledge后：\n"
         "1. 工具返回的内容就是完整的CSV数据，格式如：[2026-04-02] 节点=混沌 | 高位=超预期 | ...\n"
         "2. 直接引用这些数据，不要质疑或说'未提供数据'\n"
         "3. 可以添加简短分析，但不能修改或省略任何日期和字段值\n\n"
         "【示例 - 正确做法】\n"
         "工具返回：[2026-04-02] 节点=混沌 | 高位=超预期 | 是否开仓=买入试错\n"
         "你的回答：根据竞价表数据：\n"
         "[2026-04-02] 节点=混沌 | 高位=超预期 | 是否开仓=买入试错\n"
         "分析：高位超预期表现较强...\n\n"
         "【示例 - 错误做法】\n"
         "❌ 说'工具未返回具体数据'\n"
         "❌ 说'数据为空'或'无法提供'\n"
         "❌ 编造不同的数据\n"
         "❌ 省略工具返回的日期或字段\n\n"
         "【知识库优先原则 - 必须遵守！】\n"
         "⚠️ **最高优先级**：当用户提到以下CSV文件名时，无论问什么，第一步必须调用search_knowledge：\n"
         "- \"竞价表\"、\"复盘表\"、\"短线模式\"、\"题材周期\"、\"屠龙表\"、\"周期系统\"\n"
         "- 即使问题看起来像市场分析（如\"反映了什么\"、\"说明什么\"），也必须先获取CSV内容\n\n"
         "当用户问题包含以下任一关键词时，第一步操作必须是调用 search_knowledge 工具：\n\n"
         "**介绍/说明类**（必须调用！）：\n"
         "- \"介绍\"、\"是什么\"、\"什么是\"、\"有哪些\"\n"
         "- 看到这些词，无论后面跟什么（短线、题材、竞价等），都必须调用search_knowledge\n\n"
         "**模式相关**（必须调用！）：\n"
         "- \"短线模式\"、\"短线\"、\"模式\"、\"屠龙表\"\n"
         "- \"一波流\"、\"趋势接力\"、\"龙头接力\"、\"纯趋势\"\n"
         "- \"新题材同身位\"、\"接力唯一性\"、\"接力打破空间\"\n"
         "- \"龙头低吸\"、\"低位反推身位\"、\"龙头补涨\"\n"
         "- \"主线核心\"、\"情绪先锋\"、\"辨识度反包\"\n"
         "- \"断板趋势龙\"、\"逻辑趋势龙\"\n\n"
         "**交易手法**（必须调用！）：\n"
         "- \"超短\"、\"打板\"、\"低吸\"、\"半路\"、\"接力\"\n"
         "- \"龙头\"、\"龙头股\"、\"空间龙\"、\"补涨龙\"\n\n"
         "**情绪周期**（必须调用！）：\n"
         "- \"情绪周期\"、\"情绪流\"、\"市场情绪\"\n"
         "- \"竞价\"、\"选时\"、\"预期差\"\n\n"
         "**风控纪律**（必须调用！）：\n"
         "- \"交易战法\"、\"手法\"、\"策略\"\n"
         "- \"错题集\"、\"风控\"、\"卖点\"、\"买点\"\n"
         "- \"仓位\"、\"止损\"、\"纪律\"、\"惩罚\"\n\n"
         "**题材周期**（必须调用！）：\n"
         "- \"题材周期\"、\"周期系统\"、\"可做周期\"\n"
         "- \"混沌\"、\"主升\"、\"强修复\"、\"弱修复\"\n\n"
         "【强制执行规则 - 市场分析必须调用工具】\n"
         "当用户问题涉及以下内容时，必须先调用 get_market_big_picture 工具：\n"
         "- 市场分析、市场情绪、市场状况、今日行情\n"
         "- 大盘走势、涨停情况、连板情况\n"
         "- 题材板块、热点方向、操作建议、买卖方向\n\n"
         "【数据展示规则 - 必须遵守】\n"
         "调用工具后，必须：\n"
         "1. 直接引用工具返回的具体数据（指数涨幅、涨停数量、得分等）\n"
         "2. 基于真实数据给出分析和建议\n"
         "3. 用具体数字支撑你的观点\n"
         "【禁止行为】\n"
         "- 不要说\"未提供数据\"、\"数据缺失\"\n"
         "- 不要说\"涨停股数量较多\"而不说具体数字\n"
         "- 不要跳过工具调用直接根据常识回答\n"
         "- 不要说\"未提供指数数据\"\n\n"
         "【回答原则：多日对比+大局观分析】\n"
         "每次回答市场相关问题时，必须从以下4个维度提供分析：\n"
         "1. 指数 - 沪深300/创业板指/上证指数等表现（必须用具体数字）\n"
         "2. 中级周期 - 过去3-5天情绪趋势，判断当前周期位置（必须对比具体得分）\n"
         "3. 情绪 - 涨停股数量、梯队完整性、赚钱效应（必须引用具体数量）\n"
         "4. 题材 - 热门板块分布、领涨股情况（必须列出具体板块和数量）\n\n"
         "【知识库回答要求 - 必须100%基于工具返回内容】\n"
         "当回答来自知识库（CSV/文档）时：\n"
         "1. ⚠️ **严禁自己编造表格或字段** - 必须完全按照search_knowledge返回的内容回答\n"
         "2. 必须逐字引用search_knowledge返回的原文，不要改写、总结或重新组织\n"
         "3. 保持search_knowledge返回内容的原有格式和结构\n"
         "4. 如果返回内容有表格，就用表格；如果是列表，就用列表；如果是日期记录，就用日期记录\n"
         "5. 严禁添加任何工具返回内容中不存在的字段、数据或说明\n"
         "6. 不要根据自己的理解重新格式化或转换数据\n\n"
         "【竞价表/复盘表等时间序列表格】\n"
         "当用户问竞价表、复盘表等时间序列数据时：\n"
         "- 必须按照search_knowledge返回的格式展示（通常是按日期排列）\n"
         "- 不要转换成其他格式的表格\n"
         "- 保留所有日期和对应的字段（如：节点、高位、中位、是否开仓等）\n\n"
         "【工具】\n"
         "1. get_market_big_picture - 大局观分析（指数+周期+情绪+题材，多日对比）【市场分析必须调用】\n"
         "2. search_knowledge - 知识库搜索（策略、理论、战法）【交易策略问题必须调用】\n"
         "3. get_limit_up_stocks - 今日涨停\n"
         "4. get_continuous_limit_up_leaders - 连板梯队\n"
         "5. analyze_market_sentiment - 市场情绪\n"
         "6. get_hot_stocks_ranking - 热股榜排行（判断市场热度）\n"
         "7. analyze_profit_effect - 赚钱效应分析（评估市场机会）\n"
         "8. get_stock_quote - 个股行情查询\n"
         "9. get_stock_history - 个股历史K线\n\n"
         "【回答格式】\n"
         "结构化输出：\n"
         "1. 一句话总结（基于大局观数据）\n"
         "2. 多维度分析（用工具返回的具体数据：指数+周期+情绪+题材）\n"
         "3. 对比昨日/前几天的变化（用具体数字对比）\n"
         "4. 具体建议（操作方向、仓位控制、风险提示）"),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad")
    ])

    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        memory=memory,
        verbose=False,
        max_iterations=30,
        handle_parsing_errors=True,
        return_intermediate_steps=False
    )


# -----------------------------
# 交互式测试
# -----------------------------
def interactive_test():
    """交互式测试模式"""
    print("=" * 70)
    print("股票实时分析Agent - 智能知识库版")
    print("=" * 70)

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("\n⚠️  警告：未检测到 DASHSCOPE_API_KEY 环境变量")
        return

    # 构建知识库
    build_knowledge_base(api_key, folder_path="./ku")

    try:
        agent = build_chat_agent()
        print("\n✓ 初始化完成！")
    except Exception as e:
        print(f"\n❌ 初始化失败: {str(e)}")
        return

    print("\n💡 你可以问我：")
    print("  • 交易策略问题（如：如何判断情绪周期？）")
    print("  • 实时行情查询（如：今天成交额最大的股票？）")
    print("  • 综合分析（如：这只股票适合打板吗？）")
    print("\n输入 'exit' 或 'quit' 退出")
    print("=" * 70)

    while True:
        try:
            user_input = input("\n💬 你的问题: ").strip()

            if user_input.lower() in ['exit', 'quit', '退出']:
                print("\n👋 再见！")
                break

            if not user_input:
                continue

            print("\n⏳ 正在分析...\n")
            # 获取完整结果后再显示，避免流式输出
            result = agent.invoke({"input": user_input})
            output = result.get("output", "")
            # 确保只显示最终结果，不显示中间过程
            print("─" * 70)
            print(output)
            print("─" * 70)

        except KeyboardInterrupt:
            print("\n\n👋 再见！")
            break
        except Exception as e:
            import traceback
            print(f"\n❌ 错误: {str(e)}")
            print("\n详细错误信息:")
            traceback.print_exc()


def quick_test():
    """快速测试"""
    print("=" * 70)
    print("股票实时分析Agent - 快速测试")
    print("=" * 70)

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("\n⚠️  警告：未检测到 DASHSCOPE_API_KEY 环境变量")
        return

    # 构建知识库
    build_knowledge_base(api_key, folder_path="./ku")

    try:
        agent = build_chat_agent()
        print("✓ 初始化完成\n")
    except Exception as e:
        print(f"\n❌ 初始化失败: {str(e)}")
        return

    test_questions = [
        "今天成交额最大的股票是谁？",
        "如何判断市场情绪周期？",
        "打板战法的核心要点是什么？",
        "胜宏科技适合打板吗？",
    ]

    for i, question in enumerate(test_questions, 1):
        print(f"{'─' * 70}")
        print(f"📝 测试 {i}/{len(test_questions)}: {question}")
        print(f"{'─' * 70}\n")

        try:
            result = agent.invoke({"input": question})
            print(result["output"])
            print()
        except Exception as e:
            print(f"❌ 错误: {str(e)}\n")

        if i < len(test_questions):
            time.sleep(2)

    print(f"{'=' * 70}")
    print("✓ 测试完成")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "quick":
        quick_test()
    else:
        interactive_test()
