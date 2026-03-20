"""
股票实时分析Agent - 带知识库版本
支持从ku文件夹学习交易知识，结合实时数据提供更智能的分析
"""
import os
import time
import requests
import json
from typing import Dict, Any, List
import pandas as pd
from io import StringIO
from pathlib import Path

from langchain_community.chat_models.tongyi import ChatTongyi
from langchain.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.document_loaders import TextLoader, Docx2txtLoader
from langchain.memory import ConversationBufferWindowMemory
import docx
import openpyxl

# 修补 ChatTongyi 的 subtract_client_response 方法以修复索引错误
def patched_subtract_client_response(self, resp, prev_resp):
    """修补后的响应差分方法，添加索引边界检查"""
    import copy

    if prev_resp is None:
        return resp

    # 处理dict类型的响应
    if isinstance(resp, dict):
        result = copy.deepcopy(resp)
    else:
        result = resp.model_copy(deep=True)

    try:
        # 安全地处理 tool_calls
        if isinstance(result, dict):
            # 处理dict格式的响应
            if 'output' in result and 'choices' in result['output']:
                for choice_idx, choice in enumerate(result['output']['choices']):
                    if 'message' in choice and 'tool_calls' in choice['message'] and choice['message']['tool_calls']:
                        prev_choice = None
                        if isinstance(prev_resp, dict) and 'output' in prev_resp and 'choices' in prev_resp['output']:
                            if choice_idx < len(prev_resp['output']['choices']):
                                prev_choice = prev_resp['output']['choices'][choice_idx]

                        if prev_choice and 'message' in prev_choice and 'tool_calls' in prev_choice['message']:
                            prev_tool_calls = prev_choice['message']['tool_calls']
                            for index, tool_call in enumerate(choice['message']['tool_calls']):
                                # 添加索引边界检查
                                if index < len(prev_tool_calls):
                                    prev_tool_call = prev_tool_calls[index]
                                    if 'function' in tool_call and 'function' in prev_tool_call:
                                        if 'arguments' in tool_call['function'] and tool_call['function']['arguments']:
                                            prev_args = prev_tool_call['function'].get('arguments', '')
                                            if prev_args:
                                                tool_call['function']['arguments'] = tool_call['function']['arguments'].replace(prev_args, "", 1)
        else:
            # 处理Pydantic模型格式的响应
            if hasattr(result, 'output') and hasattr(result.output, 'choices'):
                for choice_idx, choice in enumerate(result.output.choices):
                    if hasattr(choice.message, 'tool_calls') and choice.message.tool_calls:
                        prev_choice = None
                        if hasattr(prev_resp, 'output') and hasattr(prev_resp.output, 'choices'):
                            if choice_idx < len(prev_resp.output.choices):
                                prev_choice = prev_resp.output.choices[choice_idx]

                        if prev_choice and hasattr(prev_choice.message, 'tool_calls') and prev_choice.message.tool_calls:
                            for index, tool_call in enumerate(choice.message.tool_calls):
                                # 添加索引边界检查
                                if index < len(prev_choice.message.tool_calls):
                                    prev_tool_call = prev_choice.message.tool_calls[index]
                                    if hasattr(tool_call, 'function') and hasattr(prev_tool_call, 'function'):
                                        if hasattr(tool_call.function, 'arguments') and tool_call.function.arguments:
                                            prev_args = prev_tool_call.function.arguments if hasattr(prev_tool_call.function, 'arguments') else ''
                                            if prev_args:
                                                tool_call.function.arguments = tool_call.function.arguments.replace(prev_args, "", 1)
    except Exception as e:
        # 如果补丁失败，至少返回原始响应
        pass

    return result

# 应用补丁 - 注释掉因为导致输出重复
# ChatTongyi.subtract_client_response = patched_subtract_client_response

try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    print("⚠️  警告：akshare未安装，历史数据功能将不可用")


