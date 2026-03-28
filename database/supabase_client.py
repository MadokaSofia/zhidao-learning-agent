"""
database/supabase_client.py - Supabase 数据库客户端
负责所有数据的持久化操作
"""

import json
import streamlit as st
from datetime import datetime
from typing import Any, Optional
from utils.config import AppConfig

# SQL schema for creating tables (run once in Supabase Dashboard)
CREATE_TABLES_SQL = """
-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email TEXT UNIQUE,
    display_name TEXT,
    role TEXT DEFAULT 'student',  -- student / professional / curious
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 用户画像表
CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    cognitive_level TEXT DEFAULT 'L1',
    cognitive_score FLOAT DEFAULT 0,
    personality_patience FLOAT DEFAULT 0.5,
    personality_confidence FLOAT DEFAULT 0.5,
    personality_initiative FLOAT DEFAULT 0.5,
    personality_thinking_style FLOAT DEFAULT 0.5,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, topic)
);

-- 学习会话表
CREATE TABLE IF NOT EXISTS learning_sessions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    mode TEXT DEFAULT 'academic',  -- academic / explore
    start_time TIMESTAMPTZ DEFAULT NOW(),
    end_time TIMESTAMPTZ,
    rounds INTEGER DEFAULT 0,
    start_level TEXT,
    end_level TEXT,
    summary TEXT
);

-- 内循环打分日志
CREATE TABLE IF NOT EXISTS scoring_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id UUID REFERENCES learning_sessions(id) ON DELETE CASCADE,
    round_number INTEGER,
    concept_depth FLOAT DEFAULT 0,
    logic_reasoning FLOAT DEFAULT 0,
    transfer_ability FLOAT DEFAULT 0,
    example_ability FLOAT DEFAULT 0,
    followup_ability FLOAT DEFAULT 0,
    total_score FLOAT DEFAULT 0,
    level_before TEXT,
    level_after TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 错题本
CREATE TABLE IF NOT EXISTS wrong_answers (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id UUID REFERENCES learning_sessions(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    question TEXT,
    user_answer TEXT,
    correct_answer TEXT,
    knowledge_point TEXT,
    is_fixed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 官方知识点高亮
CREATE TABLE IF NOT EXISTS knowledge_highlights (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id UUID REFERENCES learning_sessions(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    topic TEXT,
    title TEXT,
    definition TEXT,
    formula TEXT,
    keywords TEXT[],
    pitfalls TEXT,
    mode TEXT DEFAULT 'academic',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 认知断点记录
CREATE TABLE IF NOT EXISTS cognitive_breakpoints (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id UUID REFERENCES learning_sessions(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    breakpoint_description TEXT,
    knowledge_point TEXT,
    is_repaired BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 知识图谱
CREATE TABLE IF NOT EXISTS knowledge_maps (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    map_data JSONB DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, topic)
);

-- 会话笔记
CREATE TABLE IF NOT EXISTS session_notes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id UUID REFERENCES learning_sessions(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    content TEXT,
    highlights_summary TEXT,
    action_items TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 新观点库
CREATE TABLE IF NOT EXISTS new_insights (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id UUID REFERENCES learning_sessions(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    topic TEXT,
    insight TEXT,
    discussion TEXT,
    is_validated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 开启 RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE learning_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE scoring_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE wrong_answers ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_highlights ENABLE ROW LEVEL SECURITY;
ALTER TABLE cognitive_breakpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_maps ENABLE ROW LEVEL SECURITY;
ALTER TABLE session_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE new_insights ENABLE ROW LEVEL SECURITY;
"""


