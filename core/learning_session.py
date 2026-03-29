"""
core/learning_session.py - 学习会话管理器
协调所有引擎，管理学习会话的完整生命周期

v3.0 升级：
- 知识树拆解 + 点亮系统
- 学习计划管理（目标驱动）
- 存档/读档支持
- 异步评分（后台调用）
- Mermaid + LaTeX 可视化
- 中途切换学习模式/主题
"""

import re
import json
import time
import threading
import streamlit as st
from typing import Optional
from core.ai_client import AIClient
from core.personality_engine import PersonalityEngine
from core.scoring_engine import ScoringEngine
from core.prompt_builder import PromptBuilder
from core.fact_checker import FactChecker
from core.knowledge_base import KnowledgeBase
from core.memory import MemoryManager
from core.knowledge_tree import KnowledgeTree
from core.learning_planner import LearningPlanner
from core.session_store import SessionStore
from core.agent import TeachingAgent, AgentResult
from core.tools import (
    ToolRegistry,
    AnalyzePersonalityTool,
    AssessCognitionTool,
    SearchTextbookTool,
    CheckFactsTool,
    GetTeachingStrategyTool,
    RecallMemoryTool,
    ManageKnowledgeTreeTool,
    ManageLearningPlanTool,
)
from database.supabase_client import DatabaseClient
from utils.helpers import calculate_level, get_timestamp


