"""
ui/components/sidebar.py - 侧边栏组件
v3.1: ChatGPT 风格对话列表 + 知识树点亮 + 学习计划进度

布局：
┌─────────────────┐
│ 🧠 知道 v3.0    │
│ [+ 新对话]       │
│ ─────────────── │
│ 📖 初中物理  ← 当前 │
│ 📖 高中生物      │
│ 📖 线性代数      │
│ ─────────────── │
│ 🔬/⚡ 思考模式   │
│ 📅 学习计划      │
│ 🌳 知识树        │
│ 📊 认知水平      │
│ ⚙️ 设置          │
└─────────────────┘
"""

import streamlit as st
from typing import Optional


def render_sidebar(session=None, config=None):
    """渲染侧边栏"""
    with st.sidebar:
        st.markdown("### 🧠 知道 v3.0")

        # ==================== 新对话按钮 ====================
        if st.button("➕ 新对话", key="new_chat_btn", use_container_width=True):
            _start_new_chat(session)

        # ==================== 历史对话列表 ====================
        _render_chat_list(session)

        st.markdown("---")

        if session:
            # ==================== 思考模式切换 ====================
            _render_thinking_toggle(session)

            # ==================== 学习模式切换（直接切换，无确认） ====================
            _render_mode_switch(session)

            st.markdown("---")

            # ==================== 学习计划进度 ====================
            _render_plan_progress(session)

            # ==================== 知识树点亮 ====================
            _render_knowledge_tree_section(session)

            # ==================== 认知水平 ====================
            _render_cognitive_level(session)

            # ==================== 教材状态 ====================
            _render_kb_status(session)

            # ==================== 性格画像 ====================
            _render_personality(session)

        st.markdown("---")

        # ==================== 设置 ====================
        with st.expander("⚙️ 设置"):
            if config:
                st.caption(f"AI：{config.ai.provider} / {config.ai.model}")
            st.caption("知道 v3.0 - 目标驱动学习")


# ==================== 对话列表（ChatGPT 风格） ====================

def _start_new_chat(session):
    """开始新对话：先保存当前，再跳转到 onboarding"""
    if session:
        try:
            session.save_progress("自动存档")
        except Exception:
            pass
    # 清除当前会话，回到 onboarding
    for key in ["session", "summary", "messages_display"]:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state.phase = "onboarding"
    st.session_state.messages_display = []
    st.rerun()


def _render_chat_list(session):
    """渲染历史对话列表"""
    # 获取存档列表
    if not session:
        # 没有 session 时，尝试用 SessionStore 直接读取
        from core.session_store import SessionStore
        store = SessionStore()
        user_id = st.session_state.get("user_id", "")
        if user_id:
            saves = store.list_saves(user_id)
        else:
            saves = []
    else:
        saves = session.list_saves()

    if not saves:
        return

    st.caption("📂 历史对话")

    for save in saves[:8]:  # 最多显示8个
        # 当前对话高亮
        is_current = (
            session
            and session.topic == save.topic
            and session.round_count == save.round_count
        )

        # 构建显示文本
        label = f"📖 {save.topic}"
        detail = f"{save.cognitive_level} · {save.round_count}轮 · {save.timestamp}"

        if is_current:
            st.markdown(f"**▸ {label}**")
            st.caption(f"  {detail} (当前)")
        else:
            if st.button(label, key=f"chat_{save.save_id}", use_container_width=True):
                _load_chat(session, save.save_id, save.user_id)
            st.caption(f"  {detail}")


def _load_chat(session, save_id, user_id):
    """加载历史对话"""
    if session:
        success = session.load_progress(save_id)
        if success:
            st.session_state.phase = "learning"
            st.rerun()
    else:
        # 没有 session，需要创建一个然后加载
        from core.session_store import SessionStore
        store = SessionStore()
        save = store.load_session(user_id, save_id)
        if save:
            # 存到 session_state，让 app.py 重新初始化
            st.session_state["pending_load"] = save
            st.session_state.phase = "loading"
            st.rerun()


# ==================== 思考模式 ====================

def _render_thinking_toggle(session):
    """渲染思考模式切换"""
    toggle = st.toggle(
        "🔬 深度思考" if session._use_agent else "⚡ 快速模式",
        value=session._use_agent,
        help="深度思考（Agent 推理）/ 快速模式（规则流水线）",
        key="thinking_mode_toggle",
    )
    if toggle != session._use_agent:
        session._use_agent = toggle
        if toggle and session.agent is None:
            try:
                session._init_agent()
            except Exception:
                session._use_agent = False


