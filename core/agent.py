"""
core/agent.py - 教学 Agent 核心
基于 ReAct（Thought → Action → Observation）推理循环的自主教学 Agent

v3.0 升级：
- 强化出题能力（考试真题风格和难度）
- Mermaid 图表 + LaTeX 公式支持
- 学习计划感知（知识树 + 进度追踪）
- 目标驱动教学
"""

import re
import json
from dataclasses import dataclass, field
from typing import Optional


# ==================== 数据结构 ====================

@dataclass
class ToolCall:
    """工具调用"""
    name: str
    args: dict


@dataclass
class ParsedOutput:
    """Agent 输出解析结果"""
    is_final_response: bool
    final_response: str = ""
    tool_call: Optional[ToolCall] = None
    thought: str = ""
    parse_failed: bool = False


@dataclass
class AgentResult:
    """Agent 一轮执行的完整结果"""
    response: str                        # 最终回复（用户可见）
    scratchpad: list = field(default_factory=list)  # Thought/Action/Observation 轨迹
    iterations: int = 0                  # ReAct 迭代次数
    fallback: bool = False               # 是否降级为直接回复
    reflection: Optional[dict] = None    # 本轮自评结果


# ==================== 输出解析器 ====================

class AgentOutputParser:
    """
    解析 Agent 的文本输出，提取工具调用或最终回复

    Agent 输出格式：
    [Thought] 思考过程...
    [Action] 工具名
    [Action Input] {"参数": "值"}

    或：
    [Thought] 最终思考...
    [Final Response]
    给用户的回复内容
    """

    THOUGHT_PATTERN = re.compile(
        r'\[Thought\]\s*(.*?)(?=\[Action\]|\[Final Response\]|\Z)', re.DOTALL
    )
    ACTION_PATTERN = re.compile(
        r'\[Action\]\s*(\w+)\s*(?:\n\[Action Input\]\s*(.*?))?(?=\[Thought\]|\[Final Response\]|\Z)', re.DOTALL
    )
    FINAL_RESPONSE_PATTERN = re.compile(
        r'\[Final Response\]\s*(.*)', re.DOTALL
    )

    def parse(self, text: str) -> ParsedOutput:
        """解析 Agent 输出文本"""
        text = text.strip()

        # 1. 检查是否有最终回复
        final_match = self.FINAL_RESPONSE_PATTERN.search(text)
        if final_match:
            thought_match = self.THOUGHT_PATTERN.search(text)
            return ParsedOutput(
                is_final_response=True,
                final_response=final_match.group(1).strip(),
                thought=thought_match.group(1).strip() if thought_match else "",
            )

        # 2. 检查是否有工具调用
        action_match = self.ACTION_PATTERN.search(text)
        if action_match:
            tool_name = action_match.group(1).strip()
            tool_args_raw = (action_match.group(2) or "").strip()
            tool_args = self._parse_args(tool_args_raw)
            thought_match = self.THOUGHT_PATTERN.search(text)

            return ParsedOutput(
                is_final_response=False,
                tool_call=ToolCall(name=tool_name, args=tool_args),
                thought=thought_match.group(1).strip() if thought_match else "",
            )

        # 3. 无法解析 → 当作最终回复（降级）
        return ParsedOutput(
            is_final_response=True,
            final_response=text,
            thought="",
            parse_failed=True,
        )

    def _parse_args(self, raw: str) -> dict:
        """解析工具参数，支持 JSON 和 key=value 两种格式"""
        raw = raw.strip()
        if not raw:
            return {}

        # 尝试 JSON
        if raw.startswith('{'):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                # 尝试修复常见问题（单引号）
                try:
                    return json.loads(raw.replace("'", '"'))
                except json.JSONDecodeError:
                    pass

        # 尝试 key=value
        args = {}
        for part in raw.split(','):
            if '=' in part:
                k, v = part.split('=', 1)
                args[k.strip()] = v.strip().strip('"').strip("'")
        return args if args else {"input": raw}


# ==================== 教学 Agent ====================

