"""
core/learning_session.py - 学习会话管理器
协调所有引擎，管理学习会话的完整生命周期

v2.0 - Agent 架构升级：
- 新增 TeachingAgent + ReAct 循环作为主路径
- 原规则流水线保留为 _process_via_rules() 降级回退
- 通过 _use_agent 开关控制
"""

import json
import time
import streamlit as st
from typing import Optional
from core.ai_client import AIClient
from core.personality_engine import PersonalityEngine
from core.scoring_engine import ScoringEngine
from core.prompt_builder import PromptBuilder
from core.fact_checker import FactChecker
from core.knowledge_base import KnowledgeBase
from core.memory import MemoryManager
from core.agent import TeachingAgent, AgentResult
from core.tools import (
    ToolRegistry,
    AnalyzePersonalityTool,
    AssessCognitionTool,
    SearchTextbookTool,
    CheckFactsTool,
    GetTeachingStrategyTool,
    RecallMemoryTool,
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
        mode: str,  # "academic" or "explore"
        role: str,  # "student" / "professional" / "curious"
        knowledge_base_dir: str = None,  # 自定义教材目录路径
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

        # 新增：记忆管理器
        self.memory_manager = MemoryManager(db_client)

        # 会话状态
        self.session_id: Optional[str] = None
        self.conversation_history: list[dict] = []  # 完整对话历史
        self.knowledge_highlights: list[str] = []  # 本次知识点高亮
        self.fact_check_results: list[dict] = []   # 审查结果
        self.round_count: int = 0
        self.socratic_depth_current: int = 0  # 当前追问深度计数
        self.phase: str = "diagnostic"  # diagnostic / teaching / wrapping_up

        # Agent 模式控制
        self._use_agent = True  # 开关：True=Agent模式，False=规则模式
        self.agent: Optional[TeachingAgent] = None

        # 从数据库加载用户画像（作为初始参考）
        self._load_user_profile()

        # 初始化 Agent
        if self._use_agent:
            try:
                self._init_agent()
            except Exception:
                self._use_agent = False

    def _init_agent(self):
        """初始化 Teaching Agent 和工具注册表"""
        # 创建工具注册表
        registry = ToolRegistry()

        # 注册所有工具
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

        # 构建会话上下文
        session_context = {
            "topic": self.topic,
            "mode": self.mode,
            "role": self.role,
            "user_id": self.user_id,
            "round_count": self.round_count,
            "conversation_history": self.conversation_history,
            "score_summary": self.scoring_engine.get_score_summary(),
        }

        # 创建 Agent
        self.agent = TeachingAgent(self.ai_client, registry, session_context)

    def _load_user_profile(self):
        """从数据库加载用户画像作为初始参考"""
        profile_data = self.db_client.get_user_profile(self.user_id, self.topic)
        if profile_data:
            self.personality_engine.load_from_profile_data(profile_data)
            # 恢复认知水平
            score = profile_data.get("cognitive_score", 30)
            self.scoring_engine.current_score = score
            self.scoring_engine.current_level = calculate_level(score)

    def start(self) -> str:
        """
        启动学习会话

        Returns:
            AI 的开场白
        """
        # 提前加载教材知识库
        self.knowledge_base.load()

        # 创建数据库会话记录
        self.session_id = self.db_client.create_session(
            self.user_id, self.topic, self.mode
        )

        # 构建摸底诊断提示
        diagnostic_prompt = self.prompt_builder.build_diagnostic_prompt(
            self.topic, self.mode, self.role
        )

        # 构建初始系统提示
        teaching_params = self.personality_engine.get_teaching_params()
        score_summary = self.scoring_engine.get_score_summary()

        system_prompt = self.prompt_builder.build_system_prompt(
            self.mode, self.role, self.topic, teaching_params, score_summary
        )

        # === 📖 注入教材知识库 ===
        kb_context = self._get_kb_context(self.topic)
        if kb_context:
            system_prompt += kb_context

        # 组装消息
        self.conversation_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": diagnostic_prompt},
        ]

        # 调用 AI 获取开场白
        response = self.ai_client.chat(self.conversation_history, stream=False)

        # 记录 AI 回复
        self.conversation_history.append({"role": "assistant", "content": response})

        # 记录系统发送时间（供性格引擎使用）
        self.personality_engine.record_message_sent()

        return response

    def process_user_message(self, user_message: str) -> str:
        """
        处理用户消息，返回 AI 回复

        路由逻辑：
        - _use_agent=True → Agent ReAct 循环（自主决策）
        - _use_agent=False → 原规则流水线
        - Agent 出错 → 自动降级到规则模式

        Args:
            user_message: 用户输入

        Returns:
            AI 回复文本
        """
        self.round_count += 1

        if self._use_agent and self.agent:
            try:
                return self._process_via_agent(user_message)
            except Exception as e:
                # Agent 出错，降级到规则模式
                return self._process_via_rules(user_message)

        return self._process_via_rules(user_message)

    # ==================== Agent 路径 ====================

    def _process_via_agent(self, user_message: str) -> str:
        """
        通过 Agent ReAct 循环处理用户消息

        Agent 自主决定调用哪些工具、以什么顺序
        """
        # 更新 Agent 上下文
        self.agent.session_context.update({
            "round_count": self.round_count,
            "conversation_history": self.conversation_history,
            "user_message": user_message,
            "score_summary": self.scoring_engine.get_score_summary(),
        })

        # 运行 Agent
        result: AgentResult = self.agent.run(user_message, self.conversation_history)
        response = result.response

        # === 后处理（与规则模式共享） ===

        # 判断 Agent 是否已经调用了 assess_cognition
        tool_names_used = []
        for step in result.scratchpad:
            action_str = step.get("action", "")
            tool_name = action_str.split("(")[0] if "(" in action_str else action_str
            tool_names_used.append(tool_name)

        # 如果 Agent 调用了 assess_cognition，保存评分日志
        if "assess_cognition" in tool_names_used:
            if self.scoring_engine.history:
                latest = self.scoring_engine.history[-1]
                self.db_client.save_scoring_log(self.session_id, latest.to_dict())

        # 记录发送时间
        self.personality_engine.record_message_sent()

        # 添加到对话历史
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": response})

        # 提取知识点高亮
        self._extract_and_save_highlights(response)

        # 保存用户画像
        self._save_user_profile()

        # 更新会话信息
        self.db_client.update_session(self.session_id, {
            "rounds": self.round_count,
            "end_level": self.scoring_engine.current_level,
        })

        return response

    # ==================== 规则模式（降级回退） ====================

    def _process_via_rules(self, user_message: str) -> str:
        """
        原规则流水线（保留为降级回退路径）

        固定 7 步：行为分析 → 认知评估 → 打分 → 策略 → 教材检索 → AI回复 → 后处理
        """
        # ===== Step 1: 行为分析（性格引擎） =====
        behavior_signal = self.personality_engine.analyze_response(user_message)

        # ===== Step 2: 认知评估（打分引擎） =====
        assessment = self._assess_user_response(user_message)

        # 更新性格引擎的答题正确性
        answered_correctly = assessment.get("answered_correctly", False)
        if self.personality_engine.history:
            self.personality_engine.history[-1].answered_correctly = answered_correctly

        # 更新打分
        score_record = self.scoring_engine.update_from_ai_assessment(assessment)

        # 保存打分日志
        self.db_client.save_scoring_log(self.session_id, score_record.to_dict())

        # 保存认知断点
        if assessment.get("has_breakpoint"):
            self.db_client.save_cognitive_breakpoint(
                self.session_id,
                self.user_id,
                {
                    "breakpoint_description": assessment.get("breakpoint_description", ""),
                    "knowledge_point": self.topic,
                }
            )

        # ===== Step 3: 获取策略参数 =====
        teaching_params = self.personality_engine.get_teaching_params()
        score_summary = self.scoring_engine.get_score_summary()
        strategy_hints = self.scoring_engine.get_strategy_hints()

        # ===== Step 4: 更新系统提示 =====
        updated_system_prompt = self.prompt_builder.build_system_prompt(
            self.mode, self.role, self.topic, teaching_params, score_summary
        )

        # 添加策略提示
        strategy_addon = self._build_strategy_addon(strategy_hints, teaching_params)
        updated_system_prompt += strategy_addon

        # === 📖 根据用户消息检索教材，注入相关片段 ===
        kb_context = self._get_kb_context(user_message)
        if kb_context:
            updated_system_prompt += kb_context

        # 更新对话历史中的系统提示
        if self.conversation_history and self.conversation_history[0]["role"] == "system":
            self.conversation_history[0]["content"] = updated_system_prompt

        # 添加用户消息到历史
        self.conversation_history.append({"role": "user", "content": user_message})

        # ===== Step 5: 生成 AI 回复 =====
        # 控制上下文长度（保留最近的对话，避免 token 溢出）
        messages_to_send = self._prepare_messages()

        response = self.ai_client.chat(messages_to_send, stream=False)

        # 记录 AI 回复
        self.conversation_history.append({"role": "assistant", "content": response})

        # 记录系统发送时间
        self.personality_engine.record_message_sent()

        # ===== Step 6: 后处理 =====
        # 检测并保存知识点高亮
        self._extract_and_save_highlights(response)

        # 更新用户画像到数据库
        self._save_user_profile()

        # 更新会话信息
        self.db_client.update_session(self.session_id, {
            "rounds": self.round_count,
            "end_level": self.scoring_engine.current_level,
        })

        return response

    # ==================== 共享辅助方法 ====================

    def _assess_user_response(self, user_message: str) -> dict:
        """调用 AI 进行内循环打分评估"""
        # 取最近几轮对话作为上下文
        recent_context = ""
        for msg in self.conversation_history[-6:]:
            if msg["role"] != "system":
                role_name = "用户" if msg["role"] == "user" else "助手"
                recent_context += f"{role_name}：{msg['content'][:300]}\n\n"

        assessment_messages = self.prompt_builder.build_assessment_prompt(
            self.topic, recent_context, user_message
        )

        result = self.ai_client.chat_json(assessment_messages, temperature=0.2)

        # 容错处理
        default_assessment = {
            "concept_depth": 30,
            "logic_reasoning": 30,
            "transfer_ability": 20,
            "example_ability": 20,
            "followup_ability": 30,
            "has_breakpoint": False,
            "breakpoint_description": "",
            "answered_correctly": False,
        }

        if "error" in result:
            return default_assessment

        # 合并默认值
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
        """
        从教材知识库检索相关内容

        Args:
            query: 检索查询（主题名或用户消息）

        Returns:
            格式化后的教材参考文本，若无匹配返回空字符串
        """
        try:
            chunks = self.knowledge_base.search(query, topic=self.topic, top_k=3)
            if chunks:
                return self.knowledge_base.format_context(chunks)
        except Exception:
            pass
        return ""

    def _prepare_messages(self) -> list[dict]:
        """
        准备发送给 AI 的消息列表
        控制上下文长度
        """
        if len(self.conversation_history) <= 12:
            return self.conversation_history.copy()

        # 保留系统提示 + 最近 10 轮对话
        messages = [self.conversation_history[0]]  # 系统提示

        # 添加对话摘要（如果历史很长）
        if len(self.conversation_history) > 20:
            summary = f"[前{len(self.conversation_history) - 11}轮对话摘要：用户正在学习「{self.topic}」，当前认知水平 {self.scoring_engine.current_level}]"
            messages.append({"role": "system", "content": summary})

        # 最近的对话
        messages.extend(self.conversation_history[-10:])

        return messages

    def _extract_and_save_highlights(self, response: str):
        """从 AI 回复中提取知识点高亮，并进行二次审查"""
        # 检测是否包含知识点高亮标记
        if "📌" in response or "官方知识点" in response:
            # 简单提取高亮内容
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

                # === 🛡️ 二次审查 ===
                try:
                    review = self.fact_checker.review_highlight(highlight_text, self.topic)
                    self.fact_check_results.append(review)

                    # 在知识点末尾附加审查标记
                    badge = review.get("badge", "")
                    highlight_with_badge = highlight_text + f"\n\n{badge}"

                    # 如果有问题，附加警告
                    if review.get("issues"):
                        issues_text = " | ".join(review["issues"])
                        highlight_with_badge += f"\n⚠️ 审查提示：{issues_text}"
                    if review.get("corrections"):
                        for correction in review["corrections"]:
                            highlight_with_badge += f"\n✏️ 修正建议：{correction}"

                    self.knowledge_highlights.append(highlight_with_badge)
                except Exception:
                    # 审查失败不阻塞主流程
                    self.knowledge_highlights.append(highlight_text + "\n\n⚠️ 未审查")

                self.db_client.save_knowledge_highlight(
                    self.session_id,
                    self.user_id,
                    {
                        "topic": self.topic,
                        "title": self.topic,
                        "definition": highlight_text,
                        "mode": self.mode,
                    }
                )

        # 探索模式的专业说法
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
        """
        生成学习会话总结

        v2.0: 新增 Agent 反思 + 记忆存储

        Returns:
            dict 包含笔记、知识图谱、行动建议等
        """
        # 对话摘要
        conversation_summary = ""
        for msg in self.conversation_history:
            if msg["role"] != "system":
                role = "用户" if msg["role"] == "user" else "助手"
                conversation_summary += f"{role}：{msg['content'][:200]}\n"

        # 生成结构化笔记
        notes_messages = self.prompt_builder.build_notes_prompt(
            self.topic, conversation_summary, self.knowledge_highlights
        )
        notes = self.ai_client.chat(notes_messages, stream=False)

        # 生成知识图谱
        map_messages = self.prompt_builder.build_knowledge_map_prompt(
            self.topic, conversation_summary
        )
        knowledge_map = self.ai_client.chat(map_messages, stream=False)

        # === 新增：Agent 反思 + 存入记忆 ===
        if self._use_agent and self.agent:
            try:
                reflection = self.agent.generate_session_reflection(
                    self.conversation_history
                )
                self.memory_manager.store_session_reflection(
                    self.user_id, self.topic, self.session_id, reflection
                )
            except Exception:
                pass  # 反思失败不阻塞主流程

        # 保存
        self.db_client.save_session_notes(
            self.session_id,
            self.user_id,
            {
                "content": notes,
                "highlights_summary": "\n".join(self.knowledge_highlights),
                "action_items": "",
            }
        )

        # 更新会话结束信息
        self.db_client.update_session(self.session_id, {
            "end_time": get_timestamp(),
            "end_level": self.scoring_engine.current_level,
            "summary": notes[:500] if isinstance(notes, str) else "",
        })

        return {
            "notes": notes,
            "knowledge_map": knowledge_map,
            "highlights": self.knowledge_highlights,
            "score_summary": self.scoring_engine.get_score_summary(),
            "personality": self.personality_engine.profile.describe(),
        }

    def get_display_messages(self) -> list[dict]:
        """获取可显示的对话消息（排除系统消息）"""
        return [
            msg for msg in self.conversation_history
            if msg["role"] != "system"
        ]