# 全局知识库
KNOWLEDGE_BASE = None


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
    """构建向量知识库（支持缓存）"""
    global KNOWLEDGE_BASE

    cache_dir = os.path.join(folder_path, ".faiss_cache")

    # 创建embeddings对象（加载缓存也需要）
    embeddings = DashScopeEmbeddings(
        model="text-embedding-v1",
        dashscope_api_key=api_key
    )

    # 尝试加载缓存
    if os.path.exists(cache_dir):
        try:
            print("正在加载知识库缓存...", end='', flush=True)
            KNOWLEDGE_BASE = FAISS.load_local(
                cache_dir,
                embeddings,
                allow_dangerous_deserialization=True
            )
            # 读取块数量信息
            info_file = os.path.join(cache_dir, "info.txt")
            chunk_count = "未知"
            if os.path.exists(info_file):
                with open(info_file, 'r') as f:
                    chunk_count = f.read().strip()
            print(f" ✓ ({chunk_count}个文本块)")
            return KNOWLEDGE_BASE
        except Exception as e:
            # 缓存损坏，删除重建
            import shutil
            shutil.rmtree(cache_dir, ignore_errors=True)

    # 加载文档
    docs = load_knowledge_from_folder(folder_path)
    if not docs:
        print("⚠️  没有加载到知识文件，知识库功能将不可用")
        return None

    # 切分文档（优化参数以减少文本块数量）
    print("正在切分文档...", end='', flush=True)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,  # 增加块大小，减少总块数
        chunk_overlap=100,
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]
    )

    all_texts = []
    all_metadatas = []

    for doc in docs:
        chunks = text_splitter.split_text(doc["content"])
        all_texts.extend(chunks)
        all_metadatas.extend([{"source": doc["source"]} for _ in chunks])

    print(f" ✓ ({len(all_texts)}个文本块)")

    # 创建向量数据库（这一步最慢，因为要调用API生成embeddings）
    print(f"正在生成向量索引（{len(all_texts)}个文本块）...", flush=True)
    try:
        # 分批处理，显示进度
        batch_size = 100
        if len(all_texts) > 500:
            print(f"提示：文本块较多，预计需要60-120秒，请耐心等待...", flush=True)
            KNOWLEDGE_BASE = None
            total_batches = (len(all_texts) + batch_size - 1) // batch_size
            for i in range(0, len(all_texts), batch_size):
                batch_num = i // batch_size + 1
                print(f"  进度: {batch_num}/{total_batches} 批次...", end='\r', flush=True)
                batch_texts = all_texts[i:i+batch_size]
                batch_metas = all_metadatas[i:i+batch_size]
                if KNOWLEDGE_BASE is None:
                    KNOWLEDGE_BASE = FAISS.from_texts(batch_texts, embeddings, batch_metas)
                else:
                    temp_db = FAISS.from_texts(batch_texts, embeddings, batch_metas)
                    KNOWLEDGE_BASE.merge_from(temp_db)
            print(f"  进度: {total_batches}/{total_batches} 批次 ✓ 完成          ")
        else:
            # 文本块少，直接一次性生成
            KNOWLEDGE_BASE = FAISS.from_texts(
                texts=all_texts,
                embedding=embeddings,
                metadatas=all_metadatas
            )
            print(" ✓")
    except Exception as e:
        print(f"\n❌ 向量索引生成失败: {str(e)}")
        print("建议检查网络连接或API密钥是否正确")
        return None

    # 保存缓存
    try:
        KNOWLEDGE_BASE.save_local(cache_dir)
        # 保存块数量信息
        info_file = os.path.join(cache_dir, "info.txt")
        with open(info_file, 'w') as f:
            f.write(str(len(all_texts)))
    except Exception:
        pass  # 缓存保存失败不影响使用

    return KNOWLEDGE_BASE


# -----------------------------
# 数据获取函数（使用新浪财经API + 东方财富）
# -----------------------------
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

        # 统一列名
        df = df.rename(columns={
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
        })

        # 转换日期格式
        df['日期'] = pd.to_datetime(df['日期'])

        # 按日期降序排列，取最近N天
        df = df.sort_values('日期', ascending=False).head(days)

        return df

    except Exception as e:
        # 静默处理错误，避免大量错误信息干扰用户
        # 如果需要调试，可以取消下面的注释
        # print(f"获取历史数据失败({symbol}): {e}")
        return pd.DataFrame()


def calculate_continuous_limit_up_days(symbol: str) -> int:
    """计算股票连续涨停天数（使用AKShare历史数据）

    参数：
    - symbol: 股票代码（如 '000001'）

    返回：连续涨停天数（0表示今天未涨停或不连板）
    """
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

        return continuous_days

    except Exception as e:
        print(f"计算连板失败({symbol}): {e}")
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


