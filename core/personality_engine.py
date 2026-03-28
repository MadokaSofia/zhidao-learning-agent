"""
core/personality_engine.py - 性格感知引擎
通过对话行为信号自动感知用户性格，动态调整教学策略

四大维度：
1. 耐心程度 (patience): 0=急躁 ~ 1=耐心
2. 自信程度 (confidence): 0=胆怯 ~ 1=自信
3. 主动性 (initiative): 0=被动 ~ 1=主动
4. 思维风格 (thinking_style): 0=具象 ~ 1=抽象
"""

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PersonalityProfile:
    """用户性格画像"""
    patience: float = 0.5       # 耐心程度: 0=急躁 ~ 1=耐心
    confidence: float = 0.5     # 自信程度: 0=胆怯 ~ 1=自信
    initiative: float = 0.5     # 主动性: 0=被动 ~ 1=主动
    thinking_style: float = 0.5  # 思维风格: 0=具象 ~ 1=抽象

    # 辅助状态
    frustration_level: float = 0.0  # 挫败感: 0=无 ~ 1=高
    engagement_level: float = 0.5   # 投入度: 0=低 ~ 1=高
    rounds_observed: int = 0        # 已观察轮数

    def to_dict(self) -> dict:
        return {
            "personality_patience": self.patience,
            "personality_confidence": self.confidence,
            "personality_initiative": self.initiative,
            "personality_thinking_style": self.thinking_style,
        }

    def describe(self) -> str:
        """生成自然语言描述"""
        traits = []
        if self.patience < 0.35:
            traits.append("🐇 急躁型")
        elif self.patience > 0.65:
            traits.append("🐢 耐心型")

        if self.confidence < 0.35:
            traits.append("🌱 胆怯型")
        elif self.confidence > 0.65:
            traits.append("💪 自信型")

        if self.initiative < 0.35:
            traits.append("🪨 被动型")
        elif self.initiative > 0.65:
            traits.append("🔥 主动型")

        if self.thinking_style < 0.35:
            traits.append("🎨 具象偏好")
        elif self.thinking_style > 0.65:
            traits.append("🔮 抽象偏好")

        return " / ".join(traits) if traits else "📊 观察中..."


@dataclass
class BehaviorSignal:
    """单轮对话的行为信号"""
    response_length: int = 0         # 回复字数
    response_time: float = 0.0       # 回复耗时（秒）
    has_question: bool = False       # 是否包含反问
    has_uncertainty: bool = False    # 是否包含不确定表达
    has_assertion: bool = False      # 是否包含确定表达
    is_perfunctory: bool = False     # 是否敷衍
    has_example: bool = False        # 是否自发举例
    has_summary: bool = False        # 是否自发总结
    answered_correctly: bool = False  # 是否答对
    continued_after_error: bool = False  # 答错后是否积极继续


