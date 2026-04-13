"""
core/session_store.py - 会话存档管理器
支持学习进度的保存和恢复（存档/读档）

功能：
- 保存当前学习会话的完整状态
- 恢复之前的学习会话
- 管理多个存档
"""

import os
import json
from datetime import datetime
from dataclasses import dataclass
from typing import Optional


@dataclass
class SessionSave:
    """存档条目"""
    save_id: str              # 存档 ID
    user_id: str              # 用户 ID
    topic: str                # 学习主题
    mode: str                 # 学习模式
    role: str                 # 用户角色
    round_count: int          # 对话轮数
    timestamp: str            # 保存时间
    description: str = ""     # 存档描述
    cognitive_level: str = "" # 认知水平
    cognitive_score: float = 0

    # 核心状态数据
    conversation_history: list = None
    messages_display: list = None
    knowledge_highlights: list = None
    scoring_history: list = None
    personality_data: dict = None
    knowledge_tree_data: dict = None
    planner_data: dict = None

    def to_dict(self) -> dict:
        return {
            "save_id": self.save_id,
            "user_id": self.user_id,
            "topic": self.topic,
            "mode": self.mode,
            "role": self.role,
            "round_count": self.round_count,
            "timestamp": self.timestamp,
            "description": self.description,
            "cognitive_level": self.cognitive_level,
            "cognitive_score": self.cognitive_score,
            "conversation_history": self.conversation_history or [],
            "messages_display": self.messages_display or [],
            "knowledge_highlights": self.knowledge_highlights or [],
            "scoring_history": self.scoring_history or [],
            "personality_data": self.personality_data or {},
            "knowledge_tree_data": self.knowledge_tree_data or {},
            "planner_data": self.planner_data or {},
        }

    @staticmethod
    def from_dict(data: dict) -> "SessionSave":
        return SessionSave(
            save_id=data.get("save_id", ""),
            user_id=data.get("user_id", ""),
            topic=data.get("topic", ""),
            mode=data.get("mode", "academic"),
            role=data.get("role", "student"),
            round_count=data.get("round_count", 0),
            timestamp=data.get("timestamp", ""),
            description=data.get("description", ""),
            cognitive_level=data.get("cognitive_level", "L2"),
            cognitive_score=data.get("cognitive_score", 30),
            conversation_history=data.get("conversation_history", []),
            messages_display=data.get("messages_display", []),
            knowledge_highlights=data.get("knowledge_highlights", []),
            scoring_history=data.get("scoring_history", []),
            personality_data=data.get("personality_data", {}),
            knowledge_tree_data=data.get("knowledge_tree_data", {}),
            planner_data=data.get("planner_data", {}),
        )

    def summary_text(self) -> str:
        """生成摘要文本用于显示"""
        return (
            f"📖 {self.topic} | {self.cognitive_level} ({self.cognitive_score:.0f}分) | "
            f"{self.round_count}轮对话 | {self.timestamp}"
        )


class SessionStore:
    """
    会话存档管理器

    以本地 JSON 文件保存，每个用户一个存档目录
    """

    SAVE_DIR = ".saves"
    MAX_SAVES = 20  # 每个用户最多保存 20 个存档

    def __init__(self):
        os.makedirs(self.SAVE_DIR, exist_ok=True)

    def save_session(
        self,
        user_id: str,
        topic: str,
        mode: str,
        role: str,
        round_count: int,
        conversation_history: list,
        messages_display: list,
        knowledge_highlights: list,
        scoring_data: dict,
        personality_data: dict,
        knowledge_tree_data: dict = None,
        planner_data: dict = None,
        description: str = "",
    ) -> str:
        """
        保存当前会话

        Returns:
            存档 ID
        """
        save_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        save = SessionSave(
            save_id=save_id,
            user_id=user_id,
            topic=topic,
            mode=mode,
            role=role,
            round_count=round_count,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
            description=description or f"{topic} - 第{round_count}轮",
            cognitive_level=scoring_data.get("current_level", "L2"),
            cognitive_score=scoring_data.get("current_score", 30),
            conversation_history=conversation_history,
            messages_display=messages_display,
            knowledge_highlights=knowledge_highlights,
            scoring_history=scoring_data.get("history", []),
            personality_data=personality_data,
            knowledge_tree_data=knowledge_tree_data or {},
            planner_data=planner_data or {},
        )

        # 保存到文件
        user_dir = os.path.join(self.SAVE_DIR, user_id)
        os.makedirs(user_dir, exist_ok=True)
        filepath = os.path.join(user_dir, f"{save_id}.json")

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(save.to_dict(), f, ensure_ascii=False, indent=2)

        # 限制存档数量
        self._cleanup_old_saves(user_id)

        return save_id

    def load_session(self, user_id: str, save_id: str) -> Optional[SessionSave]:
        """加载存档"""
        filepath = os.path.join(self.SAVE_DIR, user_id, f"{save_id}.json")
        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SessionSave.from_dict(data)
        except Exception:
            return None

    def list_saves(self, user_id: str) -> list[SessionSave]:
        """列出用户的所有存档"""
        user_dir = os.path.join(self.SAVE_DIR, user_id)
        if not os.path.exists(user_dir):
            return []

        saves = []
        for filename in sorted(os.listdir(user_dir), reverse=True):
            if filename.endswith(".json"):
                filepath = os.path.join(user_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    save = SessionSave.from_dict(data)
                    saves.append(save)
                except Exception:
                    continue

        return saves

    def delete_save(self, user_id: str, save_id: str) -> bool:
        """删除存档"""
        filepath = os.path.join(self.SAVE_DIR, user_id, f"{save_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False

    def _cleanup_old_saves(self, user_id: str):
        """清理旧存档，保留最近 MAX_SAVES 个"""
        user_dir = os.path.join(self.SAVE_DIR, user_id)
        if not os.path.exists(user_dir):
            return

        files = sorted(os.listdir(user_dir), reverse=True)
        if len(files) > self.MAX_SAVES:
            for old_file in files[self.MAX_SAVES:]:
                filepath = os.path.join(user_dir, old_file)
                try:
                    os.remove(filepath)
                except Exception:
                    pass
