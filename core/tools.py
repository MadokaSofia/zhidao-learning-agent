"""
core/tools.py - Agent 工具定义
将现有引擎包装为 Agent 可调用的工具，统一接口

v3.0 工具列表：
1. analyze_personality - 分析用户行为信号，更新性格画像
2. assess_cognition    - 五维度认知评估 + 策略建议
3. search_textbook     - 检索教材知识库
4. check_facts         - 知识准确性二次校验
5. get_teaching_strategy - 获取综合教学策略
6. recall_memory       - 回忆用户历史学习记录
7. manage_knowledge_tree - 知识树查询与更新
8. manage_learning_plan  - 学习计划查询与管理
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


# ==================== 工具基础设施 ====================

@dataclass
class ToolDefinition:
    """工具元数据，用于生成 Agent 提示词中的工具说明"""
    name: str
    description: str
    parameters: str
    returns: str
    when_to_use: str


class AgentTool(ABC):
    """Agent 工具基类"""

    @abstractmethod
    def definition(self) -> ToolDefinition:
        """返回工具元数据"""
        pass

    @abstractmethod
    def execute(self, args: dict, context: dict) -> str:
        """
        执行工具，返回观察结果（字符串）

        Args:
            args: 从 Agent 输出中解析的参数
            context: 会话上下文（user_message, topic, conversation_history 等）

        Returns:
            字符串形式的观察结果
        """
        pass


class ToolRegistry:
    """工具注册表，管理所有可用工具"""

    def __init__(self):
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool):
        """注册一个工具"""
        defn = tool.definition()
        self._tools[defn.name] = tool

    def get(self, name: str) -> Optional[AgentTool]:
        """获取指定工具"""
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())

    def get_tools_prompt(self) -> str:
        """生成提示词中的工具说明部分"""
        lines = ["## 可用工具\n"]
        for name, tool in self._tools.items():
            defn = tool.definition()
            lines.append(f"### {defn.name}")
            lines.append(f"- **功能**: {defn.description}")
            lines.append(f"- **参数**: {defn.parameters}")
            lines.append(f"- **返回**: {defn.returns}")
            lines.append(f"- **使用时机**: {defn.when_to_use}")
            lines.append("")
        return "\n".join(lines)


# ==================== 具体工具实现 ====================

class AnalyzePersonalityTool(AgentTool):
    """工具1: 分析用户行为信号，更新性格画像"""

    def __init__(self, personality_engine):
        self.engine = personality_engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="analyze_personality",
            description="分析用户本轮回复的行为信号（回复长度、耐心、自信等），更新性格画像，返回教学策略参数",
            parameters='{"user_message": "用户的回复文本"}',
            returns="JSON: 行为信号 + 性格维度 (patience/confidence/initiative/thinking_style) + 教学参数",
            when_to_use="每轮对话开始时调用，了解用户当前状态。用户回复很短或情绪有变化时尤其重要。如果用户只是简单确认（如'好的'、'继续'），也可以跳过。",
        )

    def execute(self, args: dict, context: dict) -> str:
        user_message = args.get("user_message", context.get("user_message", ""))
        signal = self.engine.analyze_response(user_message)
        params = self.engine.get_teaching_params()

        return json.dumps({
            "behavior_signal": {
                "response_length": signal.response_length,
                "has_question": signal.has_question,
                "has_uncertainty": signal.has_uncertainty,
                "is_perfunctory": signal.is_perfunctory,
                "has_example": signal.has_example,
                "has_summary": signal.has_summary,
            },
            "personality_profile": {
                "patience": round(self.engine.profile.patience, 2),
                "confidence": round(self.engine.profile.confidence, 2),
                "initiative": round(self.engine.profile.initiative, 2),
                "thinking_style": round(self.engine.profile.thinking_style, 2),
                "engagement": round(self.engine.profile.engagement_level, 2),
                "frustration": round(self.engine.profile.frustration_level, 2),
            },
            "teaching_params": params,
        }, ensure_ascii=False, indent=2)


class AssessCognitionTool(AgentTool):
    """工具2: AI 驱动的五维度认知评估"""

    def __init__(self, ai_client, scoring_engine, prompt_builder, personality_engine):
        self.ai_client = ai_client
        self.scoring_engine = scoring_engine
        self.prompt_builder = prompt_builder
        self.personality_engine = personality_engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="assess_cognition",
            description="调用 AI 对用户回复进行五维度认知评估（概念理解/逻辑推理/迁移能力/举例能力/追问承接），更新认知分数和等级",
            parameters='{"user_message": "用户的回复"}',
            returns="JSON: 五维度分数 + 总分 + 认知水平(L1-L5) + 是否有断点 + 策略建议",
            when_to_use="当用户给出了实质性回答（非寒暄/敷衍）时调用，用于追踪认知进步。用户只说'嗯'/'好的'时不需要调用。",
        )

    def execute(self, args: dict, context: dict) -> str:
        user_message = args.get("user_message", context.get("user_message", ""))

        # 构建上下文
        recent_context = ""
        history = context.get("conversation_history", [])
        for msg in history[-6:]:
            if msg["role"] != "system":
                role_name = "用户" if msg["role"] == "user" else "助手"
                recent_context += f"{role_name}：{msg['content'][:300]}\n\n"

        # 调用 AI 评估
        topic = context.get("topic", "")
        assessment_messages = self.prompt_builder.build_assessment_prompt(
            topic, recent_context, user_message
        )
        assessment = self.ai_client.chat_json(assessment_messages, temperature=0.2)

        # 容错
        if "error" in assessment:
            assessment = {
                "concept_depth": 30, "logic_reasoning": 30,
                "transfer_ability": 20, "example_ability": 20,
                "followup_ability": 30, "has_breakpoint": False,
                "breakpoint_description": "", "answered_correctly": False,
            }

        # 更新打分引擎
        score_record = self.scoring_engine.update_from_ai_assessment(assessment)

        # 更新性格引擎的答题正确性
        answered = assessment.get("answered_correctly", False)
        if self.personality_engine.history:
            self.personality_engine.history[-1].answered_correctly = answered

        # 获取策略
        strategy = self.scoring_engine.get_strategy_hints()
        summary = self.scoring_engine.get_score_summary()

        return json.dumps({
            "assessment": assessment,
            "score_summary": summary,
            "strategy_hints": strategy,
        }, ensure_ascii=False, indent=2)


class SearchTextbookTool(AgentTool):
    """工具3: 教材知识库检索"""

    def __init__(self, knowledge_base):
        self.kb = knowledge_base

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_textbook",
            description="在预置教材知识库中检索与查询最相关的教材片段（最多3段），确保教学内容基于权威教材",
            parameters='{"query": "检索关键词或问题"}',
            returns="教材相关片段文本（包含来源、章节标题），若无匹配返回提示",
            when_to_use="当需要讲解具体知识点、给出定义/公式时必须调用。当你不确定某个知识点时务必先检索。闲聊或追问环节不需要。",
        )

    def execute(self, args: dict, context: dict) -> str:
        query = args.get("query", context.get("user_message", ""))
        topic = context.get("topic", "")

        try:
            chunks = self.kb.search(query, topic=topic, top_k=3)
        except Exception:
            chunks = []

        if not chunks:
            return "未找到相关教材内容。请基于你的知识教学，但注意标注不确定的内容。"

        result = ""
        for i, chunk in enumerate(chunks, 1):
            source = f"{chunk.source} > {chunk.section_title}" if chunk.section_title else chunk.source
            result += f"【教材片段 {i}】（来源：{source}）\n{chunk.content}\n\n"
        return result


class CheckFactsTool(AgentTool):
    """工具4: 知识准确性二次校验"""

    def __init__(self, fact_checker):
        self.checker = fact_checker

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="check_facts",
            description="对一段知识陈述进行二次准确性校验，判断是否有错误",
            parameters='{"statement": "要校验的知识陈述", "topic": "所属主题"}',
            returns='JSON: {"accurate": bool, "note": "简短说明"}',
            when_to_use="当你准备给出重要的定义、公式或事实性陈述时，先调用此工具校验。仅对关键知识点使用，不要每句话都校验。",
        )

    def execute(self, args: dict, context: dict) -> str:
        statement = args.get("statement", "")
        topic = args.get("topic", context.get("topic", ""))

        if not statement:
            return json.dumps({"accurate": True, "note": "未提供待校验内容"}, ensure_ascii=False)

        try:
            result = self.checker.review_statement(statement, topic)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"accurate": True, "note": f"校验服务暂不可用: {e}"}, ensure_ascii=False)


class GetTeachingStrategyTool(AgentTool):
    """工具5: 综合教学策略获取"""

    def __init__(self, personality_engine, scoring_engine):
        self.personality = personality_engine
        self.scoring = scoring_engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_teaching_strategy",
            description="综合性格画像和认知水平，获取当前教学策略建议（追问深度、讲解长度、鼓励程度等）",
            parameters="无需参数",
            returns="JSON: 完整教学策略参数 + 认知摘要 + 策略建议",
            when_to_use="当你不确定该用什么教学风格时调用。如果你已经调用了 analyze_personality，其返回值中已包含 teaching_params，就不需要再调用此工具。",
        )

    def execute(self, args: dict, context: dict) -> str:
        params = self.personality.get_teaching_params()
        score = self.scoring.get_score_summary()
        hints = self.scoring.get_strategy_hints()

        return json.dumps({
            "teaching_params": params,
            "score_summary": score,
            "strategy_hints": hints,
        }, ensure_ascii=False, indent=2)


class RecallMemoryTool(AgentTool):
    """工具6: 跨会话记忆检索"""

    def __init__(self, memory_manager):
        self.memory = memory_manager

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="recall_memory",
            description="回忆该用户在之前学习会话中的关键信息：薄弱知识点、已掌握内容、学习偏好、上次进度",
            parameters='{"category": "breakpoints/highlights/preferences/progress/all（可选，默认all）"}',
            returns="用户的历史学习记忆摘要",
            when_to_use="会话开始时调用（了解用户历史），或当用户提到之前学过某内容时调用。不需要每轮都调用。",
        )

    def execute(self, args: dict, context: dict) -> str:
        user_id = context.get("user_id", "")
        topic = context.get("topic", "")
        category = args.get("category", "all")

        try:
            return self.memory.recall(user_id, topic, category=category)
        except Exception:
            return "记忆系统暂不可用，按新用户处理。"


class ManageKnowledgeTreeTool(AgentTool):
    """工具7: 知识树查询与更新"""

    def __init__(self, knowledge_tree):
        self.tree = knowledge_tree

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="manage_knowledge_tree",
            description="查询知识树状态、更新知识点掌握分数、获取统计信息。支持操作：query（查看知识树）、update（更新分数）、stats（获取统计）",
            parameters='{"action": "query/update/stats", "node_name": "知识点名称（update时需要）", "score": 分数（update时需要，0-100）}',
            returns="知识树信息或更新结果",
            when_to_use="当需要查看用户知识掌握情况、更新知识点分数、或生成知识树可视化时调用。每次用户完成一个知识点的学习后应该更新分数。",
        )

    def execute(self, args: dict, context: dict) -> str:
        action = args.get("action", "stats")

        if action == "query":
            if not self.tree.nodes:
                return "知识树尚未生成。"
            return self.tree.to_summary_text()

        elif action == "update":
            node_name = args.get("node_name", "")
            score = float(args.get("score", 0))
            if not node_name:
                return "错误：需要提供 node_name 参数。"

            node = self.tree.find_node_by_name(node_name)
            if node:
                self.tree.update_node_score(node.id, score)
                return f"已更新「{node.name}」的掌握分数为 {score:.0f}%，状态：{self.tree._status_label(node.status)}"
            return f"未找到名为「{node_name}」的知识点。"

        elif action == "stats":
            if not self.tree.nodes:
                return "知识树尚未生成。"
            stats = self.tree.get_stats()
            return json.dumps(stats, ensure_ascii=False, indent=2)

        return f"未知操作：{action}"


class ManageLearningPlanTool(AgentTool):
    """工具8: 学习计划查询与管理"""

    def __init__(self, learning_planner):
        self.planner = learning_planner

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="manage_learning_plan",
            description="查询学习计划状态、获取今日任务、完成知识点、推进天数。支持操作：query（查看计划）、today（今日任务）、complete（完成知识点）、next（下一个知识点）",
            parameters='{"action": "query/today/complete/next", "node_id": "知识点ID（complete时需要）", "score": 分数（complete时需要）}',
            returns="学习计划信息",
            when_to_use="当需要了解当前学习进度、获取下一步该学什么、或标记知识点为已完成时调用。",
        )

    def execute(self, args: dict, context: dict) -> str:
        action = args.get("action", "query")

        if action == "query":
            return self.planner.get_plan_summary()

        elif action == "today":
            plan = self.planner.get_current_day_plan()
            if not plan:
                return "当前没有学习计划或今日计划已完成。"
            return json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)

        elif action == "complete":
            node_id = args.get("node_id", "")
            score = float(args.get("score", 70))
            if not node_id:
                return "错误：需要提供 node_id 参数。"
            adjust_msg = self.planner.complete_node(node_id, score)
            result = f"已完成知识点 {node_id}，得分 {score:.0f}%。"
            if adjust_msg:
                result += f"\n{adjust_msg}"
            return result

        elif action == "next":
            next_id = self.planner.get_next_node_to_learn()
            if next_id:
                tree = self.planner.knowledge_tree
                if tree:
                    node = tree.nodes.get(next_id)
                    if node:
                        return f"下一个学习：「{node.name}」（ID: {next_id}）"
                return f"下一个学习：{next_id}"
            return "今日任务已全部完成！"

        return f"未知操作：{action}"
