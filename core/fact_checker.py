"""
core/fact_checker.py - 知识准确性审查引擎
对 AI 生成的知识点进行二次校验，降低错误知识风险

三层防护：
1. 提示词层：强制 AI 自我审查 + 置信度标注（在 prompt_builder 中）
2. 审查层：对关键知识点进行二次 AI 校验（本文件）
3. 展示层：在界面上标注知识来源和置信度（在 chat 组件中）
"""

import json
from typing import Optional
from core.ai_client import AIClient


class FactChecker:
    """
    知识准确性审查引擎

    对 AI 生成的官方知识点 Highlight 进行二次独立校验
    """

    # 审查提示词
    REVIEW_SYSTEM_PROMPT = """你是一位严谨的学术审查专家。你的唯一任务是审查以下知识点是否准确。

审查标准：
1. 定义是否与权威教材/学术共识一致
2. 公式是否正确（符号、关系、单位）
3. 关键词是否恰当
4. 是否存在常见的错误表述
5. 是否有过度简化导致的不准确

请严格返回 JSON 格式：
{
  "is_accurate": true/false,
  "confidence": 0.0-1.0,
  "issues": ["问题1", "问题2"],
  "corrections": ["修正建议1"],
  "notes": "补充说明"
}

如果知识点完全准确，issues 和 corrections 为空数组。
如果有任何不确定，confidence 必须低于 0.8。"""

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        self._cache: dict[str, dict] = {}  # 简单缓存避免重复审查

    def review_highlight(self, highlight_text: str, topic: str) -> dict:
        """
        审查一个官方知识点 Highlight

        Args:
            highlight_text: 知识点高亮文本
            topic: 所属主题

        Returns:
            {
                "is_accurate": bool,
                "confidence": float,
                "issues": list[str],
                "corrections": list[str],
                "notes": str,
                "badge": str,  # 展示用的标记
            }
        """
        # 缓存检查
        cache_key = hash(highlight_text)
        if cache_key in self._cache:
            return self._cache[cache_key]

        messages = [
            {"role": "system", "content": self.REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": f"学科/主题：{topic}\n\n待审查知识点：\n{highlight_text}"},
        ]

        result = self.ai_client.chat_json(messages, temperature=0.1)

        # 容错处理
        if "error" in result:
            review = {
                "is_accurate": True,
                "confidence": 0.5,
                "issues": [],
                "corrections": [],
                "notes": "审查服务暂时不可用",
                "badge": "⚠️ 未审查",
            }
        else:
            confidence = result.get("confidence", 0.5)
            is_accurate = result.get("is_accurate", True)

            # 生成展示标记
            if is_accurate and confidence >= 0.9:
                badge = "✅ 已审查"
            elif is_accurate and confidence >= 0.7:
                badge = "✅ 基本准确"
            elif not is_accurate:
                badge = "⚠️ 存在问题"
            else:
                badge = "❓ 建议核实"

            review = {
                "is_accurate": is_accurate,
                "confidence": confidence,
                "issues": result.get("issues", []),
                "corrections": result.get("corrections", []),
                "notes": result.get("notes", ""),
                "badge": badge,
            }

        # 缓存结果
        self._cache[cache_key] = review
        return review

    def review_statement(self, statement: str, topic: str) -> dict:
        """
        快速审查一个简单陈述（比内容审查更轻量）

        用于对话过程中快速校验关键断言
        """
        messages = [
            {
                "role": "system",
                "content": """你是学术审查员。判断以下陈述是否准确。
返回 JSON：{"accurate": true/false, "note": "简短说明"}"""
            },
            {"role": "user", "content": f"主题：{topic}\n陈述：{statement}"},
        ]

        result = self.ai_client.chat_json(messages, temperature=0.1)
        return result

    def format_review_badge(self, review: dict) -> str:
        """
        格式化审查结果为展示文本

        Args:
            review: review_highlight 的返回结果

        Returns:
            用于展示在界面上的文本
        """
        badge = review.get("badge", "")
        text = f"\n{badge}"

        if review.get("issues"):
            text += "\n"
            for issue in review["issues"]:
                text += f"\n⚠️ {issue}"

        if review.get("corrections"):
            text += "\n"
            for correction in review["corrections"]:
                text += f"\n✏️ 修正：{correction}"

        if review.get("notes"):
            text += f"\n📝 {review['notes']}"

        return text
