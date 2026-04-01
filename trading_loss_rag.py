"""
针对回撤/亏损问题的增强RAG - 专门优化版本
重点改进：
1. 优先加载错题集、风控相关文档
2. 增强查询扩展（回撤→风险控制、卖点、错误等）
3. 改进Prompt让模型更重视交易教训
"""
import os
import sys

# 导入增强RAG
from enhanced_rag import EnhancedRAG
from langchain_core.prompts import ChatPromptTemplate


class TradingLossRAG(EnhancedRAG):
    """专门用于分析交易失败和回撤的RAG系统"""

    def load_documents(self, max_files: int = None):
        """加载所有文档（并发加载，保持优先级）

        参数：
        - max_files: 最大加载文件数，None表示加载所有
        """
        from pathlib import Path
        from langchain.docstore.document import Document
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time

        documents = []
        folder = Path(self.folder_path)

        if not folder.exists():
            print(f"⚠️  知识库文件夹不存在: {self.folder_path}")
            return documents

        print(f"📚 正在加载知识库（所有文档，并发加载）...", end='', flush=True)

        # 优先级1：短线/超短核心文档（必须加载）
        priority_1_keywords = ["超短", "短线", "打板", "模式", "手法", "情绪", "竞价", "预期", "周期", "屠龙"]

        # 优先级2：错题集和风控文档
        priority_2_keywords = ["错题", "教训", "风控", "原则", "卖点"]

        # 优先级3：核心交易文档
        priority_3_keywords = ["交易", "操作", "战法"]

        all_files = list(folder.glob("*"))

        def get_priority_score(file_path):
            """计算文件优先级分数"""
            name = file_path.name.lower()
            score = 100  # 默认低优先级

            # 检查优先级1
            for keyword in priority_1_keywords:
                if keyword in name:
                    return 1  # 最高优先级

            # 检查优先级2
            for keyword in priority_2_keywords:
                if keyword in name:
                    return 2

            # 检查优先级3
            for keyword in priority_3_keywords:
                if keyword in name:
                    return 3

            return score

        # 按优先级排序（重要文档先处理）
        all_files_sorted = sorted(all_files, key=get_priority_score)

        # 过滤有效文件
        valid_files = []
        for file_path in all_files_sorted:
            if not file_path.is_file():
                continue

            file_name = file_path.name

            # 跳过临时文件
            if file_name.startswith('.~') or file_name.startswith('~$') or file_name.startswith('.'):
                continue

            # 跳过Excel
            if file_path.suffix in ['.xlsx', '.xls']:
                continue

            # 只处理txt、docx和csv
            if file_path.suffix not in ['.txt', '.docx', '.csv']:
                continue

            valid_files.append(file_path)

        print(f' 共{len(valid_files)}个文件', end='', flush=True)

        # 并发加载文档
        loaded_count = 0
        start_time = time.time()

        def load_single_file(file_path):
            """加载单个文件"""
            try:
                file_name = file_path.name
                content = ""
                title = file_name.replace(file_path.suffix, '')

                if file_path.suffix == '.txt':
                    content = self._read_txt_file(str(file_path))
                elif file_path.suffix == '.docx':
                    content, title = self._read_docx_file_with_title(str(file_path))
                elif file_path.suffix == '.csv':
                    content, title = self._read_csv_file(str(file_path))

                # 过滤低质量内容
                if not content or len(content.strip()) < 50:
                    return None

                return Document(
                    page_content=content,
                    metadata={
                        "source": file_name,
                        "title": title,
                        "path": str(file_path),
                        "file_type": file_path.suffix,
                        "char_count": len(content),
                        "priority": get_priority_score(file_path)
                    }
                )
            except Exception:
                return None

        # 使用线程池并发加载
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_file = {executor.submit(load_single_file, fp): fp for fp in valid_files}

            for future in as_completed(future_to_file):
                if max_files is not None and loaded_count >= max_files:
                    break

                doc = future.result()
                if doc:
                    documents.append(doc)
                    loaded_count += 1
                    print('.', end='', flush=True)

        elapsed = time.time() - start_time
        print(f' ✓ 加载了 {loaded_count} 个文件 (耗时 {elapsed:.2f}秒)')

        # 按优先级重新排序（确保高优先级文档在前）
        documents.sort(key=lambda d: d.metadata.get('priority', 100))

        # 显示已加载的优先级文档
        priority_docs = [d.metadata['source'] for d in documents if d.metadata.get('priority', 100) <= 2]
        if priority_docs:
            print(f"  📌 优先文档: {', '.join(priority_docs[:8])}")

        return documents

    def expand_query_for_loss_analysis(self, query: str) -> list:
        """专门针对回撤/亏损问题的查询扩展"""
        # 检测是否是回撤/亏损相关问题
        loss_keywords = ["回撤", "亏损", "失败", "错误", "大跌", "暴跌", "被套", "止损"]

        # 检测是否是短线模式相关问题
        short_term_keywords = ["短线模式", "短线", "模式", "打板", "低吸", "半路", "接力", "龙头"]

        is_loss_question = any(keyword in query for keyword in loss_keywords)
        is_short_term_question = any(keyword in query for keyword in short_term_keywords)

        if is_loss_question:
            # 针对回撤问题的专门扩展
            expanded = [
                query,  # 原始问题
                "什么情况会导致大幅回撤",
                "如何避免大的亏损",
                "风险控制原则",
                "卖点判断",
                "交易错误和教训",
            ]
            print(f"  🎯 识别为回撤/亏损类问题，使用专门查询扩展")
            return expanded
        elif is_short_term_question:
            # 针对短线模式问题的专门扩展
            expanded = [
                query,  # 原始问题
                "屠龙表短线模式",
                "一波流接力模式",
                "趋势接力主升模式",
                "纯趋势模式",
                "短线买卖点",
            ]
            print(f"  🎯 识别为短线模式类问题，优先检索屠龙表CSV")
            return expanded
        else:
            # 使用原有的扩展方法
            return self.expand_query(query)

    def retrieve_with_rerank(self, query: str, top_k: int = 5):
        """重写检索方法，使用专门的查询扩展"""
        # 1. 使用专门的查询扩展
        print(f"🔍 正在扩展查询...", end='', flush=True)
        expanded_queries = self.expand_query_for_loss_analysis(query)
        print(f" ✓ 生成 {len(expanded_queries)} 个查询")

        # 2. 对每个扩展查询进行混合检索
        all_docs = []
        seen_content = set()

        for q in expanded_queries:
            try:
                docs = self.ensemble_retriever.get_relevant_documents(q)

                for doc in docs:
                    content_hash = doc.page_content[:100]
                    if content_hash not in seen_content:
                        seen_content.add(content_hash)
                        all_docs.append(doc)
            except Exception as e:
                continue

        if not all_docs:
            return []

        print(f"📚 检索到 {len(all_docs)} 个候选文档")

        # 3. 重排序（针对短线模式问题，提升CSV文件权重）
        print(f"🎯 正在重排序...", end='', flush=True)

        # 检测是否是短线模式相关查询
        short_term_keywords = ["短线模式", "短线", "模式", "打板", "低吸", "半路", "接力", "龙头"]
        is_short_term_question = any(keyword in query for keyword in short_term_keywords)

        reranked = self._rerank_documents_with_priority(query, all_docs, is_short_term_question)
        print(" ✓")

        return reranked[:top_k]

    def _rerank_documents_with_priority(self, query: str, documents: list, boost_csv: bool = False):
        """重排序文档，可选择性提升CSV文件权重"""
        from langchain.docstore.document import Document

        results = []

        for doc in documents:
            try:
                # 调用父类的基础打分逻辑（简化版）
                content_preview = doc.page_content[:500]

                # 基础相关性评估（简化，避免过多LLM调用）
                score = 5.0  # 默认分数

                # 关键词匹配加分
                query_lower = query.lower()
                content_lower = content_preview.lower()

                if any(word in content_lower for word in query_lower.split()):
                    score += 2.0

                # CSV文件加分（如果是短线模式相关问题）
                source = doc.metadata.get('source', '')
                if boost_csv and source.endswith('.csv'):
                    # CSV文件额外加分
                    score += 2.0
                    # 如果是"短线模式"CSV，额外加更多分
                    if '短线模式' in source:
                        score += 3.0
                        print(f"\n  ⭐ 提升 {source} 权重")

                # 优先级文档加分
                priority = doc.metadata.get('priority', 100)
                if priority <= 2:
                    score += 1.0

                score = max(0, min(10, score))  # 限制在0-10

            except Exception as e:
                score = 5.0

            from enhanced_rag import RetrievalResult
            result = RetrievalResult(
                content=doc.page_content,
                source=doc.metadata.get('source', '未知'),
                score=score,
                metadata=doc.metadata
            )
            results.append(result)

        # 按分数降序排序
        results.sort(key=lambda x: x.score, reverse=True)

        return results

    def answer_short_term_question(self, query: str, context: str = "") -> str:
        """专门回答短线模式相关问题，优先使用屠龙表CSV"""
        # 检索知识
        print("🔍 正在检索短线模式知识（优先屠龙表CSV）...")
        knowledge = self.retrieve(query, top_k=6, use_rerank=True)

        # 专门的Prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "你是一位精通超短线交易的实战导师，专门基于《屠龙表 - 短线模式》来解答问题。\n\n"
             "【核心原则】\n"
             "1. 必须优先引用和解读《屠龙表 - 短线模式.csv》中的具体条目\n"
             "2. 按照CSV表格的结构来组织回答（行情种类、模式种类、名字、周期、场景、条件、买卖点、仓位等）\n"
             "3. 每个模式都要完整介绍其核心要素\n"
             "4. 强调实战细节：买点时机、卖点判断、仓位管理、惩罚机制\n\n"
             "【回答框架】\n"
             "## 短线模式体系概览\n"
             "根据屠龙表，短线模式分为三大类：\n"
             "- 一波流接力模式\n"
             "- 趋势接力/龙头接力主升模式\n"
             "- 纯趋势模式\n\n"
             "## 各模式详细介绍\n"
             "对于每个模式，按以下结构说明：\n"
             "### 【模式名称】\n"
             "- **行情种类**：\n"
             "- **适用周期**：\n"
             "- **胜率高场景**：\n"
             "- **盈亏比**：\n"
             "- **模式条件**：\n"
             "- **买点**：\n"
             "- **卖点**：\n"
             "- **仓位**：\n"
             "- **注意事项**：\n\n"
             "## 实战要点\n"
             "总结关键执行细节和常见误区\n\n"
             "【重要提示】\n"
             "- 必须基于屠龙表CSV的具体内容，逐条引用\n"
             "- 不要遗漏买卖点、仓位管理等关键细节\n"
             "- 要体现表格中的纪律性要求（如惩罚机制）\n"
             "- 保持专业、精准、可执行的风格"),
            ("human",
             "【用户问题】\n{query}\n\n"
             "【知识库检索结果】\n{knowledge}\n\n"
             "【实时上下文】\n{context}\n\n"
             "请基于屠龙表CSV详细介绍短线模式：")
        ])

        try:
            response = self.llm.invoke(
                prompt.format_messages(
                    query=query,
                    knowledge=knowledge,
                    context=context if context else "（无实时数据）"
                )
            )

            return response.content

        except Exception as e:
            return f"分析失败: {str(e)}"

    def answer_loss_question(self, query: str, context: str = "") -> str:
        """专门回答回撤/亏损相关问题"""
        # 检索知识
        print("🔍 正在检索交易教训知识...")
        knowledge = self.retrieve(query, top_k=6, use_rerank=True)

        # 专门的Prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "你是一位经验丰富的股票交易导师，专门分析交易失败和回撤原因。\n\n"
             "【分析框架】\n"
             "用户问到回撤、亏损问题时，你需要从知识库中找到相关的交易原则和教训，\n"
             "用以下框架回答：\n\n"
             "🔍 **回撤原因分析**\n"
             "根据知识库中的交易原则和错题集，分析可能导致回撤的具体原因：\n"
             "- 违反了哪些核心交易原则？\n"
             "- 没有遵守哪些风控规则？\n"
             "- 在哪个市场环境下容易出现这种回撤？\n\n"
             "📋 **知识库中的相关教训**\n"
             "引用知识库中的具体条目（如\"错题集第X条\"、\"交易原则第X条\"）\n\n"
             "⚠️ **避免措施**\n"
             "基于知识库，给出具体的避免措施：\n"
             "- 事前防范：如何识别风险信号\n"
             "- 事中应对：如何及时止损\n"
             "- 事后复盘：如何从中学习\n\n"
             "✅ **正确做法**\n"
             "根据知识库中的原则，说明正确的操作应该是什么\n\n"
             "【重要提示】\n"
             "- 必须基于知识库内容，引用具体的原则和教训\n"
             "- 不要泛泛而谈，要给出可执行的具体建议\n"
             "- 如果知识库中有相关错题案例，一定要引用\n"
             "- 要严肃对待，这关系到资金安全"),
            ("human",
             "【用户问题】\n{query}\n\n"
             "【知识库检索结果】\n{knowledge}\n\n"
             "【实时上下文】\n{context}\n\n"
             "请深入分析回撤原因并给出建议：")
        ])

        try:
            response = self.llm.invoke(
                prompt.format_messages(
                    query=query,
                    knowledge=knowledge,
                    context=context if context else "（无实时数据）"
                )
            )

            return response.content

        except Exception as e:
            return f"分析失败: {str(e)}"

    def search_with_reasoning(self, query: str, context: str = "") -> str:
        """通用知识检索和推理回答方法

        这是agent_ui.py调用的主要方法，用于回答所有基于知识库的问题
        """
        # 检测问题类型，使用专门的处理方法
        loss_keywords = ["回撤", "亏损", "失败", "错误", "大跌", "暴跌", "被套", "止损"]
        short_term_keywords = ["短线模式", "短线", "模式", "打板", "低吸", "半路", "接力", "龙头"]

        is_loss_question = any(keyword in query for keyword in loss_keywords)
        is_short_term_question = any(keyword in query for keyword in short_term_keywords)

        if is_short_term_question and not is_loss_question:
            # 短线模式问题：优先使用屠龙表CSV
            return self.answer_short_term_question(query, context)
        elif is_loss_question:
            # 回撤/亏损问题：使用专门的分析方法
            return self.answer_loss_question(query, context)
        else:
            # 其他问题：使用父类的通用推理方法
            return self.answer_with_reasoning(query, context)


def test_loss_rag():
    """测试回撤分析RAG"""
    print("=" * 70)
    print("📉 交易回撤分析RAG - 专门测试")
    print("=" * 70)

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("\n⚠️  警告：未检测到 DASHSCOPE_API_KEY 环境变量")
        return

    # 初始化专门的RAG
    rag = TradingLossRAG(api_key=api_key, folder_path="./ku")

    # 构建索引
    if not rag.build_enhanced_index():
        print("❌ 索引构建失败")
        return

    # 测试回撤问题
    test_questions = [
        "为什么会出现大的回撤？",
        "什么情况下容易亏钱？",
        "如何避免大幅回撤？",
    ]

    for i, question in enumerate(test_questions, 1):
        print(f"\n{'=' * 70}")
        print(f"📝 测试 {i}/{len(test_questions)}: {question}")
        print(f"{'=' * 70}\n")

        # 使用专门的回答方法
        answer = rag.answer_loss_question(question)
        print(answer)

        if i < len(test_questions):
            import time
            time.sleep(2)

    print(f"\n{'=' * 70}")
    print("✓ 测试完成")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    test_loss_rag()
