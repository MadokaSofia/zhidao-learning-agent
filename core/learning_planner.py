"""
core/learning_planner.py - 学习计划管理器
目标驱动的学习规划：知识树拆解 → 摸底测试 → 智能计划 → 动态调整

流程：
1. 用户设定学习目标（对话中自然表达）
2. AI 拆解知识树（底层完成，用户不可见）
3. 摸底测试（综合知识点和考试难度）
4. 生成个性化学习计划
5. 执行学习 + 动态调整
"""

import json
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timedelta


@dataclass
class DailyPlan:
    """每日学习计划"""
    day: int                        # 第几天
    date: str = ""                  # 日期
    node_ids: list = field(default_factory=list)  # 今日要学的知识点 ID
    node_names: list = field(default_factory=list)  # 知识点名称
    completed_ids: list = field(default_factory=list)  # 已完成的
    status: str = "pending"         # pending/in_progress/completed

    def to_dict(self) -> dict:
        return {
            "day": self.day,
            "date": self.date,
            "node_ids": self.node_ids,
            "node_names": self.node_names,
            "completed_ids": self.completed_ids,
            "status": self.status,
        }

    @staticmethod
    def from_dict(data: dict) -> "DailyPlan":
        return DailyPlan(
            day=data.get("day", 0),
            date=data.get("date", ""),
            node_ids=data.get("node_ids", []),
            node_names=data.get("node_names", []),
            completed_ids=data.get("completed_ids", []),
            status=data.get("status", "pending"),
        )


@dataclass
class LearningGoal:
    """学习目标"""
    topic: str = ""                 # 学习主题
    target_days: int = 7            # 目标天数
    start_date: str = ""            # 开始日期
    daily_plans: list = field(default_factory=list)  # DailyPlan 列表
    current_day: int = 1            # 当前第几天
    diagnostic_done: bool = False   # 是否完成摸底测试
    diagnostic_results: dict = field(default_factory=dict)  # 摸底结果

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "target_days": self.target_days,
            "start_date": self.start_date,
            "daily_plans": [dp.to_dict() for dp in self.daily_plans],
            "current_day": self.current_day,
            "diagnostic_done": self.diagnostic_done,
            "diagnostic_results": self.diagnostic_results,
        }

    @staticmethod
    def from_dict(data: dict) -> "LearningGoal":
        goal = LearningGoal(
            topic=data.get("topic", ""),
            target_days=data.get("target_days", 7),
            start_date=data.get("start_date", ""),
            current_day=data.get("current_day", 1),
            diagnostic_done=data.get("diagnostic_done", False),
            diagnostic_results=data.get("diagnostic_results", {}),
        )
        goal.daily_plans = [
            DailyPlan.from_dict(dp) for dp in data.get("daily_plans", [])
        ]
        return goal