def fetch_sina_stock_data(sort_field='amount', page=1, num=100, asc=0):
    """从新浪财经获取A股数据（带重试机制）

    参数：
    - sort_field: 排序字段（'amount'=成交额, 'changepercent'=涨跌幅）
    - page: 页码
    - num: 获取数量
    - asc: 排序方式（0=降序，1=升序）

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
            'node': 'hs_a'
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
    """分析连板股梯队（查询所有非ST涨停股）- 简化快速版"""
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        from datetime import datetime
        import os

        # 检查今日缓存
        today = datetime.now().strftime('%Y%m%d')
        cache_file = f'./data/limit_up_history/{today}_board_cache.json'

        # 如果缓存存在且不超过1小时，直接使用缓存
        if os.path.exists(cache_file):
            try:
                cache_age = time.time() - os.path.getmtime(cache_file)
                if cache_age < 3600:
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

        # 只分析前50只（加快速度）
        results = []
        board_stats = {}
        max_board = 1
        max_board_stocks = []
        failed_count = 0

        # 准备前50只股票数据
        stock_data = []
        for idx, (_, row) in enumerate(df_zt_sorted.head(50).iterrows(), 1):
            name = row['名称']
            code = row.get('代码', '').replace('sh', '').replace('sz', '').replace('bj', '')
            pct = row['涨跌幅']
            amount = row.get('成交额(亿)', 0)
            stock_data.append((idx, name, code, pct, amount))

        # 并发处理
        def process_stock(stock_info):
            idx, name, code, pct, amount = stock_info
            board_days = calculate_continuous_limit_up_days_with_retry(code, max_retries=0)
            if board_days > 0:
                board_label = f"{board_days}板"
            else:
                board_label = "首板"
                board_days = 0
            return (idx, name, code, pct, amount, board_days, board_label)

        results_dict = {}
        with ThreadPoolExecutor(max_workers=100) as executor:
            future_to_stock = {executor.submit(process_stock, stock): stock for stock in stock_data}
            for future in as_completed(future_to_stock):
                try:
                    idx, name, code, pct, amount, board_days, board_label = future.result()
                    results_dict[idx] = {
                        'text': f"{name}({code}) {pct:.2f}% 成交额{amount:.2f}亿 [{board_label}]",
                        'board_days': board_days,
                        'name': name
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
                except:
                    idx, name, code, pct, amount = future_to_stock[future]
                    results_dict[idx] = {
                        'text': f"{name}({code}) {pct:.2f}% 成交额{amount:.2f}亿 [首板]",
                        'board_days': 0,
                        'name': name
                    }
                    failed_count += 1

        results = [results_dict[i+1]['text'] for i in range(len(stock_data))]

        # 构建简洁summary
        summary = f"📊 今日涨停股共 {total_count} 只（已过滤ST股），已分析成交额前50只\n\n"

        if board_stats:
            summary += f"🔥 最高板: {max_board}板"
            if max_board > 1 and max_board_stocks:
                summary += f"（{', '.join(max_board_stocks[:3])}）"
            summary += "\n"
            summary += f"📈 连板统计: " + ", ".join([f"{k}板×{v}只" for k, v in sorted(board_stats.items(), reverse=True)]) + "\n\n"

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
        summary += "💹 涨停梯队：\n\n"
        for board_num in sorted(high_boards.keys(), reverse=True):
            stocks = high_boards[board_num]
            summary += f"【{board_num}板】({len(stocks)}只)：\n"
            for stock in stocks[:10]:  # 每个梯队最多显示10只
                summary += f"  {stock}\n"
            if len(stocks) > 10:
                summary += f"  ... 还有{len(stocks)-10}只\n"
            summary += "\n"

        # 显示首板前15只
        if first_boards:
            summary += f"【首板】({len(first_boards)}只，显示前15只)：\n"
            for stock in first_boards[:15]:
                summary += f"  {stock}\n"
            if len(first_boards) > 15:
                summary += f"  ... 还有{len(first_boards)-15}只\n"

        # 保存缓存
        try:
            os.makedirs('./data/limit_up_history', exist_ok=True)
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({'summary': summary, 'timestamp': time.time()}, f, ensure_ascii=False, indent=2)
        except:
            pass

        return summary

    except Exception as e:
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
    - top_k: 返回最相关的前几条结果，默认15

    返回：相关知识的文本内容
    """
    global KNOWLEDGE_BASE

    if KNOWLEDGE_BASE is None:
        return "知识库未初始化，无法搜索"

    try:
        # 使用MMR搜索以增加结果多样性，避免都是同一个文件
        docs = KNOWLEDGE_BASE.max_marginal_relevance_search(
            query,
            k=top_k,
            fetch_k=50,  # 先获取50个候选，再筛选多样性最高的15个
            lambda_mult=0.5  # 平衡相关性和多样性
        )

        results = []
        seen_content = set()
        seen_sources = {}  # 记录每个来源文件出现的次数

        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get('source', '未知')
            content = doc.page_content.strip()

            # 去重：避免返回重复内容
            content_hash = hash(content[:100])
            if content_hash in seen_content:
                continue
            seen_content.add(content_hash)

            # 限制单个文件最多出现2次（避免被屠龙表占据）
            if source not in seen_sources:
                seen_sources[source] = 0
            if seen_sources[source] >= 2 and '屠龙表' in source:
                continue  # 屠龙表最多2条
            seen_sources[source] += 1

            # txt文件优先（经验总结更精炼）
            priority = 0 if '.txt' in source else 1
            results.append((priority, f"【来源: {source}】\n{content}\n"))

            if len(results) >= 5:  # 最多返回5条
                break

        # 按优先级排序
        results.sort(key=lambda x: x[0])
        return "\n---\n".join([r[1] for r in results])
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
    """分析当前市场情绪

    返回：
    - 涨停股数量
    - 跌停股数量
    - 涨停梯队分析
    - 板块效应
    - 情绪判断
    """
    try:
        # 获取涨停数据
        df_zt = fetch_limit_up_stocks()

        # 获取跌停数据（涨幅<-9.5%）
        df_all = fetch_sina_stock_data(num=5000, sort_field='changepercent')
        df_dt = df_all[df_all['涨跌幅'] <= -9.5] if not df_all.empty else pd.DataFrame()

        # 获取板块数据
        df_board = fetch_board_ranking()

        # 统计分析
        zt_count = len(df_zt) if not df_zt.empty else 0
        dt_count = len(df_dt) if not df_dt.empty else 0

        # 板块分析
        strong_boards = []
        if not df_board.empty:
            strong_boards = df_board[df_board['涨跌幅'] > 2].head(5)['板块名称'].tolist()

        # 涨停股前10名
        top_zt = ""
        if not df_zt.empty:
            top10 = df_zt.head(10)
            results = []
            for _, row in top10.iterrows():
                code = row.get('代码', row.get('symbol', ''))
                name = row.get('名称', row.get('name', ''))
                pct = row.get('涨跌幅', 0)
                amount = row.get('成交额', 0) / 1e8
                turnover = row.get('换手率', 0)
                results.append(f"{name}({code}) {pct:.2f}% 成交额{amount:.2f}亿 换手{turnover:.2f}%")
            top_zt = "\n".join(results)

        # 情绪判断
        sentiment = "中性"
        if zt_count > 100 and dt_count < 20:
            sentiment = "极度亢奋"
        elif zt_count > 60:
            sentiment = "偏强"
        elif zt_count < 30:
            sentiment = "偏弱"
        if dt_count > 50:
            sentiment = "恐慌"

        result = f"""
【市场情绪分析】

涨停股数量: {zt_count}只
跌停股数量: {dt_count}只
赚钱效应: {'强' if zt_count > dt_count * 2 else '弱'}
情绪判断: {sentiment}

活跃板块: {', '.join(strong_boards) if strong_boards else '无明显主线'}

涨停股TOP10:
{top_zt if top_zt else '暂无数据'}
"""
        return result

    except Exception as e:
        return f"市场情绪分析失败: {str(e)}"


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
# 构建Agent
# -----------------------------
def build_chat_agent() -> AgentExecutor:
    """构建对话式股票分析Agent - 带知识库和短期记忆"""

    # 使用qwen-turbo模型，更稳定
    llm = ChatTongyi(
        model_name="qwen-turbo",
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
         "你是A股交易助手。你有知识库工具，必须优先使用。\n\n"
         "【必须遵守】\n"
         "用户问题中包含以下关键词时，第一步必须调用search_knowledge：\n"
         "- '为什么' / '为何' → 调用search_knowledge\n"
         "- '如何' → 调用search_knowledge\n"
         "- '什么是' → 调用search_knowledge\n"
         "- '怎么' → 调用search_knowledge\n"
         "- '态度' → 调用search_knowledge\n"
         "- '原则' / '方法' / '技巧' → 调用search_knowledge\n"
         "- '回撤' / '亏损' / '止损' → 调用search_knowledge\n"
         "- '情绪' / '周期' / '打板' / '龙头' → 调用search_knowledge\n\n"
         "调用search_knowledge后，优先使用工具返回的原文内容回答（保留关键表述），\n"
         "可以适当整理使其更清晰易懂。\n\n"
         "【工具】\n"
         "1. search_knowledge - 知识库搜索\n"
         "2. get_limit_up_stocks - 今日涨停\n"
         "3. get_continuous_limit_up_leaders - 连板梯队\n"
         "4. analyze_market_sentiment - 市场情绪\n"
         "5. get_hot_stocks_ranking - 热股榜排行（判断市场热度）\n"
         "6. analyze_profit_effect - 赚钱效应分析（评估市场机会）"),
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