class LearningSession:
    """
    学习会话管理器
    协调 AI 客户端、性格引擎、打分引擎、数据库等模块
    """

    def __init__(
        self,
        ai_client: AIClient,
        db_client: DatabaseClient,
        user_id: str,
        topic: str,
        mode: str,
        role: str,
        knowledge_base_dir: str = None,
    ):
        self.ai_client = ai_client
        self.db_client = db_client
        self.user_id = user_id
        self.topic = topic
        self.mode = mode
        self.role = role

        # 引擎
        self.personality_engine = PersonalityEngine()
        self.scoring_engine = ScoringEngine()
        self.prompt_builder = PromptBuilder()
        self.fact_checker = FactChecker(ai_client)
        self.knowledge_base = KnowledgeBase(kb_dir=knowledge_base_dir) if knowledge_base_dir else KnowledgeBase()

        # 记忆管理器
        self.memory_manager = MemoryManager(db_client)

        # v3.0：知识树 + 学习计划 + 存档
        self.knowledge_tree = KnowledgeTree()
        self.learning_planner = LearningPlanner()
        self.session_store = SessionStore(db_client=db_client)

        # 会话状态
        self.session_id: Optional[str] = None
        self.conversation_history: list[dict] = []
        self.knowledge_highlights: list[str] = []
        self.fact_check_results: list[dict] = []
        self.round_count: int = 0
        self.socratic_depth_current: int = 0
        self.phase: str = "diagnostic"

        # Agent 模式控制
        self._use_agent = True
        self.agent: Optional[TeachingAgent] = None

        # 异步评分
        self._async_scoring_thread: Optional[threading.Thread] = None

        # 从数据库加载用户画像
        self._load_user_profile()

        # 尝试加载已有知识树
        self.knowledge_tree.load(user_id, topic)

        # 初始化 Agent
        if self._use_agent:
            try:
                self._init_agent()
            except Exception:
                self._use_agent = False

    def _init_agent(self):
        """初始化 Teaching Agent 和工具注册表"""
        registry = ToolRegistry()

        registry.register(AnalyzePersonalityTool(self.personality_engine))
        registry.register(AssessCognitionTool(
            self.ai_client, self.scoring_engine,
            self.prompt_builder, self.personality_engine
        ))
        registry.register(SearchTextbookTool(self.knowledge_base))
        registry.register(CheckFactsTool(self.fact_checker))
        registry.register(GetTeachingStrategyTool(
            self.personality_engine, self.scoring_engine
        ))
        registry.register(RecallMemoryTool(self.memory_manager))
        registry.register(ManageKnowledgeTreeTool(self.knowledge_tree))
        registry.register(ManageLearningPlanTool(self.learning_planner))

        session_context = {
            "topic": self.topic,
            "mode": self.mode,
            "role": self.role,
            "user_id": self.user_id,
            "round_count": self.round_count,
            "conversation_history": self.conversation_history,
            "score_summary": self.scoring_engine.get_score_summary(),
            "plan_summary": self.learning_planner.get_plan_summary() if self.learning_planner.has_active_plan else "",
            "tree_stats": self.knowledge_tree.get_stats() if self.knowledge_tree.nodes else None,
        }

        self.agent = TeachingAgent(self.ai_client, registry, session_context)

    def _load_user_profile(self):
        """从数据库加载用户画像作为初始参考"""
        profile_data = self.db_client.get_user_profile(self.user_id, self.topic)
        if profile_data:
            self.personality_engine.load_from_profile_data(profile_data)
            score = profile_data.get("cognitive_score", 30)
            self.scoring_engine.current_score = score
            self.scoring_engine.current_level = calculate_level(score)

    def start(self) -> str:
        """启动学习会话"""
        self.knowledge_base.load()

        self.session_id = self.db_client.create_session(
            self.user_id, self.topic, self.mode
        )

        diagnostic_prompt = self.prompt_builder.build_diagnostic_prompt(
            self.topic, self.mode, self.role
        )

        teaching_params = self.personality_engine.get_teaching_params()
        score_summary = self.scoring_engine.get_score_summary()

        system_prompt = self.prompt_builder.build_system_prompt(
            self.mode, self.role, self.topic, teaching_params, score_summary
        )

        kb_context = self._get_kb_context(self.topic)
        if kb_context:
            system_prompt += kb_context

        self.conversation_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": diagnostic_prompt},
        ]

        response = self.ai_client.chat(self.conversation_history, stream=False)
        self.conversation_history.append({"role": "assistant", "content": response})
        self.personality_engine.record_message_sent()

        return response

    def process_user_message(self, user_message: str) -> str:
        """处理用户消息，返回 AI 回复"""
        self.round_count += 1

        # 检测学习目标设定意图
        self._detect_learning_goal(user_message)

        if self._use_agent and self.agent:
            try:
                return self._process_via_agent(user_message)
            except Exception:
                return self._process_via_rules(user_message)

        return self._process_via_rules(user_message)

    # ==================== 学习目标检测 ====================

    def _detect_learning_goal(self, user_message: str):
        """检测用户是否在设定学习目标"""
        goal_keywords = ["学完", "学习完", "天学", "周学", "天内学", "掌握",
                         "学习计划", "制定计划", "规划学习"]
        time_keywords = ["天", "周", "月"]

        msg_lower = user_message.lower()
        has_goal = any(kw in msg_lower for kw in goal_keywords)
        has_time = any(kw in msg_lower for kw in time_keywords)

        if has_goal and has_time and not self.learning_planner.has_active_plan:
            days = self._parse_days(user_message)
            if days > 0:
                self.learning_planner.create_goal(self.topic, days)

    def _parse_days(self, text: str) -> int:
        """从文本中解析学习天数"""
        day_match = re.search(r'(\d+)\s*天', text)
        if day_match:
            return int(day_match.group(1))

        week_match = re.search(r'(\d+)\s*周', text)
        if week_match:
            return int(week_match.group(1)) * 7

        month_match = re.search(r'(\d+)\s*[个月]', text)
        if month_match:
            return int(month_match.group(1)) * 30

        return 7

    # ==================== Agent 路径 ====================

    def _process_via_agent(self, user_message: str) -> str:
        """通过 Agent ReAct 循环处理用户消息"""
        self.agent.session_context.update({
            "round_count": self.round_count,
            "conversation_history": self.conversation_history,
            "user_message": user_message,
            "score_summary": self.scoring_engine.get_score_summary(),
            "plan_summary": self.learning_planner.get_plan_summary() if self.learning_planner.has_active_plan else "",
            "tree_stats": self.knowledge_tree.get_stats() if self.knowledge_tree.nodes else None,
        })

        result: AgentResult = self.agent.run(user_message, self.conversation_history)
        response = result.response

        # 判断 Agent 是否已经调用了 assess_cognition
        tool_names_used = []
        for step in result.scratchpad:
            action_str = step.get("action", "")
            tool_name = action_str.split("(")[0] if "(" in action_str else action_str
            tool_names_used.append(tool_name)

        if "assess_cognition" in tool_names_used:
            if self.scoring_engine.history:
                latest = self.scoring_engine.history[-1]
                self.db_client.save_scoring_log(self.session_id, latest.to_dict())
        else:
            # 异步后台评分
            self._async_assess(user_message)

        self.personality_engine.record_message_sent()

        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": response})

        self._extract_and_save_highlights(response)
        self._save_user_profile()

        if self.knowledge_tree.nodes:
            self.knowledge_tree.save(self.user_id)

        self.db_client.update_session(self.session_id, {
            "rounds": self.round_count,
            "end_level": self.scoring_engine.current_level,
        })

        return response

    # ==================== 异步评分 ====================

    def _async_assess(self, user_message: str):
        """在后台线程中进行认知评估"""
        def _do_assess():
            try:
                assessment = self._assess_user_response(user_message)
                self.scoring_engine.update_from_ai_assessment(assessment)
                if self.scoring_engine.history:
                    latest = self.scoring_engine.history[-1]
                    self.db_client.save_scoring_log(self.session_id, latest.to_dict())
            except Exception:
                pass

        self._async_scoring_thread = threading.Thread(target=_do_assess, daemon=True)
        self._async_scoring_thread.start()

    # ==================== 知识树生成 ====================

    def generate_knowledge_tree(self) -> bool:
        """通过 AI 生成知识树"""
        try:
            prompt = self.learning_planner.build_tree_generation_prompt(self.topic)
            tree_data = self.ai_client.chat_json(prompt, temperature=0.3)

            if "error" not in tree_data and "chapters" in tree_data:
                self.knowledge_tree.build_from_ai_response(self.topic, tree_data)
                self.knowledge_tree.save(self.user_id)
                self.learning_planner.knowledge_tree = self.knowledge_tree
                return True
        except Exception:
            pass
        return False

    # ==================== 存档/读档 ====================

    def save_progress(self, description: str = "") -> str:
        """保存当前学习进度，返回存档 ID"""
        scoring_data = self.scoring_engine.get_score_summary()
        scoring_data["history"] = [r.to_dict() for r in self.scoring_engine.history]

        personality_data = self.personality_engine.profile.to_dict()

        kt_data = {}
        if self.knowledge_tree.nodes:
            kt_data = {
                "topic": self.knowledge_tree.topic,
                "root_id": self.knowledge_tree.root_id,
                "created_at": self.knowledge_tree.created_at,
                "nodes": {nid: n.to_dict() for nid, n in self.knowledge_tree.nodes.items()},
            }

        planner_data = self.learning_planner.to_dict()

        return self.session_store.save_session(
            user_id=self.user_id,
            topic=self.topic,
            mode=self.mode,
            role=self.role,
            round_count=self.round_count,
            conversation_history=self.conversation_history,
            messages_display=st.session_state.get("messages_display", []),
            knowledge_highlights=self.knowledge_highlights,
            scoring_data=scoring_data,
            personality_data=personality_data,
            knowledge_tree_data=kt_data,
            planner_data=planner_data,
            description=description,
        )

    def load_progress(self, save_id: str) -> bool:
        """从存档恢复学习进度"""
        save = self.session_store.load_session(self.user_id, save_id)
        if not save:
            return False

        self.topic = save.topic
        self.mode = save.mode
        self.role = save.role
        self.round_count = save.round_count
        self.conversation_history = save.conversation_history or []
        self.knowledge_highlights = save.knowledge_highlights or []

        self.scoring_engine.current_score = save.cognitive_score
        self.scoring_engine.current_level = save.cognitive_level

        if save.personality_data:
            self.personality_engine.load_from_profile_data(save.personality_data)

        if save.knowledge_tree_data and save.knowledge_tree_data.get("nodes"):
            from core.knowledge_tree import KnowledgeNode
            self.knowledge_tree.topic = save.knowledge_tree_data.get("topic", self.topic)
            self.knowledge_tree.root_id = save.knowledge_tree_data.get("root_id", "root")
            self.knowledge_tree.created_at = save.knowledge_tree_data.get("created_at", "")
            self.knowledge_tree.nodes = {
                nid: KnowledgeNode.from_dict(ndata)
                for nid, ndata in save.knowledge_tree_data.get("nodes", {}).items()
            }

        if save.planner_data:
            self.learning_planner.load_from_dict(save.planner_data)
            self.learning_planner.knowledge_tree = self.knowledge_tree

        if save.messages_display:
            st.session_state["messages_display"] = save.messages_display

        if self._use_agent:
            try:
                self._init_agent()
            except Exception:
                self._use_agent = False

        return True

    def list_saves(self) -> list:
        """列出用户的所有存档"""
        return self.session_store.list_saves(self.user_id)

    # ==================== 中途切换 ====================

    def switch_topic(self, new_topic: str):
        """中途切换学习主题"""
        self.save_progress(f"自动存档-切换到{new_topic}")
        self.topic = new_topic
        self.round_count = 0
        self.knowledge_highlights = []
        self.phase = "diagnostic"
        self.knowledge_tree = KnowledgeTree()
        self.knowledge_tree.load(self.user_id, new_topic)
        if self._use_agent:
            try:
                self._init_agent()
            except Exception:
                pass

    def switch_mode(self, new_mode: str):
        """中途切换学习模式"""
        self.mode = new_mode
        if self._use_agent:
            try:
                self._init_agent()
            except Exception:
                pass

    # ==================== 规则模式（降级回退） ====================

    def _process_via_rules(self, user_message: str) -> str:
        """快速规则流水线（每3轮做一次AI认知评估）"""
        behavior_signal = self.personality_engine.analyze_response(user_message)

        if self.round_count % 3 == 1 or self.round_count <= 2:
            assessment = self._assess_user_response(user_message)
            answered_correctly = assessment.get("answered_correctly", False)
            if self.personality_engine.history:
                self.personality_engine.history[-1].answered_correctly = answered_correctly
            score_record = self.scoring_engine.update_from_ai_assessment(assessment)
            self.db_client.save_scoring_log(self.session_id, score_record.to_dict())
            if assessment.get("has_breakpoint"):
                self.db_client.save_cognitive_breakpoint(
                    self.session_id, self.user_id,
                    {
                        "breakpoint_description": assessment.get("breakpoint_description", ""),
                        "knowledge_point": self.topic,
                    }
                )

        teaching_params = self.personality_engine.get_teaching_params()
        score_summary = self.scoring_engine.get_score_summary()
        strategy_hints = self.scoring_engine.get_strategy_hints()

        updated_system_prompt = self.prompt_builder.build_system_prompt(
            self.mode, self.role, self.topic, teaching_params, score_summary
        )
        strategy_addon = self._build_strategy_addon(strategy_hints, teaching_params)
        updated_system_prompt += strategy_addon

        kb_context = self._get_kb_context(user_message)
        if kb_context:
            updated_system_prompt += kb_context

        if self.conversation_history and self.conversation_history[0]["role"] == "system":
            self.conversation_history[0]["content"] = updated_system_prompt

        self.conversation_history.append({"role": "user", "content": user_message})

        messages_to_send = self._prepare_messages()
        response = self.ai_client.chat(messages_to_send, stream=False)

        self.conversation_history.append({"role": "assistant", "content": response})
        self.personality_engine.record_message_sent()

        self._extract_and_save_highlights(response)
        self._save_user_profile()

        self.db_client.update_session(self.session_id, {
            "rounds": self.round_count,
            "end_level": self.scoring_engine.current_level,
        })

        return response

    # ==================== 共享辅助方法 ====================

    def _assess_user_response(self, user_message: str) -> dict:
        """调用 AI 进行内循环打分评估"""
        recent_context = ""
        for msg in self.conversation_history[-6:]:
            if msg["role"] != "system":
                role_name = "用户" if msg["role"] == "user" else "助手"
                recent_context += f"{role_name}：{msg['content'][:300]}\n\n"

        assessment_messages = self.prompt_builder.build_assessment_prompt(
            self.topic, recent_context, user_message
        )
        result = self.ai_client.chat_json(assessment_messages, temperature=0.2)

        default_assessment = {
            "concept_depth": 30, "logic_reasoning": 30,
            "transfer_ability": 20, "example_ability": 20,
            "followup_ability": 30, "has_breakpoint": False,
            "breakpoint_description": "", "answered_correctly": False,
        }

        if "error" in result:
            return default_assessment

        for key, default_val in default_assessment.items():
            if key not in result:
                result[key] = default_val

        return result

    def _build_strategy_addon(self, strategy_hints: dict, teaching_params: dict) -> str:
        """构建策略附加提示"""
        addon = "\n\n## 🎯 本轮策略提示\n"
        if strategy_hints.get("should_deepen"):
            addon += "- ⬆️ 用户连续表现好，请加深难度，减少铺垫\n"
        if strategy_hints.get("should_simplify"):
            addon += "- ⬇️ 检测到认知断点，请降低难度，从「为什么」开始讲解\n"
        if strategy_hints.get("should_branch"):
            addon += "- 🔀 用户水平稳定，可以尝试引入新的知识分支\n"
        if teaching_params.get("needs_intervention"):
            addon += "- ⚠️ 用户注意力/耐心严重下降，请考虑切换节奏或优雅收尾\n"
        addon += f"- 当前认知分数：{strategy_hints.get('current_score', 0):.0f}/100\n"
        addon += f"- 当前水平：{strategy_hints.get('current_level', 'L2')}\n"
        return addon

    def _get_kb_context(self, query: str) -> str:
        """从教材知识库检索相关内容"""
        try:
            chunks = self.knowledge_base.search(query, topic=self.topic, top_k=3)
            if chunks:
                return self.knowledge_base.format_context(chunks)
        except Exception:
            pass
        return ""

    def _prepare_messages(self) -> list[dict]:
        """准备发送给 AI 的消息列表"""
        if len(self.conversation_history) <= 12:
            return self.conversation_history.copy()

        messages = [self.conversation_history[0]]
        if len(self.conversation_history) > 20:
            summary = f"[前{len(self.conversation_history) - 11}轮对话摘要：用户正在学习「{self.topic}」，当前认知水平 {self.scoring_engine.current_level}]"
            messages.append({"role": "system", "content": summary})

        messages.extend(self.conversation_history[-10:])
        return messages

    def _extract_and_save_highlights(self, response: str):
        """从 AI 回复中提取知识点高亮"""
        if "📌" in response or "官方知识点" in response:
            lines = response.split("\n")
            highlight_block = []
            in_highlight = False

            for line in lines:
                if "📌" in line or "官方知识点" in line:
                    in_highlight = True
                    highlight_block.append(line)
                elif in_highlight:
                    if "━" in line or line.strip() == "":
                        if highlight_block:
                            highlight_block.append(line)
                        if "━" in line and len(highlight_block) > 2:
                            in_highlight = False
                    else:
                        highlight_block.append(line)

            if highlight_block:
                highlight_text = "\n".join(highlight_block)
                try:
                    review = self.fact_checker.review_highlight(highlight_text, self.topic)
                    self.fact_check_results.append(review)
                    badge = review.get("badge", "")
                    highlight_with_badge = highlight_text + f"\n\n{badge}"
                    if review.get("issues"):
                        issues_text = " | ".join(review["issues"])
                        highlight_with_badge += f"\n⚠️ 审查提示：{issues_text}"
                    if review.get("corrections"):
                        for correction in review["corrections"]:
                            highlight_with_badge += f"\n✏️ 修正建议：{correction}"
                    self.knowledge_highlights.append(highlight_with_badge)
                except Exception:
                    self.knowledge_highlights.append(highlight_text + "\n\n⚠️ 未审查")

                self.db_client.save_knowledge_highlight(
                    self.session_id, self.user_id,
                    {"topic": self.topic, "title": self.topic, "definition": highlight_text, "mode": self.mode}
                )

        if "📎" in response:
            lines = response.split("\n")
            for line in lines:
                if "📎" in line:
                    self.knowledge_highlights.append(line.strip())

    def _save_user_profile(self):
        """保存用户画像到数据库"""
        profile_data = self.personality_engine.profile.to_dict()
        profile_data["cognitive_level"] = self.scoring_engine.current_level
        profile_data["cognitive_score"] = self.scoring_engine.current_score
        self.db_client.upsert_user_profile(self.user_id, self.topic, profile_data)

    def generate_session_summary(self) -> dict:
        """生成学习会话总结"""
        conversation_summary = ""
        for msg in self.conversation_history:
            if msg["role"] != "system":
                role = "用户" if msg["role"] == "user" else "助手"
                conversation_summary += f"{role}：{msg['content'][:200]}\n"

        notes_messages = self.prompt_builder.build_notes_prompt(
            self.topic, conversation_summary, self.knowledge_highlights
        )
        notes = self.ai_client.chat(notes_messages, stream=False)

        map_messages = self.prompt_builder.build_knowledge_map_prompt(
            self.topic, conversation_summary
        )
        knowledge_map = self.ai_client.chat(map_messages, stream=False)

        if self._use_agent and self.agent:
            try:
                reflection = self.agent.generate_session_reflection(self.conversation_history)
                self.memory_manager.store_session_reflection(
                    self.user_id, self.topic, self.session_id, reflection
                )
            except Exception:
                pass

        if self.knowledge_tree.nodes:
            self.knowledge_tree.save(self.user_id)

        self.db_client.save_session_notes(
            self.session_id, self.user_id,
            {"content": notes, "highlights_summary": "\n".join(self.knowledge_highlights), "action_items": ""}
        )

        self.db_client.update_session(self.session_id, {
            "end_time": get_timestamp(),
            "end_level": self.scoring_engine.current_level,
            "summary": notes[:500] if isinstance(notes, str) else "",
        })

        result = {
            "notes": notes,
            "knowledge_map": knowledge_map,
            "highlights": self.knowledge_highlights,
            "score_summary": self.scoring_engine.get_score_summary(),
            "personality": self.personality_engine.profile.describe(),
        }

        if self.knowledge_tree.nodes:
            result["knowledge_tree_summary"] = self.knowledge_tree.to_summary_text()
            result["knowledge_tree_mermaid"] = self.knowledge_tree.to_mermaid()

        return result

    def get_display_messages(self) -> list[dict]:
        """获取可显示的对话消息"""
        return [msg for msg in self.conversation_history if msg["role"] != "system"]
