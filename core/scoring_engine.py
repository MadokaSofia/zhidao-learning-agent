"""
core/scoring_engine.py - 内循环打分引擎
每轮对话实时评估用户认知水平，用户无感知

五维度评分:
1. 概念理解深度 (30%)
2. 逻辑推理能力 (25%)
3. 关联迁移能力 (20%)
4. 举例应用能力 (15%)
5. 追问承接能力 (10%)
"""

from dataclasses import dataclass, field
from typing import Optional
from utils.helpers import calculate_level


@dataclass
class ScoreRecord:
    """单轮打分记录"""
    round_number: int = 0
    concept_depth: float = 0.0        # 概念理解深度 (0-100)
    logic_reasoning: float = 0.0      # 逻辑推理能力 (0-100)
    transfer_ability: float = 0.0     # 关联迁移能力 (0-100)
    example_ability: float = 0.0      # 举例应用能力 (0-100)
    followup_ability: float = 0.0     # 追问承接能力 (0-100)

    @property
    def total_score(self) -> float:
        """加权总分"""
        return (
            self.concept_depth * 0.30 +
            self.logic_reasoning * 0.25 +
            self.transfer_ability * 0.20 +
            self.example_ability * 0.15 +
            self.followup_ability * 0.10
        )

    @property
    def level(self) -> str:
        return calculate_level(self.total_score)

    def to_dict(self) -> dict:
        return {
            "round_number": self.round_number,
            "concept_depth": self.concept_depth,
            "logic_reasoning": self.logic_reasoning,
            "transfer_ability": self.transfer_ability,
            "example_ability": self.example_ability,
            "followup_ability": self.followup_ability,
            "total_score": self.total_score,
            "level_before": "",  # 由 engine 填充
            "level_after": self.level,
        }


class ScoringEngine:
    """内循环打分引擎"""

    def __init__(self):
        self.history: list[ScoreRecord] = []
        self.current_score: float = 30.0  # 初始分数（L2 有印象）
        self.current_level: str = "L2"
        self.consecutive_good: int = 0    # 连续答得好的轮数
        self.consecutive_bad: int = 0     # 连续答得差的轮数

    def update_from_ai_assessment(self, assessment: dict) -> ScoreRecord:
        """
        根据 AI 返回的评估结果更新打分

        Args:
            assessment: AI 分析结果，包含五维度分数
                {
                    "concept_depth": 0-100,
                    "logic_reasoning": 0-100,
                    "transfer_ability": 0-100,
                    "example_ability": 0-100,
                    "followup_ability": 0-100,
                    "has_breakpoint": true/false,
                    "breakpoint_description": "..."
                }

        Returns:
            ScoreRecord
        """
        record = ScoreRecord(
            round_number=len(self.history) + 1,
            concept_depth=float(assessment.get("concept_depth", 30)),
            logic_reasoning=float(assessment.get("logic_reasoning", 30)),
            transfer_ability=float(assessment.get("transfer_ability", 20)),
            example_ability=float(assessment.get("example_ability", 20)),
            followup_ability=float(assessment.get("followup_ability", 30)),
        )

        # 计算新分数（使用移动平均，避免剧烈波动）
        old_level = self.current_level
        alpha = 0.4  # 新分数权重
        self.current_score = (1 - alpha) * self.current_score + alpha * record.total_score
        self.current_level = calculate_level(self.current_score)

        # 更新连续好/差轮数
        if record.total_score >= self.current_score + 5:
            self.consecutive_good += 1
            self.consecutive_bad = 0
        elif record.total_score <= self.current_score - 10:
            self.consecutive_bad += 1
            self.consecutive_good = 0
        else:
            # 分数持平
            pass

        record_dict = record.to_dict()
        record_dict["level_before"] = old_level

        self.history.append(record)

        return record

    def get_strategy_hints(self) -> dict:
        """
        根据打分趋势生成策略提示

        Returns:
            dict 策略提示
        """
        hints = {
            "should_deepen": False,      # 是否应加深难度
            "should_simplify": False,     # 是否应降低难度
            "has_breakpoint": False,      # 是否有认知断点
            "should_branch": False,       # 是否应引入新分支
            "current_score": self.current_score,
            "current_level": self.current_level,
        }

        # 连续2轮都答得好 → 加深
        if self.consecutive_good >= 2:
            hints["should_deepen"] = True
            self.consecutive_good = 0  # 重置

        # 答差时 → 降低 + 标记断点
        if self.consecutive_bad >= 1:
            hints["should_simplify"] = True
            hints["has_breakpoint"] = True

        # 分数稳定在某区间 → 尝试引入新分支
        if len(self.history) >= 4:
            recent = [r.total_score for r in self.history[-4:]]
            score_range = max(recent) - min(recent)
            if score_range < 10:
                hints["should_branch"] = True

        return hints

    def get_score_summary(self) -> dict:
        """获取打分摘要"""
        if not self.history:
            return {
                "current_score": self.current_score,
                "current_level": self.current_level,
                "rounds": 0,
                "trend": "stable",
            }

        # 趋势判断
        if len(self.history) >= 3:
            recent_scores = [r.total_score for r in self.history[-3:]]
            if all(recent_scores[i] <= recent_scores[i + 1] for i in range(len(recent_scores) - 1)):
                trend = "improving"
            elif all(recent_scores[i] >= recent_scores[i + 1] for i in range(len(recent_scores) - 1)):
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "stable"

        return {
            "current_score": self.current_score,
            "current_level": self.current_level,
            "rounds": len(self.history),
            "trend": trend,
            "latest_dimensions": self.history[-1].to_dict() if self.history else None,
        }
