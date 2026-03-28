"""
core/memory.py - 跨会话记忆管理器
为 Agent 提供长期记忆能力，记住用户的学习历史

记忆分类：
- breakpoint: 认知断点/薄弱知识点
- highlight: 已掌握的知识点
- preference: 学习偏好（急躁/耐心、具象/抽象等）
- progress: 学习进度摘要

存储方式：
- 优先使用 Supabase（线上部署）
- 回退到本地 JSON 文件（离线/开发环境）
"""

import os
import json
from datetime import datetime
from typing import Optional


class MemoryManager:
    """
    跨会话记忆管理器

    在每次学习会话结束时，Agent 会生成结构化反思：
    - 哪些知识点是薄弱的
    - 哪些已经掌握
    - 用户的学习偏好
    - 进度摘要

    下次会话开始时，Agent 可以通过 recall_memory 工具检索这些信息。
    """

    LOCAL_MEMORY_DIR = ".memory"

    def __init__(self, db_client=None):
        self.db = db_client

    @property
    def _db_enabled(self) -> bool:
        return self.db is not None and hasattr(self.db, 'enabled') and self.db.enabled

    def store(
        self,
        user_id: str,
        topic: str,
        category: str,
        content: str,
        importance: float = 0.5,
        session_id: str = None,
    ):
        """
        存储一条记忆

        Args:
            user_id: 用户 ID
            topic: 学习主题
            category: 记忆分类 (breakpoint/highlight/preference/progress)
            content: 记忆内容
            importance: 重要度 0-1（越高越优先被回忆）
            session_id: 关联的会话 ID
        """
        if self._db_enabled:
            try:
                self._store_supabase(user_id, topic, category, content, importance, session_id)
                return
            except Exception:
                pass
        # 回退到本地
        self._store_local(user_id, topic, category, content, importance)

    def recall(
        self,
        user_id: str,
        topic: str,
        query: str = "",
        category: str = "all",
    ) -> str:
        """
        回忆用户的历史学习记录

        Args:
            user_id: 用户 ID
            topic: 学习主题
            query: 关键词过滤（可选）
            category: 分类过滤（可选，默认 all）

        Returns:
            格式化的记忆摘要文本
        """
        memories = []

        if self._db_enabled:
            try:
                memories = self._recall_supabase(user_id, topic, category)
            except Exception:
                memories = self._recall_local(user_id, topic, category)
        else:
            memories = self._recall_local(user_id, topic, category)

        if not memories:
            return "没有找到该用户之前的学习记录。这可能是第一次学习此主题。"

        # 按关键词过滤（如果有 query）
        if query:
            memories = [m for m in memories if query in m.get("content", "")]
            if not memories:
                return f"没有找到与「{query}」相关的历史记录。"

        return self._format_memories(memories)

    def store_session_reflection(
        self,
        user_id: str,
        topic: str,
        session_id: str,
        reflection: dict,
    ):
        """
        存储会话结束时的反思结果为多条记忆

        Args:
            user_id: 用户 ID
            topic: 学习主题
            session_id: 会话 ID
            reflection: Agent 生成的反思 dict
        """
        # 存储薄弱点
        for wp in reflection.get("weak_points", []):
            if wp:
                self.store(user_id, topic, "breakpoint", wp,
                          importance=0.8, session_id=session_id)

        # 存储已掌握的知识点
        for mc in reflection.get("mastered", []):
            if mc:
                self.store(user_id, topic, "highlight", mc,
                          importance=0.5, session_id=session_id)

        # 存储学习偏好
        prefs = reflection.get("preferences", "")
        if prefs:
            self.store(user_id, topic, "preference", prefs,
                      importance=0.7, session_id=session_id)

        # 存储进度摘要
        progress = reflection.get("progress_summary", "")
        if progress:
            score = reflection.get("final_score", 0)
            content = f"{progress}（认知分数：{score:.0f}）"
            self.store(user_id, topic, "progress", content,
                      importance=0.6, session_id=session_id)

    # ==================== 本地存储 ====================

    def _store_local(self, user_id, topic, category, content, importance):
        """存储到本地 JSON 文件"""
        os.makedirs(self.LOCAL_MEMORY_DIR, exist_ok=True)
        filepath = os.path.join(self.LOCAL_MEMORY_DIR, f"{user_id}.json")

        existing = []
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, Exception):
                existing = []

        existing.append({
            "topic": topic,
            "category": category,
            "content": content,
            "importance": importance,
            "created_at": datetime.now().isoformat(),
        })

        # 限制总条目数（避免文件过大）
        if len(existing) > 200:
            # 按重要度排序，保留最重要的 150 条
            existing.sort(key=lambda x: x.get("importance", 0.5), reverse=True)
            existing = existing[:150]

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    def _recall_local(self, user_id, topic, category):
        """从本地 JSON 读取记忆"""
        filepath = os.path.join(self.LOCAL_MEMORY_DIR, f"{user_id}.json")
        if not os.path.exists(filepath):
            return []

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                all_memories = json.load(f)
        except (json.JSONDecodeError, Exception):
            return []

        # 按主题过滤（模糊匹配）
        topic_lower = topic.lower()
        filtered = [
            m for m in all_memories
            if topic_lower in m.get("topic", "").lower()
            or m.get("topic", "").lower() in topic_lower
        ]

        # 按分类过滤
        if category != "all":
            filtered = [m for m in filtered if m.get("category") == category]

        # 按重要度排序
        filtered.sort(key=lambda x: x.get("importance", 0.5), reverse=True)
        return filtered[:10]

    # ==================== Supabase 存储 ====================

    def _store_supabase(self, user_id, topic, category, content, importance, session_id):
        """存储到 Supabase"""
        data = {
            "user_id": user_id,
            "topic": topic,
            "category": category,
            "content": content,
            "importance": importance,
        }
        if session_id:
            data["session_id"] = session_id

        self.db.save_agent_memory(data)

    def _recall_supabase(self, user_id, topic, category):
        """从 Supabase 读取记忆"""
        memories = self.db.get_agent_memories(user_id, limit=20)

        # 客户端侧过滤（Supabase 客户端 LIKE 支持有限）
        topic_lower = topic.lower()
        relevant = [
            m for m in memories
            if topic_lower in m.get("topic", "").lower()
            or m.get("topic", "").lower() in topic_lower
        ]

        if category != "all":
            relevant = [m for m in relevant if m.get("category") == category]

        return relevant[:10]

    # ==================== 格式化 ====================

    def _format_memories(self, memories: list) -> str:
        """将记忆条目格式化为 Agent 可理解的文本"""
        if not memories:
            return "无历史学习记录。"

        sections = {
            "breakpoint": ("🔴 认知断点/薄弱知识点", []),
            "highlight": ("🟢 已掌握的知识点", []),
            "preference": ("🎨 学习偏好", []),
            "progress": ("📊 学习进度", []),
        }

        for mem in memories:
            cat = mem.get("category", "progress")
            if cat in sections:
                sections[cat][1].append(mem.get("content", ""))

        result = "## 用户学习记忆\n\n"
        has_content = False

        for cat, (title, items) in sections.items():
            if items:
                has_content = True
                result += f"### {title}\n"
                for item in items[:5]:  # 每类最多 5 条
                    result += f"- {item}\n"
                result += "\n"

        if not has_content:
            return "有历史记录但无具体内容。"

        return result
