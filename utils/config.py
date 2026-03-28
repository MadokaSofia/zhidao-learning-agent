"""
utils/config.py - 配置管理器
管理所有应用配置项，从 Streamlit secrets 或环境变量读取
"""

import os
import streamlit as st
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AIConfig:
    """AI 模型配置"""
    provider: str = "deepseek"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    max_tokens: int = 2048
    temperature: float = 0.7


@dataclass
class SupabaseConfig:
    """Supabase 配置"""
    url: str = ""
    key: str = ""


@dataclass
class AppConfig:
    """应用总配置"""
    ai: AIConfig = field(default_factory=AIConfig)
    supabase: SupabaseConfig = field(default_factory=SupabaseConfig)
    debug: bool = False


def load_config() -> AppConfig:
    """
    从 Streamlit secrets 加载配置
    优先读取 st.secrets，回退到环境变量
    """
    config = AppConfig()

    # --- Supabase ---
    config.supabase.url = _get_secret("SUPABASE_URL", "")
    config.supabase.key = _get_secret("SUPABASE_KEY", "")

    # --- AI Provider ---
    provider = _get_secret("AI_PROVIDER", "deepseek").lower()
    config.ai.provider = provider

    if provider == "deepseek":
        config.ai.api_key = _get_secret("DEEPSEEK_API_KEY", "")
        config.ai.base_url = _get_secret("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        config.ai.model = _get_secret("DEEPSEEK_MODEL", "deepseek-chat")
    elif provider == "tongyi":
        config.ai.api_key = _get_secret("TONGYI_API_KEY", "")
        config.ai.base_url = _get_secret(
            "TONGYI_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        config.ai.model = _get_secret("TONGYI_MODEL", "qwen-plus")
    elif provider == "zhipu":
        config.ai.api_key = _get_secret("ZHIPU_API_KEY", "")
        config.ai.base_url = _get_secret("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
        config.ai.model = _get_secret("ZHIPU_MODEL", "glm-4")

    config.debug = _get_secret("DEBUG", "false").lower() == "true"

    return config


def _get_secret(key: str, default: str = "") -> str:
    """从 Streamlit secrets 获取，回退到环境变量"""
    try:
        return str(st.secrets.get(key, os.environ.get(key, default)))
    except Exception:
        return os.environ.get(key, default)


def validate_config(config: AppConfig) -> list[str]:
    """
    校验配置完整性，返回缺失项列表
    """
    missing = []
    if not config.ai.api_key:
        missing.append(f"AI API Key ({config.ai.provider.upper()})")
    if not config.supabase.url:
        missing.append("SUPABASE_URL")
    if not config.supabase.key:
        missing.append("SUPABASE_KEY")
    return missing
