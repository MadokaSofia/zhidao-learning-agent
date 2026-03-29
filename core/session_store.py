"""
core/session_store.py - 会话存档管理器
支持学习进度的保存和恢复（存档/读档）

v3.1 升级：
- Supabase 云端存储（优先）
- 本地 JSON 文件存储（降级方案）
- 两种存储方式透明切换，API 不变
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

    优先使用 Supabase 云端存储，当 Supabase 不可用时降级到本地 JSON 文件
    """

    SAVE_DIR = ".saves"
    MAX_SAVES = 20  # 每个用户最多保存 20 个存档
    AUTOSAVE_ID = "_autosave"  # 自动存档使用的固定 ID

    def __init__(self, db_client=None):
        """
        初始化存档管理器

        Args:
            db_client: DatabaseClient 实例，提供 Supabase 云端存储能力
                       如果为 None 或 Supabase 未启用，将使用本地文件存储
        """
        self.db_client = db_client
        self._use_cloud = bool(db_client and db_client.enabled)
        # 始终创建本地目录作为备用
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
        save_id: str = None,
    ) -> str:
        """
        保存当前会话

        Args:
            save_id: 可选，指定存档 ID（用于自动存档覆盖写）

        Returns:
            存档 ID
        """
        if not save_id:
            save_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        save = SessionSave(
            save_id=save_id,
            user_id=user_id,
            topic=topic,
            mode=mode,
            role=role,
            round_count=round_count,
            timestamp=timestamp,
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

        # 优先云端存储
        if self._use_cloud:
            session_data = {
                "conversation_history": conversation_history,
                "messages_display": messages_display,
                "knowledge_highlights": knowledge_highlights,
                "scoring_history": scoring_data.get("history", []),
                "personality_data": personality_data,
                "knowledge_tree_data": knowledge_tree_data or {},
                "planner_data": planner_data or {},
            }
            success = self.db_client.save_session_snapshot(
                user_id=user_id,
                save_id=save_id,
                topic=topic,
                mode=mode,
                role=role,
                round_count=round_count,
                description=save.description,
                cognitive_level=save.cognitive_level,
                cognitive_score=save.cognitive_score,
                session_data=session_data,
            )
            if success:
                self._cleanup_old_saves_cloud(user_id)
                return save_id

        # 降级到本地文件
        self._save_local(save)
        self._cleanup_old_saves_local(user_id)
        return save_id

    def load_session(self, user_id: str, save_id: str) -> Optional[SessionSave]:
        """加载存档"""
        # 优先从云端加载
        if self._use_cloud:
            data = self.db_client.load_session_snapshot(user_id, save_id)
            if data:
                return SessionSave.from_dict(data)

        # 降级到本地文件
        return self._load_local(user_id, save_id)

    def list_saves(self, user_id: str) -> list[SessionSave]:
        """列出用户的所有存档（不包含自动存档）"""
        # 优先从云端获取
        if self._use_cloud:
            rows = self.db_client.list_session_snapshots(user_id, limit=self.MAX_SAVES)
            if rows:
                saves = []
                for row in rows:
                    # 过滤自动存档
                    if row.get("save_id", "") == self.AUTOSAVE_ID:
                        continue
                    ts = row.get("created_at", "")
                    # 格式化时间戳
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        display_ts = dt.strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        display_ts = ts[:16] if len(ts) > 16 else ts

                    saves.append(SessionSave(
                        save_id=row["save_id"],
                        user_id=row["user_id"],
                        topic=row.get("topic", ""),
                        mode=row.get("mode", "academic"),
                        role=row.get("role", "student"),
                        round_count=row.get("round_count", 0),
                        timestamp=display_ts,
                        description=row.get("description", ""),
                        cognitive_level=row.get("cognitive_level", "L2"),
                        cognitive_score=row.get("cognitive_score", 30),
                    ))
                return saves

        # 降级到本地文件
        return self._list_local(user_id)

    def delete_save(self, user_id: str, save_id: str) -> bool:
        """删除存档"""
        if self._use_cloud:
            success = self.db_client.delete_session_snapshot(user_id, save_id)
            if success:
                return True

        return self._delete_local(user_id, save_id)

    # ==================== 本地文件存储（降级方案） ====================

    def _save_local(self, save: SessionSave):
        """保存到本地 JSON 文件"""
        user_dir = os.path.join(self.SAVE_DIR, save.user_id)
        os.makedirs(user_dir, exist_ok=True)
        filepath = os.path.join(user_dir, f"{save.save_id}.json")

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(save.to_dict(), f, ensure_ascii=False, indent=2)

    def _load_local(self, user_id: str, save_id: str) -> Optional[SessionSave]:
        """从本地 JSON 文件加载"""
        filepath = os.path.join(self.SAVE_DIR, user_id, f"{save_id}.json")
        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SessionSave.from_dict(data)
        except Exception:
            return None

    def _list_local(self, user_id: str) -> list[SessionSave]:
        """列出本地存档（不包含自动存档）"""
        user_dir = os.path.join(self.SAVE_DIR, user_id)
        if not os.path.exists(user_dir):
            return []

        saves = []
        for filename in sorted(os.listdir(user_dir), reverse=True):
            if filename.endswith(".json") and not filename.startswith(self.AUTOSAVE_ID):
                filepath = os.path.join(user_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    save = SessionSave.from_dict(data)
                    saves.append(save)
                except Exception:
                    continue

        return saves

    def _delete_local(self, user_id: str, save_id: str) -> bool:
        """删除本地存档"""
        filepath = os.path.join(self.SAVE_DIR, user_id, f"{save_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False

    def _cleanup_old_saves_cloud(self, user_id: str):
        """清理云端旧存档，保留最近 MAX_SAVES 个"""
        try:
            rows = self.db_client.list_session_snapshots(user_id, limit=100)
            if len(rows) > self.MAX_SAVES:
                for old_row in rows[self.MAX_SAVES:]:
                    self.db_client.delete_session_snapshot(user_id, old_row["save_id"])
        except Exception:
            pass

    def _cleanup_old_saves_local(self, user_id: str):
        """清理本地旧存档，保留最近 MAX_SAVES 个"""
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