class TeachingAgent:
    """
    基于 ReAct 的自适应教学 Agent

    v3.0 能力：
    - 考试真题风格出题
    - Mermaid 图表 / LaTeX 公式可视化
    - 知识树感知 + 学习计划驱动
    - 自主决策教学策略
    """

    MAX_ITERATIONS = 3    # 最大 ReAct 迭代次数（控制响应速度）
    REFLECT_INTERVAL = 3  # 每 N 轮做一次自评（减少额外 AI 调用）

    def __init__(self, ai_client, tool_registry, session_context: dict):
        self.ai_client = ai_client
        self.tools = tool_registry
        self.session_context = session_context
        self.parser = AgentOutputParser()
        self.scratchpad: list = []
        self._turn_count = 0

    def run(self, user_message: str, conversation_history: list[dict]) -> AgentResult:
        """
        执行一次 ReAct 推理循环

        Args:
            user_message: 用户消息
            conversation_history: 完整对话历史

        Returns:
            AgentResult
        """
        self._turn_count += 1
        self.scratchpad = []

        # 更新上下文
        self.session_context["user_message"] = user_message

        # 构建消息
        system_prompt = self._build_agent_system_prompt()
        messages = [{"role": "system", "content": system_prompt}]

        # 添加最近的对话历史（控制长度）
        messages.extend(self._prepare_history(conversation_history))

        # 添加当前用户消息 + ReAct 指令
        messages.append({
            "role": "user",
            "content": self._wrap_user_message(user_message),
        })

        # ReAct 循环
        for iteration in range(self.MAX_ITERATIONS):
            response_text = self._call_ai(messages)
            parsed = self.parser.parse(response_text)

            if parsed.is_final_response:
                result = AgentResult(
                    response=parsed.final_response,
                    scratchpad=self.scratchpad,
                    iterations=iteration + 1,
                    fallback=parsed.parse_failed,
                )
                # 定期自评
                if self._turn_count % self.REFLECT_INTERVAL == 0:
                    result.reflection = self._reflect_on_response(
                        user_message, parsed.final_response
                    )
                return result

            if parsed.tool_call:
                # 执行工具
                observation = self._execute_tool(
                    parsed.tool_call.name, parsed.tool_call.args
                )

                # 记录到 scratchpad
                self.scratchpad.append({
                    "thought": parsed.thought,
                    "action": f"{parsed.tool_call.name}({json.dumps(parsed.tool_call.args, ensure_ascii=False)})",
                    "observation": observation[:500],  # 截断避免过长
                })

                # 将 Agent 输出和观察结果追加到消息中
                messages.append({"role": "assistant", "content": response_text})
                messages.append({
                    "role": "user",
                    "content": f"[Observation]\n{observation}\n\n请继续你的思考。如果你已经有足够信息，请直接输出 [Final Response] 给用户。",
                })
            else:
                # 解析失败，直接返回
                return AgentResult(
                    response=response_text,
                    scratchpad=self.scratchpad,
                    iterations=iteration + 1,
                    fallback=True,
                )

        # 达到最大迭代次数，强制生成回复
        return self._force_final_response(messages)

    def _call_ai(self, messages: list[dict]) -> str:
        """调用 AI，带简单重试"""
        for attempt in range(2):
            try:
                result = self.ai_client.chat(messages, temperature=0.7, stream=False)
                if isinstance(result, str) and result:
                    return result
            except Exception:
                if attempt == 0:
                    continue
        return "[Final Response]\n抱歉，我暂时无法回应，请再试一次。"

    def _execute_tool(self, tool_name: str, args: dict) -> str:
        """执行工具，带异常处理"""
        tool = self.tools.get(tool_name)
        if not tool:
            available = ", ".join(self.tools.list_names())
            return f"错误：未知工具 '{tool_name}'。可用工具: {available}"

        try:
            return tool.execute(args, self.session_context)
        except Exception as e:
            return f"工具 '{tool_name}' 执行失败: {str(e)}。请继续推理，可以不依赖此工具的结果。"

    def _force_final_response(self, messages: list[dict]) -> AgentResult:
        """达到最大迭代次数时强制生成回复"""
        messages.append({
            "role": "user",
            "content": "你已经获取了足够的信息。请立刻输出 [Final Response] 给用户一个完整的教学回复。不要再调用任何工具。",
        })
        response_text = self._call_ai(messages)
        parsed = self.parser.parse(response_text)
        final = parsed.final_response if parsed.is_final_response else response_text

        return AgentResult(
            response=final,
            scratchpad=self.scratchpad,
            iterations=self.MAX_ITERATIONS,
            fallback=True,
        )

    # ==================== 提示词构建 ====================

    def _build_agent_system_prompt(self) -> str:
        """构建 Agent 系统提示词"""
        ctx = self.session_context
        tool_prompt = self.tools.get_tools_prompt()
        mode = ctx.get("mode", "academic")
        mode_display = "学科攻克" if mode == "academic" else "领域探索"

        role_map = {"student": "学生", "professional": "职场人", "curious": "好奇宝宝"}
        role_display = role_map.get(ctx.get("role", "student"), "学生")

        # 学习计划上下文
        plan_context = ""
        plan_summary = ctx.get("plan_summary", "")
        if plan_summary:
            plan_context = f"\n\n## 📅 当前学习计划\n{plan_summary}"

        # 知识树上下文
        tree_context = ""
        tree_stats = ctx.get("tree_stats")
        if tree_stats and tree_stats.get("total", 0) > 0:
            tree_context = f"\n\n## 🌳 知识树状态\n已点亮 {tree_stats.get('lit_count', 0)}/{tree_stats.get('total', 0)} 个知识点"
            weak = tree_stats.get("weak", 0)
            if weak > 0:
                tree_context += f"（{weak} 个薄弱）"

        # 模式特定教学规则
        if mode == "academic":
            mode_rules = """### 📌 官方知识点 Highlight（学科模式必须使用）
当你讲完一个知识点的接地气解释后，必须附加：

📌 **官方知识点**
━━━━━━━━━━━━━━━━━━━━━━━━━━━
**【定义】** 标准定义
**【公式】** 公式（如有，使用 LaTeX：$F=ma$）
**【关键词】** 考试必考关键词
**【易错点】** 常见错误
━━━━━━━━━━━━━━━━━━━━━━━━━━━

然后用桥接话术：「所以刚才说的大白话，用物理语言说就是...考试写这个就满分！」"""
        else:
            mode_rules = """### 📎 专业说法提示（探索模式使用）
在关键概念处插入行业术语：
📎 **专业说法**：行业里管这个叫「XXX」
💡 和别人聊的时候用这个词，显得你很懂行 😉"""

        # 记忆提示
        memory_hint = ""
        if "recall_memory" in self.tools.list_names():
            memory_hint = "\n- 会话刚开始时，可以用 recall_memory 回忆该用户之前的学习情况"

        # 知识树工具提示
        tree_hint = ""
        if "manage_knowledge_tree" in self.tools.list_names():
            tree_hint = "\n- 每个知识点学完后，用 manage_knowledge_tree 更新掌握分数"

        # 学习计划工具提示
        plan_hint = ""
        if "manage_learning_plan" in self.tools.list_names():
            plan_hint = "\n- 可以用 manage_learning_plan 查看今日任务和下一个知识点"

        return f"""# 你是「知道」—— 自适应智能学习 Agent

## 你的身份
你是一位经验丰富的自适应学习导师。你通过苏格拉底式追问引导学生主动思考，用最接地气的方式把复杂知识讲明白。你有自主判断力——你决定何时分析用户、何时查教材、何时直接回复。

## 当前会话信息
- 学习主题：{ctx.get('topic', '')}
- 学习模式：{mode_display}
- 用户身份：{role_display}
- 当前对话轮数：{ctx.get('round_count', 0)}{plan_context}{tree_context}

## 你的工作方式（ReAct 推理循环）

你通过「思考 → 行动 → 观察 → ... → 最终回复」的循环来决定如何回应用户。

### 格式规范（必须严格遵守！）

当你需要使用工具时，按此格式输出：
```
[Thought] 你的思考过程
[Action] 工具名称
[Action Input] {{"参数名": "参数值"}}
```

当你准备好给用户最终回复时，按此格式输出：
```
[Thought] 你的最终思考
[Final Response]
你给用户的回复内容
```

### 重要规则
1. 每次只能调用一个工具
2. 工具调用后会收到 [Observation]，然后继续思考
3. [Final Response] 后面的内容用户会直接看到，不要包含 [Thought]、[Action] 等标记
4. 最多调用 5 次工具，之后必须给出最终回复
5. 如果不需要任何工具，可以直接输出 [Final Response]

{tool_prompt}

## 教学核心原则

### 苏格拉底方法（最高优先级）
- **绝不直接给答案**：永远用问题引导学生自己发现答案
- **答对了也不能直接出解释！** 这是最重要的规则：
  - 第一步：追问「为什么？你是怎么想到的？」让学生说出推理过程
  - 第二步：如果学生能说出原理 → 变换条件追问「如果换成XXX，结果还一样吗？」
  - 第三步：学生也能回答 → 才可以给出官方知识点总结，然后进入下一题
  - **至少追问 1-2 次才能进入解释环节，即使学生答对了！**
- 答错时不批评：「没关系，你当时是怎么思考的？」然后从「为什么」开始引导
- 理科类题目（物理/数学/化学/生物）追问尤其重要：
  - 物理：「这个力是怎么产生的？方向为什么是这样？」
  - 数学：「这一步你是根据什么性质变换的？」
  - 化学：「为什么这个反应会发生？本质上是什么在变化？」
  - 生物：「这个机制存在的生物学意义是什么？」

### ⚠️ 禁止行为（违反将导致教学效果大幅下降）
- ❌ 用户答对 → 直接给解释/给知识点卡片 → 出下一题（这是最差的教学模式！）
- ✅ 用户答对 → 追问「为什么」 → 用户解释原理 → 变换条件再问 → 确认理解 → 官方知识点

### 认知断点处理
当用户有认知断点（assess_cognition 返回 has_breakpoint=true）时：
- 从最底层的「为什么」讲起
- ❌ 不说：「牛顿第二定律是 F=ma」
- ✅ 要说：「你有没有想过，为什么推重的东西比轻的更费劲？想象你在超市推购物车...」

### 性格适配（根据 analyze_personality 的结果动态调整）
- 急躁型(patience<0.35)：简短回复，快问快答，少铺垫
- 胆怯型(confidence<0.35)：多鼓励，先出简单题建立信心
- 被动型(initiative<0.35)：系统主导，多出选择题
- 具象思维(thinking_style<0.35)：先例子后原理
- 抽象思维(thinking_style>0.65)：先原理后例子

{mode_rules}

### 🎯 考试真题风格出题（极其重要！）
当需要出题时，必须遵循以下规则：
- 参照历年考试真题的风格和难度，不要出过于简单或童趣的题目
- 题目要有区分度，能测试不同层次的理解
- 选择题的干扰项要有迷惑性（常见错误思路）
- 简答题要考查理解深度而非死记硬背
- 出题格式清晰规范，包含题号、选项标签

### 📊 可视化内容（Mermaid + LaTeX）
在教学中积极使用可视化来帮助理解：

**LaTeX 公式**：数学、物理公式使用 LaTeX 行内语法 $...$
- 例如：$F = ma$，$E = mc^2$，$\\sum_{{i=1}}^n a_i$

**Mermaid 图表**：在讲解概念关系、流程、分类时使用
```mermaid
graph TD
    A[力] --> B[重力]
    A --> C[弹力]
    A --> D[摩擦力]
```

使用时机：
- 知识点之间有层次/分类关系时 → mindmap 或 graph
- 有因果/流程关系时 → flowchart
- 对比关系时 → 表格
- 公式推导时 → LaTeX

### 知识准确性（极其重要）
- 涉及定义、公式时，**必须先调用 search_textbook**
- 如果教材中找不到且你不确定，用 ⚠️ 标注
- 重要知识陈述可用 check_facts 二次校验

## 决策指南（何时使用哪个工具）

你不需要每轮都调用所有工具。根据情况选择：

| 场景 | 建议操作 |
|------|---------|
| 会话前3轮，不了解用户 | 调用 analyze_personality 了解风格 |
| 用户给了实质性回答 | 调用 assess_cognition 评估认知 |
| 用户回复很短/敷衍 | 调用 analyze_personality 确认是否失去耐心 |
| 要讲解新知识点/给定义公式 | 调用 search_textbook |
| 不确定知识陈述准确性 | 调用 check_facts |
| 用户只是确认/说'好''继续' | 不需要工具，直接回复 |
| 不确定该用什么教学风格 | 调用 get_teaching_strategy |
| 一个知识点学完了 | 调用 manage_knowledge_tree 更新分数 |
| 想知道下一步学什么 | 调用 manage_learning_plan |{memory_hint}{tree_hint}{plan_hint}

## 回复风格
- 亲切口语化，像聊天不像上课
- 适当用 emoji（但不要过度）
- 类比生活场景
- 每次回复控制在合理长度内
- 使用 Markdown 格式
- 涉及公式时使用 LaTeX
- 涉及关系/结构时使用 Mermaid 图表
"""

    def _prepare_history(self, conversation_history: list[dict]) -> list[dict]:
        """准备对话历史（排除 system 消息，控制长度）"""
        non_system = [m for m in conversation_history if m["role"] != "system"]

        if len(non_system) <= 10:
            return non_system

        # 太长时只保留最近 10 条
        summary_msg = {
            "role": "system",
            "content": f"[前 {len(non_system) - 10} 轮对话已省略，主题：{self.session_context.get('topic', '')}]",
        }
        return [summary_msg] + non_system[-10:]

    def _wrap_user_message(self, user_message: str) -> str:
        """为用户消息添加 ReAct 提示"""
        round_count = self.session_context.get("round_count", 0)

        hint = ""
        if round_count <= 1:
            hint = "\n\n（提示：这是对话的开头，你可以考虑先用 analyze_personality 了解用户风格）"
        elif round_count <= 3:
            hint = "\n\n（提示：还在对话前期，注意收集用户信息）"

        return f"用户说：{user_message}{hint}\n\n请按 ReAct 格式思考后回复。"

    # ==================== 自评与反思 ====================

    def _reflect_on_response(self, user_message: str, agent_response: str) -> Optional[dict]:
        """
        轻量自评：评估本轮教学效果
        每 N 轮执行一次，结果存入 session_context 供下次参考
        """
        reflection_prompt = [
            {
                "role": "system",
                "content": """你是教学质量评估员。请对以下教学回复进行快速评估。

返回 JSON：
{
  "teaching_effectiveness": 1-5,
  "socratic_quality": 1-5,
  "knowledge_accuracy_risk": "low/medium/high",
  "improvement_hint": "一句话改进建议"
}""",
            },
            {
                "role": "user",
                "content": f"用户说：{user_message[:200]}\n\n助手回复：{agent_response[:500]}\n\n请评估。",
            },
        ]

        try:
            result = self.ai_client.chat_json(reflection_prompt, temperature=0.2)
            if "error" not in result:
                self.session_context["last_reflection"] = result
                return result
        except Exception:
            pass
        return None

    def generate_session_reflection(self, conversation_history: list[dict]) -> dict:
        """
        会话结束时生成结构化反思，用于存入长期记忆

        Returns:
            dict: {weak_points, mastered, preferences, progress_summary, next_suggestion, final_score}
        """
        # 构建对话摘要
        summary_parts = []
        for msg in conversation_history:
            if msg["role"] != "system":
                role = "用户" if msg["role"] == "user" else "助手"
                summary_parts.append(f"{role}：{msg['content'][:200]}")
        conversation_summary = "\n".join(summary_parts[-20:])  # 最多最近20条

        reflection_prompt = [
            {
                "role": "system",
                "content": """你是教学反思专家。根据本次学习对话，生成结构化反思。

返回 JSON：
{
  "weak_points": ["用户的薄弱知识点1", "薄弱知识点2"],
  "mastered": ["已掌握的知识点1", "已掌握的知识点2"],
  "preferences": "该用户的学习偏好描述",
  "progress_summary": "本次学习进度一句话总结",
  "next_suggestion": "下次学习建议从哪里开始",
  "final_score": 0
}""",
            },
            {
                "role": "user",
                "content": f"学习主题：{self.session_context.get('topic', '')}\n\n对话摘要：\n{conversation_summary}",
            },
        ]

        try:
            result = self.ai_client.chat_json(reflection_prompt, temperature=0.3)
            if "error" not in result:
                # 补充实际分数
                score_summary = self.session_context.get("score_summary", {})
                result["final_score"] = score_summary.get("current_score", 0)
                return result
        except Exception:
            pass

        return {
            "weak_points": [],
            "mastered": [],
            "preferences": "",
            "progress_summary": "反思生成失败",
            "next_suggestion": "",
            "final_score": 0,
        }
