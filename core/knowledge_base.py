"""
core/knowledge_base.py - 教材知识库引擎（RAG）
开发者预注入权威教材，AI 基于教材内容教学，确保知识准确

使用方式：
1. 把教材文件放到 knowledge_base/ 目录下
   支持格式：.txt / .md / .json / .pdf
2. 文件命名建议：「主题名.pdf」如「初中物理-力学.pdf」「AI Agent.md」
3. 系统自动加载、分块、建立索引
4. 对话时自动检索最相关的教材片段，注入到 AI 提示词中
"""

import os
import re
import json
import hashlib
from dataclasses import dataclass
from typing import Optional


# ==================== 数据结构 ====================

@dataclass
class TextChunk:
    """文本块"""
    content: str          # 文本内容
    source: str           # 来源文件名
    topic: str            # 所属主题
    chunk_id: str         # 唯一 ID
    section_title: str    # 所属章节标题
    keywords: list[str]   # 关键词（用于检索）


# ==================== 知识库管理 ====================

class KnowledgeBase:
    """
    教材知识库

    功能：
    - 从 knowledge_base/ 目录加载教材文件
    - 自动分块（按章节/段落）
    - 关键词检索最相关片段
    - 注入到 AI 提示词中
    """

    # 默认知识库目录
    DEFAULT_KB_DIR = "knowledge_base"

    # 分块大小（字符数）
    CHUNK_SIZE = 800
    CHUNK_OVERLAP = 100

    def __init__(self, kb_dir: str = None):
        self.kb_dir = kb_dir or self.DEFAULT_KB_DIR
        self.chunks: list[TextChunk] = []
        self.topics: dict[str, list[TextChunk]] = {}  # 按主题索引
        self._loaded = False

    def load(self):
        """加载知识库目录下的所有文件"""
        if self._loaded:
            return

        if not os.path.exists(self.kb_dir):
            os.makedirs(self.kb_dir, exist_ok=True)
            self._loaded = True
            return

        for filename in os.listdir(self.kb_dir):
            filepath = os.path.join(self.kb_dir, filename)
            if not os.path.isfile(filepath):
                continue

            if filename.endswith(".txt") or filename.endswith(".md"):
                self._load_text_file(filepath, filename)
            elif filename.endswith(".json"):
                self._load_json_file(filepath, filename)
            elif filename.endswith(".pdf"):
                self._load_pdf_file(filepath, filename)

        self._loaded = True

    def _load_text_file(self, filepath: str, filename: str):
        """加载文本/Markdown 文件"""
        topic = os.path.splitext(filename)[0]

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # 按章节分块
        chunks = self._split_by_sections(content, filename, topic)
        self.chunks.extend(chunks)

        if topic not in self.topics:
            self.topics[topic] = []
        self.topics[topic].extend(chunks)

    def _load_pdf_file(self, filepath: str, filename: str):
        """
        加载 PDF 教材文件

        使用 pymupdf 提取文本和图片信息，按页/章节分块
        - 文本：直接提取
        - 图片：提取图片周围的文字描述（图注/标题），标记为[图片]
        """
        try:
            import fitz  # pymupdf
        except ImportError:
            print(f"⚠️ 跳过 PDF 文件 {filename}：请安装 pymupdf (pip install pymupdf)")
            return

        topic = os.path.splitext(filename)[0]
        doc = fitz.open(filepath)

        # 保存提取的图片到目录（供多模态模型使用）
        img_dir = os.path.join(self.kb_dir, f".images_{topic}")
        os.makedirs(img_dir, exist_ok=True)

        # 逐页提取文本 + 图片信息
        full_text = ""
        page_texts = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_content = ""

            # 提取文本（保留排版结构）
            text = page.get_text("text")
            if text.strip():
                page_content += text.strip()

            # 提取图片并保存 + 记录位置信息
            image_list = page.get_images(full=True)
            if image_list:
                saved_count = 0
                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    try:
                        base_image = doc.extract_image(xref)
                        if base_image and base_image.get("image"):
                            img_ext = base_image.get("ext", "png")
                            img_filename = f"p{page_num + 1}_img{img_index + 1}.{img_ext}"
                            img_path = os.path.join(img_dir, img_filename)

                            with open(img_path, "wb") as img_file:
                                img_file.write(base_image["image"])
                            saved_count += 1
                    except Exception:
                        continue

                if saved_count > 0:
                    page_content += f"\n\n[📷 本页包含 {saved_count} 张图片（示意图/公式图/表格），"
                    page_content += f"图片已保存在 {img_dir}/ 目录]"

            if page_content.strip():
                page_texts.append({
                    "page": page_num + 1,
                    "text": page_content.strip(),
                })
                full_text += page_content + "\n\n"

        total_pages = len(doc)
        doc.close()

        if not full_text.strip():
            print(f"⚠️ PDF 文件 {filename} 未提取到文本（可能是扫描版图片PDF）")
            return

        # 尝试按章节标题分块
        # 常见教材章节标题模式：「第X章」「第X节」「X.X」等
        chapter_pattern = re.compile(
            r"(第[一二三四五六七八九十\d]+[章节篇]|"
            r"\d+\.\d+\s|"
            r"[一二三四五六七八九十]+[、.]\s*\S+|"
            r"Chapter\s+\d+)",
            re.MULTILINE
        )

        sections = chapter_pattern.split(full_text)
        titles = chapter_pattern.findall(full_text)

        if len(titles) >= 2:
            # 有明确的章节结构，按章节分块
            for i, section_text in enumerate(sections):
                section_text = section_text.strip()
                if not section_text or len(section_text) < 20:
                    continue

                section_title = titles[i - 1].strip() if i > 0 and i - 1 < len(titles) else f"第{i}部分"

                # 长章节进一步分块
                if len(section_text) > self.CHUNK_SIZE:
                    sub_chunks = self._split_long_text(section_text)
                    for j, sub in enumerate(sub_chunks):
                        chunk = TextChunk(
                            content=sub,
                            source=filename,
                            topic=topic,
                            chunk_id=hashlib.md5(f"{filename}-{i}-{j}".encode()).hexdigest()[:12],
                            section_title=section_title,
                            keywords=self._extract_keywords(sub),
                        )
                        self.chunks.append(chunk)
                        if topic not in self.topics:
                            self.topics[topic] = []
                        self.topics[topic].append(chunk)
                else:
                    chunk = TextChunk(
                        content=section_text,
                        source=filename,
                        topic=topic,
                        chunk_id=hashlib.md5(f"{filename}-{i}".encode()).hexdigest()[:12],
                        section_title=section_title,
                        keywords=self._extract_keywords(section_text),
                    )
                    self.chunks.append(chunk)
                    if topic not in self.topics:
                        self.topics[topic] = []
                    self.topics[topic].append(chunk)
        else:
            # 没有明确章节，按页分块
            for page_info in page_texts:
                text = page_info["text"]
                page_num = page_info["page"]

                if len(text) < 30:
                    continue  # 跳过几乎空白的页

                if len(text) > self.CHUNK_SIZE:
                    sub_chunks = self._split_long_text(text)
                    for j, sub in enumerate(sub_chunks):
                        chunk = TextChunk(
                            content=sub,
                            source=filename,
                            topic=topic,
                            chunk_id=hashlib.md5(f"{filename}-p{page_num}-{j}".encode()).hexdigest()[:12],
                            section_title=f"第{page_num}页",
                            keywords=self._extract_keywords(sub),
                        )
                        self.chunks.append(chunk)
                        if topic not in self.topics:
                            self.topics[topic] = []
                        self.topics[topic].append(chunk)
                else:
                    chunk = TextChunk(
                        content=text,
                        source=filename,
                        topic=topic,
                        chunk_id=hashlib.md5(f"{filename}-p{page_num}".encode()).hexdigest()[:12],
                        section_title=f"第{page_num}页",
                        keywords=self._extract_keywords(text),
                    )
                    self.chunks.append(chunk)
                    if topic not in self.topics:
                        self.topics[topic] = []
                    self.topics[topic].append(chunk)

        print(f"✅ 已加载 PDF：{filename}（{total_pages}页 → {len(self.topics.get(topic, []))}个文本块）")

    def _load_json_file(self, filepath: str, filename: str):
        """
        加载 JSON 格式教材

        期望格式：
        {
            "topic": "初中物理-力学",
            "sections": [
                {
                    "title": "牛顿第一定律",
                    "content": "内容...",
                    "keywords": ["惯性", "力", "运动状态"],
                    "key_points": [
                        {
                            "definition": "牛顿第一定律：...",
                            "formula": "无",
                            "keywords": ["惯性定律"],
                            "pitfalls": ["易错点..."]
                        }
                    ]
                }
            ]
        }
        """
        topic = os.path.splitext(filename)[0]

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            topic = data.get("topic", topic)
            sections = data.get("sections", [])

            for section in sections:
                title = section.get("title", "")
                content = section.get("content", "")
                keywords = section.get("keywords", [])
                key_points = section.get("key_points", [])

                # 组合内容
                full_content = f"## {title}\n\n{content}"
                if key_points:
                    full_content += "\n\n### 官方知识点\n"
                    for kp in key_points:
                        if kp.get("definition"):
                            full_content += f"\n- 定义：{kp['definition']}"
                        if kp.get("formula"):
                            full_content += f"\n- 公式：{kp['formula']}"
                        if kp.get("pitfalls"):
                            full_content += f"\n- 易错点：{'; '.join(kp['pitfalls']) if isinstance(kp['pitfalls'], list) else kp['pitfalls']}"

                chunk = TextChunk(
                    content=full_content,
                    source=filename,
                    topic=topic,
                    chunk_id=hashlib.md5(full_content[:100].encode()).hexdigest()[:12],
                    section_title=title,
                    keywords=keywords,
                )
                self.chunks.append(chunk)

                if topic not in self.topics:
                    self.topics[topic] = []
                self.topics[topic].append(chunk)

    def _split_by_sections(
        self, content: str, source: str, topic: str
    ) -> list[TextChunk]:
        """
        按章节标题和段落分块

        识别 Markdown 标题（# ## ###）和分隔线（---）
        """
        chunks = []
        # 按标题分割
        sections = re.split(r"\n(?=#{1,3}\s)", content)

        for section in sections:
            section = section.strip()
            if not section:
                continue

            # 提取章节标题
            title_match = re.match(r"^(#{1,3})\s+(.+)", section)
            section_title = title_match.group(2).strip() if title_match else ""

            # 如果段落太长，进一步分块
            if len(section) > self.CHUNK_SIZE:
                sub_chunks = self._split_long_text(section)
                for i, sub in enumerate(sub_chunks):
                    chunk = TextChunk(
                        content=sub,
                        source=source,
                        topic=topic,
                        chunk_id=hashlib.md5(sub[:50].encode()).hexdigest()[:12],
                        section_title=section_title,
                        keywords=self._extract_keywords(sub),
                    )
                    chunks.append(chunk)
            else:
                chunk = TextChunk(
                    content=section,
                    source=source,
                    topic=topic,
                    chunk_id=hashlib.md5(section[:50].encode()).hexdigest()[:12],
                    section_title=section_title,
                    keywords=self._extract_keywords(section),
                )
                chunks.append(chunk)

        return chunks

    def _split_long_text(self, text: str) -> list[str]:
        """将过长文本按段落分块，保持重叠"""
        paragraphs = text.split("\n\n")
        chunks = []
        current = ""

        for para in paragraphs:
            if len(current) + len(para) > self.CHUNK_SIZE:
                if current:
                    chunks.append(current.strip())
                    # 重叠：保留上一块末尾
                    overlap = current[-self.CHUNK_OVERLAP:] if len(current) > self.CHUNK_OVERLAP else ""
                    current = overlap + "\n\n" + para
                else:
                    # 单个段落就超长，直接加入
                    chunks.append(para.strip())
                    current = ""
            else:
                current += "\n\n" + para if current else para

        if current.strip():
            chunks.append(current.strip())

        return chunks

    def _extract_keywords(self, text: str) -> list[str]:
        """从文本中提取关键词（简单方法：提取加粗/标记的词）"""
        keywords = []

        # 提取 **加粗** 的词
        bold_matches = re.findall(r"\*\*(.+?)\*\*", text)
        keywords.extend(bold_matches)

        # 提取 「」内的词
        bracket_matches = re.findall(r"「(.+?)」", text)
        keywords.extend(bracket_matches)

        # 提取【】内的词
        square_matches = re.findall(r"【(.+?)】", text)
        keywords.extend(square_matches)

        return list(set(keywords))[:20]

    # ==================== 检索 ====================

    def search(self, query: str, topic: str = None, top_k: int = 3) -> list[TextChunk]:
        """
        根据查询检索最相关的教材片段

        使用关键词匹配（无需向量数据库，轻量级方案）

        Args:
            query: 搜索查询
            topic: 限定主题（可选）
            top_k: 返回前 K 个结果

        Returns:
            最相关的 TextChunk 列表
        """
        self.load()  # 确保已加载

        if not self.chunks:
            return []

        # 候选池
        if topic and topic in self.topics:
            candidates = self.topics[topic]
        elif topic:
            # 模糊匹配主题名
            candidates = []
            topic_lower = topic.lower()
            for t, chunks in self.topics.items():
                if topic_lower in t.lower() or t.lower() in topic_lower:
                    candidates.extend(chunks)
            if not candidates:
                candidates = self.chunks
        else:
            candidates = self.chunks

        # 关键词匹配打分
        query_terms = set(self._tokenize(query))
        scored = []

        for chunk in candidates:
            score = 0
            chunk_text = chunk.content.lower() + " " + " ".join(chunk.keywords).lower()
            chunk_terms = set(self._tokenize(chunk_text))

            # 计算匹配度
            common = query_terms & chunk_terms
            if common:
                score = len(common) / max(len(query_terms), 1)

            # 标题匹配加分
            if chunk.section_title:
                title_terms = set(self._tokenize(chunk.section_title))
                title_common = query_terms & title_terms
                score += len(title_common) * 0.5

            # 关键词完全匹配加分
            for kw in chunk.keywords:
                if kw.lower() in query.lower():
                    score += 1.0

            if score > 0:
                scored.append((score, chunk))

        # 按分数排序
        scored.sort(key=lambda x: x[0], reverse=True)
        return [chunk for _, chunk in scored[:top_k]]

    def _tokenize(self, text: str) -> list[str]:
        """
        简单分词

        中文按字/词切分，英文按空格切分
        """
        text = text.lower().strip()

        # 提取中文词（2-4字组合）和英文单词
        tokens = []

        # 英文单词
        eng_words = re.findall(r"[a-zA-Z]+", text)
        tokens.extend(eng_words)

        # 中文：提取所有中文字符，生成 bigram/trigram
        chinese_chars = re.findall(r"[\u4e00-\u9fff]+", text)
        for segment in chinese_chars:
            # 单字
            tokens.extend(list(segment))
            # bigram
            for i in range(len(segment) - 1):
                tokens.append(segment[i:i+2])
            # trigram
            for i in range(len(segment) - 2):
                tokens.append(segment[i:i+3])

        return tokens

    # ==================== 格式化 ====================

    def format_context(self, chunks: list[TextChunk]) -> str:
        """
        格式化检索到的教材片段，用于注入到 AI 提示词

        Args:
            chunks: 检索到的文本块列表

        Returns:
            格式化后的上下文文本
        """
        if not chunks:
            return ""

        context = "\n## 📖 教材参考资料（你必须优先基于以下内容教学）\n\n"
        context += "⚠️ 以下内容来自开发者预注入的权威教材，讲解时必须以此为准。"
        context += "如果你的知识与教材冲突，以教材为准。\n\n"

        for i, chunk in enumerate(chunks, 1):
            source_info = f"来源：{chunk.source}"
            if chunk.section_title:
                source_info += f" > {chunk.section_title}"

            context += f"### 参考资料 {i}（{source_info}）\n"
            context += f"{chunk.content}\n\n"

        context += "---\n"
        context += "请基于以上教材内容进行教学。"
        context += "可以用自己的话解释，但核心定义、公式、结论必须与教材一致。\n"

        return context

    # ==================== 状态查询 ====================

    def get_stats(self) -> dict:
        """获取知识库统计信息"""
        self.load()
        return {
            "total_chunks": len(self.chunks),
            "total_topics": len(self.topics),
            "topics": list(self.topics.keys()),
            "files": list(set(c.source for c in self.chunks)),
        }

    def has_topic(self, topic: str) -> bool:
        """检查是否有某个主题的教材"""
        self.load()
        if topic in self.topics:
            return True
        topic_lower = topic.lower()
        return any(topic_lower in t.lower() or t.lower() in topic_lower for t in self.topics)