class LearningPlanner:
    """
    学习计划管理器

    职责：
    - 生成 AI 提示词让 AI 拆解知识树
    - 根据摸底测试结果 + 知识树生成学习计划
    - 动态调整计划（根据实际学习情况）
    - 提供当前任务信息
    """

    def __init__(self):
        self.goal: Optional[LearningGoal] = None
        self.knowledge_tree = None  # 由外部设置

    @property
    def has_active_plan(self) -> bool:
        return self.goal is not None and len(self.goal.daily_plans) > 0

    # ==================== AI 提示词生成 ====================

    def build_tree_generation_prompt(self, topic: str) -> list[dict]:
        """生成让 AI 拆解知识树的提示词"""
        return [
            {
                "role": "system",
                "content": """你是一个教育专家。请将指定学科/主题拆解为完整的知识树结构。

要求：
1. 按照教材的标准章节结构拆解
2. 每个章节下有具体的知识点，知识点下有子知识点
3. 标注每个章节/知识点的考试权重（0-1，所有权重之和约为1）
4. 标注每个知识点的难度（0-1）
5. 覆盖该学科的所有核心考点

严格返回 JSON 格式：
{
    "topic": "学科名称",
    "chapters": [
        {
            "name": "章节名",
            "exam_weight": 0.3,
            "sections": [
                {
                    "name": "知识点名",
                    "exam_weight": 0.4,
                    "difficulty": 0.3,
                    "sub_points": ["子知识点1", "子知识点2"]
                }
            ]
        }
    ]
}"""
            },
            {
                "role": "user",
                "content": f"请拆解「{topic}」的完整知识树。要求覆盖所有核心知识点和考点。",
            },
        ]

    def build_diagnostic_prompt(self, topic: str, knowledge_tree_summary: str) -> str:
        """
        生成摸底测试提示词
        综合知识点和考试难度出题
        """
        return f"""现在需要对用户进行「{topic}」的摸底水平测试。

以下是该学科的知识树结构：
{knowledge_tree_summary}

请出一组摸底题（5道），要求：
1. 覆盖不同章节的核心知识点
2. 综合考试难度，题目难度分布为：2道基础题 + 2道中等题 + 1道较难题
3. 用选择题形式，每题4个选项
4. 每道题标注考查的知识点
5. 语气轻松亲切，告诉用户这只是「热身小测」
6. 一次出一题，不要一次全出完
7. 先和用户打个招呼，然后出第一道题

开始吧！"""

    # ==================== 计划生成 ====================

    def create_goal(self, topic: str, target_days: int = 7):
        """创建学习目标"""
        self.goal = LearningGoal(
            topic=topic,
            target_days=target_days,
            start_date=datetime.now().strftime("%Y-%m-%d"),
        )

    def generate_plan_from_diagnostic(
        self, diagnostic_results: dict, knowledge_tree
    ):
        """
        根据摸底测试结果 + 知识树生成学习计划

        Args:
            diagnostic_results: {
                "mastered_nodes": ["node_id1", ...],
                "weak_nodes": ["node_id2", ...],
                "unknown_nodes": ["node_id3", ...],
            }
            knowledge_tree: KnowledgeTree 实例
        """
        if not self.goal:
            return

        self.goal.diagnostic_done = True
        self.goal.diagnostic_results = diagnostic_results
        self.knowledge_tree = knowledge_tree

        # 获取所有需要学习的知识点（排除已掌握的）
        mastered_ids = set(diagnostic_results.get("mastered_nodes", []))
        all_leaves = knowledge_tree.get_leaf_nodes()

        # 分类知识点
        to_learn = []
        for node in all_leaves:
            if node.id in mastered_ids:
                # 已掌握的标记为轻量复习
                knowledge_tree.update_node_score(node.id, 85)
                continue
            to_learn.append(node)

        # 按优先级排序：高考试权重 + 薄弱优先
        weak_ids = set(diagnostic_results.get("weak_nodes", []))
        to_learn.sort(
            key=lambda n: (
                1 if n.id in weak_ids else 0,  # 薄弱优先
                n.exam_weight,                   # 高权重优先
                -n.difficulty,                   # 先易后难
            ),
            reverse=True,
        )

        # 按天分配
        days = self.goal.target_days
        nodes_per_day = max(1, len(to_learn) // days)
        # 如果有余数，前几天多分配一些
        remainder = len(to_learn) % days

        self.goal.daily_plans = []
        idx = 0
        for d in range(1, days + 1):
            count = nodes_per_day + (1 if d <= remainder else 0)
            day_nodes = to_learn[idx:idx + count]
            idx += count

            plan = DailyPlan(
                day=d,
                date=(datetime.now() + timedelta(days=d - 1)).strftime("%Y-%m-%d"),
                node_ids=[n.id for n in day_nodes],
                node_names=[n.name for n in day_nodes],
            )
            self.goal.daily_plans.append(plan)

    # ==================== 动态调整 ====================

    def complete_node(self, node_id: str, score: float):
        """
        完成一个知识点学习，根据分数决定是否需要调整计划

        Args:
            node_id: 知识点 ID
            score: 掌握分数 0-100

        Returns:
            调整建议文本（如果需要调整）
        """
        if not self.goal or not self.knowledge_tree:
            return None

        # 更新知识树
        self.knowledge_tree.update_node_score(node_id, score)

        # 更新当天计划
        current_plan = self.get_current_day_plan()
        if current_plan and node_id in current_plan.node_ids:
            if node_id not in current_plan.completed_ids:
                current_plan.completed_ids.append(node_id)

            # 检查是否完成今日所有任务
            if len(current_plan.completed_ids) >= len(current_plan.node_ids):
                current_plan.status = "completed"

        # 动态调整逻辑
        if score < 50:
            # 薄弱 → 后续计划自动顺延，当前知识点需要重新安排
            return self._adjust_for_weak_node(node_id)

        return None

    def _adjust_for_weak_node(self, weak_node_id: str) -> str:
        """当知识点薄弱时调整计划"""
        if not self.goal:
            return ""

        # 找到这个节点在哪天
        node_name = ""
        node = self.knowledge_tree.nodes.get(weak_node_id) if self.knowledge_tree else None
        if node:
            node_name = node.name

        # 在后续计划中插入复习
        future_plans = [
            dp for dp in self.goal.daily_plans
            if dp.day > self.goal.current_day
        ]
        if future_plans:
            # 在下一天的开头插入复习
            next_plan = future_plans[0]
            if weak_node_id not in next_plan.node_ids:
                next_plan.node_ids.insert(0, weak_node_id)
                next_plan.node_names.insert(0, f"复习:{node_name}")

        return f"「{node_name}」掌握不够牢固，已自动安排复习巩固。"

    def advance_day(self):
        """推进到下一天"""
        if self.goal:
            self.goal.current_day = min(
                self.goal.current_day + 1,
                self.goal.target_days
            )

    # ==================== 查询 ====================

    def get_current_day_plan(self) -> Optional[DailyPlan]:
        """获取当天学习计划"""
        if not self.goal or not self.goal.daily_plans:
            return None

        day = self.goal.current_day
        for dp in self.goal.daily_plans:
            if dp.day == day:
                return dp
        return None

    def get_next_node_to_learn(self) -> Optional[str]:
        """获取下一个要学习的知识点 ID"""
        plan = self.get_current_day_plan()
        if not plan:
            return None

        for nid in plan.node_ids:
            if nid not in plan.completed_ids:
                return nid
        return None

    def get_plan_summary(self) -> str:
        """获取计划摘要（用于 Agent 上下文）"""
        if not self.goal:
            return "当前没有学习计划。"

        plan = self.get_current_day_plan()
        if not plan:
            return "学习计划已完成！"

        total_nodes = sum(len(dp.node_ids) for dp in self.goal.daily_plans)
        completed_nodes = sum(len(dp.completed_ids) for dp in self.goal.daily_plans)

        lines = [
            f"📅 学习计划：{self.goal.topic}（{self.goal.target_days}天）",
            f"总进度：{completed_nodes}/{total_nodes} 知识点",
            f"今日（Day {plan.day}）任务：{len(plan.node_ids)} 个知识点",
        ]

        for i, (nid, name) in enumerate(zip(plan.node_ids, plan.node_names)):
            if nid in plan.completed_ids:
                lines.append(f"  ✅ {name}")
            elif i == 0 or (i > 0 and plan.node_ids[i-1] in plan.completed_ids):
                lines.append(f"  🔄 {name}（进行中）")
            else:
                lines.append(f"  ⬜ {name}")

        return "\n".join(lines)

    def get_sidebar_info(self) -> dict:
        """获取侧边栏显示信息"""
        if not self.goal:
            return {}

        plan = self.get_current_day_plan()
        total_nodes = sum(len(dp.node_ids) for dp in self.goal.daily_plans)
        completed_nodes = sum(len(dp.completed_ids) for dp in self.goal.daily_plans)

        return {
            "topic": self.goal.topic,
            "target_days": self.goal.target_days,
            "current_day": self.goal.current_day,
            "total_nodes": total_nodes,
            "completed_nodes": completed_nodes,
            "progress_pct": round(completed_nodes / max(total_nodes, 1) * 100, 1),
            "today_plan": plan.to_dict() if plan else None,
        }

    # ==================== 持久化 ====================

    def to_dict(self) -> dict:
        """序列化为字典"""
        return self.goal.to_dict() if self.goal else {}

    def load_from_dict(self, data: dict):
        """从字典恢复"""
        if data:
            self.goal = LearningGoal.from_dict(data)
