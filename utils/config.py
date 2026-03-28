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
    knowledge_base_dir: str = ""  # 自定义教材目录路径（留空则用默认的 knowledge_base/）


def load_config() -> AppConfig:
    """
    从 Streamlit secrets 加载配置
    支持两种配置方式：
    1. [ai] 段直接配置 api_key / base_url / model
    2. 按 provider 分开配置（DEEPSEEK_API_KEY 等）
    """
    config = AppConfig()

    # --- Supabase ---
    config.supabase.url = _get_secret("SUPABASE_URL", "")
    config.supabase.key = _get_secret("SUPABASE_KEY", "")

    # --- 方式1：尝试从 [ai] 段直接读取 ---
    ai_key = _get_secret_section("ai", "api_key", "")
    ai_base_url = _get_secret_section("ai", "base_url", "")
    ai_model = _get_secret_section("ai", "model", "")

    if ai_key:
        config.ai.api_key = ai_key
        config.ai.base_url = ai_base_url or "https://api.deepseek.com"
        config.ai.model = ai_model or "deepseek-chat"
        config.ai.provider = "custom"
    else:
        # --- 方式2：按 provider 分开读取 ---
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

    # --- 教材知识库路径 ---
    config.knowledge_base_dir = _get_secret_section("ai", "knowledge_base_dir", "")

    return config


def _get_secret(key: str, default: str = "") -> str:
    """从 Streamlit secrets 获取，回退到环境变量"""
    try:
        return str(st.secrets.get(key, os.environ.get(key, default)))
    except Exception:
        return os.environ.get(key, default)


def _get_secret_section(section: str, key: str, default: str = "") -> str:
    """从 Streamlit secrets 的嵌套 section 获取值（如 [ai].api_key）"""
    try:
        section_data = st.secrets.get(section, {})
        if isinstance(section_data, dict):
            return str(section_data.get(key, default))
        return default
    except Exception:
        return default


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