class PersonalityEngine:
    """性格感知引擎"""

    # 不确定性表达关键词
    UNCERTAINTY_KEYWORDS = [
        "我不确定", "可能是", "应该吧", "大概", "也许",
        "不太懂", "好像", "似乎", "感觉", "猜", "不太清楚",
        "不知道对不对", "是不是", "有点", "或许",
    ]

    # 确定性表达关键词
    ASSERTION_KEYWORDS = [
        "我觉得是", "肯定是", "一定是", "就是", "没错",
        "显然", "很明显", "当然", "毫无疑问", "确定",
    ]

    # 敷衍回复
    PERFUNCTORY_PATTERNS = [
        "嗯", "哦", "好的", "好吧", "不知道", "算了",
        "随便", "都行", "ok", "OK", "对", "是",
        "啊", "呃", "emmm",
    ]

    def __init__(self):
        self.profile = PersonalityProfile()
        self.history: list[BehaviorSignal] = []
        self._last_send_time: Optional[float] = None

    def record_message_sent(self):
        """记录系统发送消息的时间（用于计算用户响应耗时）"""
        self._last_send_time = time.time()

    def analyze_response(self, user_message: str, answered_correctly: bool = False) -> BehaviorSignal:
        """
        分析用户回复，提取行为信号

        Args:
            user_message: 用户回复内容
            answered_correctly: 该轮是否答对（由打分引擎提供）

        Returns:
            BehaviorSignal 行为信号
        """
        signal = BehaviorSignal()
        text = user_message.strip()

        # 回复长度
        signal.response_length = len(text)

        # 回复耗时
        if self._last_send_time:
            signal.response_time = time.time() - self._last_send_time
        self._last_send_time = None  # 重置

        # 是否反问
        signal.has_question = "？" in text or "?" in text

        # 不确定表达
        signal.has_uncertainty = any(kw in text for kw in self.UNCERTAINTY_KEYWORDS)

        # 确定表达
        signal.has_assertion = any(kw in text for kw in self.ASSERTION_KEYWORDS)

        # 敷衍判断（回复很短且匹配敷衍模式）
        signal.is_perfunctory = (
            len(text) <= 6 and
            any(text.strip("。，.!！") == p for p in self.PERFUNCTORY_PATTERNS)
        )

        # 自发举例
        example_markers = ["比如", "例如", "就像", "举个例子", "打比方"]
        signal.has_example = any(m in text for m in example_markers)

        # 自发总结
        summary_markers = ["总结", "所以", "也就是说", "换句话说", "归纳", "综上"]
        signal.has_summary = any(m in text for m in summary_markers)

        # 答题结果
        signal.answered_correctly = answered_correctly

        # 答错后继续积极：检查上一轮是否答错，这一轮是否积极
        if self.history and not self.history[-1].answered_correctly:
            signal.continued_after_error = signal.response_length > 10 and not signal.is_perfunctory

        # 保存信号
        self.history.append(signal)

        # 更新性格画像
        self._update_profile(signal)

        return signal

    def _update_profile(self, signal: BehaviorSignal):
        """根据行为信号更新性格画像"""
        p = self.profile
        p.rounds_observed += 1

        # 学习率随轮数递减（前期快调，后期微调）
        lr = max(0.05, 0.3 / (1 + p.rounds_observed * 0.1))

        # === 耐心程度 ===
        patience_delta = 0.0
        if signal.is_perfunctory:
            patience_delta -= 0.15
        if signal.response_length > 50:
            patience_delta += 0.05
        if signal.response_length < 10 and not signal.is_perfunctory:
            patience_delta -= 0.05
        # 回复长度逐渐变短 → 失去耐心
        if len(self.history) >= 3:
            recent_lengths = [s.response_length for s in self.history[-3:]]
            if recent_lengths == sorted(recent_lengths, reverse=True):  # 递减
                patience_delta -= 0.08
        p.patience = max(0.0, min(1.0, p.patience + patience_delta * lr * 3))

        # === 自信程度 ===
        confidence_delta = 0.0
        if signal.has_assertion:
            confidence_delta += 0.1
        if signal.has_uncertainty:
            confidence_delta -= 0.1
        if signal.answered_correctly:
            confidence_delta += 0.05
        if not signal.answered_correctly and signal.response_length > 5:
            confidence_delta -= 0.03
        p.confidence = max(0.0, min(1.0, p.confidence + confidence_delta * lr * 3))

        # === 主动性 ===
        initiative_delta = 0.0
        if signal.has_question:
            initiative_delta += 0.12
        if signal.is_perfunctory:
            initiative_delta -= 0.08
        if signal.response_length > 80:
            initiative_delta += 0.05
        p.initiative = max(0.0, min(1.0, p.initiative + initiative_delta * lr * 3))

        # === 思维风格 ===
        style_delta = 0.0
        if signal.has_example:
            style_delta -= 0.1  # 举例 → 偏具象
        if signal.has_summary:
            style_delta += 0.1  # 总结 → 偏抽象
        p.thinking_style = max(0.0, min(1.0, p.thinking_style + style_delta * lr * 3))

        # === 投入度 ===
        if signal.is_perfunctory:
            p.engagement_level = max(0.0, p.engagement_level - 0.15)
        elif signal.response_length > 30:
            p.engagement_level = min(1.0, p.engagement_level + 0.05)

        # === 挫败感 ===
        if not signal.answered_correctly:
            p.frustration_level = min(1.0, p.frustration_level + 0.1)
        else:
            p.frustration_level = max(0.0, p.frustration_level - 0.15)
        if signal.continued_after_error:
            p.frustration_level = max(0.0, p.frustration_level - 0.1)

    def get_teaching_params(self) -> dict:
        """
        根据当前性格画像生成教学参数

        Returns:
            dict 包含教学策略参数
        """
        p = self.profile

        # 追问深度
        if p.patience < 0.3:
            socratic_depth = 1  # 急躁型：1轮
        elif p.patience < 0.5:
            socratic_depth = 2
        elif p.patience < 0.7:
            socratic_depth = 3
        else:
            socratic_depth = 4  # 耐心型：4轮

        # 讲解长度
        if p.patience < 0.3:
            explanation_length = "ultra_short"  # 3句内
        elif p.patience < 0.5:
            explanation_length = "short"
        elif p.patience < 0.7:
            explanation_length = "medium"
        else:
            explanation_length = "long"

        # 鼓励强度
        if p.confidence < 0.3:
            encouragement = "high"  # 多鼓励
        elif p.confidence < 0.6:
            encouragement = "medium"
        else:
            encouragement = "low"  # 平等切磋

        # 引导方式
        if p.initiative < 0.3:
            guidance_mode = "system_led"  # 系统主导
        elif p.initiative < 0.6:
            guidance_mode = "balanced"
        else:
            guidance_mode = "user_led"  # 用户主导

        # 出题方式
        if p.initiative < 0.4 or p.confidence < 0.4:
            question_style = "multiple_choice"  # 选择题，降低门槛
        else:
            question_style = "open_ended"  # 开放题

        # 讲解风格
        if p.thinking_style < 0.35:
            explanation_style = "concrete_first"  # 先例子后原理
        elif p.thinking_style > 0.65:
            explanation_style = "abstract_first"  # 先原理后例子
        else:
            explanation_style = "balanced"

        # 桥接风格
        if p.patience < 0.3:
            bridge_style = "one_liner"  # 一句话桥接
        elif p.confidence < 0.3:
            bridge_style = "encouraging"  # 鼓励式
        else:
            bridge_style = "detailed"  # 展开对照

        # 需要紧急干预？
        needs_intervention = (
            p.engagement_level < 0.3 or
            p.frustration_level > 0.7 or
            (p.patience < 0.2 and p.rounds_observed > 3)
        )

        return {
            "socratic_depth": socratic_depth,
            "explanation_length": explanation_length,
            "encouragement": encouragement,
            "guidance_mode": guidance_mode,
            "question_style": question_style,
            "explanation_style": explanation_style,
            "bridge_style": bridge_style,
            "needs_intervention": needs_intervention,
            "patience": p.patience,
            "confidence": p.confidence,
            "initiative": p.initiative,
            "thinking_style": p.thinking_style,
            "engagement": p.engagement_level,
            "frustration": p.frustration_level,
        }

    def load_from_profile_data(self, data: dict):
        """从数据库加载的画像数据初始化（作为参考基线）"""
        if data:
            self.profile.patience = data.get("personality_patience", 0.5)
            self.profile.confidence = data.get("personality_confidence", 0.5)
            self.profile.initiative = data.get("personality_initiative", 0.5)
            self.profile.thinking_style = data.get("personality_thinking_style", 0.5)
