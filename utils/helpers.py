"""
utils/helpers.py - 通用工具函数
"""

import json
import time
import hashlib
from datetime import datetime
from typing import Any, Optional


def generate_session_id() -> str:
    """生成唯一会话 ID"""
    timestamp = str(time.time())
    return hashlib.md5(timestamp.encode()).hexdigest()[:16]


def get_timestamp() -> str:
    """获取当前时间戳字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_json_loads(text: str, default: Any = None) -> Any:
    """安全的 JSON 解析"""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else {}


def truncate_text(text: str, max_length: int = 100) -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def calculate_level(score: float) -> str:
    """根据分数映射认知水平等级"""
    if score <= 20:
        return "L1"
    elif score <= 40:
        return "L2"
    elif score <= 60:
        return "L3"
    elif score <= 80:
        return "L4"
    else:
        return "L5"


def level_description(level: str) -> str:
    """返回认知水平描述"""
    descriptions = {
        "L1": "完全陌生 - 对该领域几乎零认知",
        "L2": "有印象 - 听过一些名词但不理解含义",
        "L3": "基本理解 - 能解释核心概念但推理不稳",
        "L4": "融会贯通 - 能关联、迁移、举例",
        "L5": "可以输出 - 能教别人、能发现新观点",
    }
    return descriptions.get(level, "未知")


def format_score_display(score: float) -> str:
    """格式化分数显示"""
    level = calculate_level(score)
    return f"{level} ({score:.0f}/100)"


def estimate_response_length(personality_patience: float) -> str:
    """根据耐心度估算推荐回复长度"""
    if personality_patience < 0.3:
        return "short"  # 急躁型：简短
    elif personality_patience < 0.7:
        return "medium"  # 中等
    else:
        return "long"  # 耐心型：展开


def format_knowledge_highlight(
    title: str,
    definition: str = "",
    formula: str = "",
    keywords: list[str] = None,
    pitfalls: str = "",
    mode: str = "academic"
) -> str:
    """
    格式化官方知识点高亮卡片

    Args:
        title: 知识点名称
        definition: 官方定义
        formula: 公式（如有）
        keywords: 关键词列表
        pitfalls: 易错点
        mode: academic(学科) 或 explore(探索)
    """
    if mode == "academic":
        card = f"\n📌 **官方知识点**\n"
        card += "━" * 30 + "\n"
        if definition:
            card += f"**【定义】** {definition}\n"
        if formula:
            card += f"**【公式】** {formula}\n"
        if keywords:
            card += f"**【关键词】** {', '.join(keywords)}\n"
        if pitfalls:
            card += f"**【易错点】** {pitfalls}\n"
        card += "━" * 30
    else:
        card = f"\n📎 **专业说法**：{definition}"
        if keywords:
            card += f"\n💡 记住这几个词：{', '.join(keywords)}"

    return card