# ==================== 模式切换（直接生效） ====================

def _render_mode_switch(session):
    """渲染学习模式切换（直接切换，无确认按钮）"""
    modes = ["学科攻克", "领域探索"]
    mode_map = {"学科攻克": "academic", "领域探索": "explore"}
    current_idx = 0 if session.mode == "academic" else 1

    new_mode = st.radio(
        "学习模式",
        modes,
        index=current_idx,
        horizontal=True,
        key="mode_radio",
        label_visibility="collapsed",
    )

    if mode_map[new_mode] != session.mode:
        session.switch_mode(mode_map[new_mode])
        st.rerun()


# ==================== 学习计划进度 ====================

def _render_plan_progress(session):
    """渲染学习计划进度"""
    if not session.learning_planner.has_active_plan:
        return

    info = session.learning_planner.get_sidebar_info()
    if not info:
        return

    st.markdown(f"### 📅 学习计划")
    st.markdown(f"**{info['topic']}** · Day {info['current_day']}/{info['target_days']}")

    pct = info.get("progress_pct", 0)
    st.progress(min(pct / 100, 1.0))
    st.caption(f"已完成 {info['completed_nodes']}/{info['total_nodes']} ({pct:.0f}%)")

    today = info.get("today_plan")
    if today:
        with st.expander("📋 今日任务", expanded=False):
            for i, name in enumerate(today.get("node_names", [])):
                nid = today.get("node_ids", [])[i] if i < len(today.get("node_ids", [])) else ""
                is_done = nid in today.get("completed_ids", [])
                st.markdown(f"{'✅' if is_done else '⬜'} {name}")

    st.markdown("---")


# ==================== 知识树 ====================

def _render_knowledge_tree_section(session):
    """渲染知识树点亮区域"""
    if session.knowledge_tree.nodes:
        stats = session.knowledge_tree.get_stats()
        total = stats["total"]
        lit = stats["lit_count"]

        st.markdown(f"### 🌳 知识树 · {lit}/{total}")

        if total > 0:
            st.progress(min(lit / total, 1.0))

        with st.expander("📖 查看知识树"):
            tree_text = session.knowledge_tree.to_summary_text()
            st.markdown(tree_text, unsafe_allow_html=False)

        # 章节徽章
        chapters = session.knowledge_tree.get_chapter_nodes()
        badges = [
            f"{session.knowledge_tree.get_chapter_badge(ch.id)} {ch.name}"
            for ch in chapters
            if session.knowledge_tree.get_chapter_badge(ch.id)
        ]
        if badges:
            for b in badges:
                st.caption(b)

        st.markdown("---")
    else:
        if st.button("🌳 生成知识树", key="gen_tree_btn", use_container_width=True):
            with st.spinner("正在拆解知识树..."):
                success = session.generate_knowledge_tree()
                if success:
                    st.success("知识树已生成！")
                    st.rerun()
                else:
                    st.warning("生成失败，请稍后重试")


# ==================== 认知水平 ====================

def _render_cognitive_level(session):
    """渲染认知水平"""
    score_summary = session.scoring_engine.get_score_summary()
    level = score_summary["current_level"]
    score = score_summary["current_score"]
    trend = score_summary.get("trend", "stable")
    trend_icon = {"improving": "📈", "declining": "📉", "stable": "➡️"}.get(trend, "➡️")

    st.markdown(f"### 📊 {level} ({score:.0f}分) {trend_icon}")
    st.progress(min(score / 100, 1.0))


# ==================== 教材状态 ====================

def _render_kb_status(session):
    """渲染教材知识库状态"""
    kb_stats = session.knowledge_base.get_stats()
    if kb_stats["total_chunks"] > 0:
        st.caption(f"📚 教材：{len(kb_stats['files'])} 文件 / {kb_stats['total_chunks']} 片段")
    else:
        st.caption("📚 未加载教材")


# ==================== 性格画像 ====================

def _render_personality(session):
    """渲染性格画像"""
    profile = session.personality_engine.profile
    with st.expander("👤 性格画像"):
        for name, val in [("耐心", profile.patience), ("自信", profile.confidence),
                          ("主动", profile.initiative), ("投入", profile.engagement_level)]:
            st.caption(name)
            st.progress(min(val, 1.0))