class DatabaseClient:
    """Supabase 数据库客户端封装"""

    def __init__(self, config: AppConfig):
        self.config = config
        self._client = None
        self._enabled = bool(config.supabase.url and config.supabase.key)

    @property
    def client(self):
        """懒加载 Supabase 客户端"""
        if self._client is None and self._enabled:
            try:
                from supabase import create_client
                self._client = create_client(
                    self.config.supabase.url,
                    self.config.supabase.key
                )
            except Exception as e:
                st.warning(f"Supabase 连接失败，数据将仅保存在当前会话中: {e}")
                self._enabled = False
        return self._client

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ==================== 用户管理 ====================

    def get_or_create_user(self, user_id: str, role: str = "student") -> dict:
        """获取或创建用户"""
        if not self.enabled:
            return {"id": user_id, "role": role}

        try:
            result = self.client.table("users").select("*").eq("id", user_id).execute()
            if result.data:
                return result.data[0]

            new_user = {"id": user_id, "role": role}
            result = self.client.table("users").insert(new_user).execute()
            return result.data[0] if result.data else new_user
        except Exception:
            return {"id": user_id, "role": role}

    def update_user_role(self, user_id: str, role: str):
        """更新用户角色"""
        if not self.enabled:
            return
        try:
            self.client.table("users").update({"role": role}).eq("id", user_id).execute()
        except Exception:
            pass

    # ==================== 用户画像 ====================

    def get_user_profile(self, user_id: str, topic: str) -> Optional[dict]:
        """获取特定主题的用户画像"""
        if not self.enabled:
            return None
        try:
            result = (
                self.client.table("user_profiles")
                .select("*")
                .eq("user_id", user_id)
                .eq("topic", topic)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception:
            return None

    def upsert_user_profile(self, user_id: str, topic: str, profile_data: dict):
        """插入或更新用户画像"""
        if not self.enabled:
            return
        try:
            data = {
                "user_id": user_id,
                "topic": topic,
                "updated_at": datetime.now().isoformat(),
                **profile_data,
            }
            self.client.table("user_profiles").upsert(
                data, on_conflict="user_id,topic"
            ).execute()
        except Exception:
            pass

    # ==================== 学习会话 ====================

    def create_session(self, user_id: str, topic: str, mode: str) -> Optional[str]:
        """创建新的学习会话，返回 session_id"""
        if not self.enabled:
            return None
        try:
            data = {
                "user_id": user_id,
                "topic": topic,
                "mode": mode,
            }
            result = self.client.table("learning_sessions").insert(data).execute()
            return result.data[0]["id"] if result.data else None
        except Exception:
            return None

    def update_session(self, session_id: str, updates: dict):
        """更新学习会话"""
        if not self.enabled or not session_id:
            return
        try:
            self.client.table("learning_sessions").update(updates).eq("id", session_id).execute()
        except Exception:
            pass

    # ==================== 打分日志 ====================

    def save_scoring_log(self, session_id: str, log_data: dict):
        """保存内循环打分日志"""
        if not self.enabled or not session_id:
            return
        try:
            data = {"session_id": session_id, **log_data}
            self.client.table("scoring_logs").insert(data).execute()
        except Exception:
            pass

    # ==================== 错题本 ====================

    def save_wrong_answer(self, session_id: str, user_id: str, data: dict):
        """保存错题"""
        if not self.enabled:
            return
        try:
            record = {"session_id": session_id, "user_id": user_id, **data}
            self.client.table("wrong_answers").insert(record).execute()
        except Exception:
            pass

    def get_wrong_answers(self, user_id: str, topic: str = None) -> list:
        """获取错题"""
        if not self.enabled:
            return []
        try:
            query = self.client.table("wrong_answers").select("*").eq("user_id", user_id)
            if topic:
                query = query.eq("knowledge_point", topic)
            result = query.order("created_at", desc=True).execute()
            return result.data or []
        except Exception:
            return []

    # ==================== 知识点高亮 ====================

    def save_knowledge_highlight(self, session_id: str, user_id: str, data: dict):
        """保存知识点高亮"""
        if not self.enabled:
            return
        try:
            record = {"session_id": session_id, "user_id": user_id, **data}
            self.client.table("knowledge_highlights").insert(record).execute()
        except Exception:
            pass

    def get_knowledge_highlights(self, user_id: str, topic: str = None) -> list:
        """获取知识点高亮"""
        if not self.enabled:
            return []
        try:
            query = (
                self.client.table("knowledge_highlights")
                .select("*")
                .eq("user_id", user_id)
            )
            if topic:
                query = query.eq("topic", topic)
            result = query.order("created_at", desc=True).execute()
            return result.data or []
        except Exception:
            return []

    # ==================== 认知断点 ====================

    def save_cognitive_breakpoint(self, session_id: str, user_id: str, data: dict):
        """保存认知断点"""
        if not self.enabled:
            return
        try:
            record = {"session_id": session_id, "user_id": user_id, **data}
            self.client.table("cognitive_breakpoints").insert(record).execute()
        except Exception:
            pass

    # ==================== 知识图谱 ====================

    def get_knowledge_map(self, user_id: str, topic: str) -> Optional[dict]:
        """获取知识图谱"""
        if not self.enabled:
            return None
        try:
            result = (
                self.client.table("knowledge_maps")
                .select("*")
                .eq("user_id", user_id)
                .eq("topic", topic)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception:
            return None

    def upsert_knowledge_map(self, user_id: str, topic: str, map_data: dict):
        """插入或更新知识图谱"""
        if not self.enabled:
            return
        try:
            data = {
                "user_id": user_id,
                "topic": topic,
                "map_data": json.dumps(map_data),
                "updated_at": datetime.now().isoformat(),
            }
            self.client.table("knowledge_maps").upsert(
                data, on_conflict="user_id,topic"
            ).execute()
        except Exception:
            pass

    # ==================== 会话笔记 ====================

    def save_session_notes(self, session_id: str, user_id: str, data: dict):
        """保存会话笔记"""
        if not self.enabled:
            return
        try:
            record = {"session_id": session_id, "user_id": user_id, **data}
            self.client.table("session_notes").insert(record).execute()
        except Exception:
            pass

    def get_session_notes(self, user_id: str) -> list:
        """获取所有会话笔记"""
        if not self.enabled:
            return []
        try:
            result = (
                self.client.table("session_notes")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )
            return result.data or []
        except Exception:
            return []

    # ==================== 新观点库 ====================

    def save_insight(self, session_id: str, user_id: str, data: dict):
        """保存新观点"""
        if not self.enabled:
            return
        try:
            record = {"session_id": session_id, "user_id": user_id, **data}
            self.client.table("new_insights").insert(record).execute()
        except Exception:
            pass
