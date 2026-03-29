"""
ui/components/sidebar.py - 侧边栏组件
v3.0: 知识树点亮、学习计划进度、存档/读档、切换模式/主题
"""

import streamlit as st
from typing import Optional


def render_sidebar(session=None, config=None):
    """
    渲染侧边栏

    v3.0 新功能:
    - 知识树点亮进度
    - 学习计划进度条
    - 存档/读档按钮
    - 切换主题/模式
    - 知识汇总按钮
    """
    with st.sidebar:
        st.markdown("### 🧠 知道 v3.0")
        st.caption("自适应智能学习助手")

        # ==================== 思考模式切换 ====================
        if session:
            current_mode_label = "🔬 深度思考" if session._use_agent else "⚡ 快速模式"
            toggle = st.toggle(
                f"当前：{current_mode_label}",
                value=session._use_agent,
                help="深度思考（~8s）使用 Agent 自主推理；快速模式（~3s）使用规则流水线",
                key="thinking_mode_toggle",
            )
            if toggle != session._use_agent:
                session._use_agent = toggle
                if toggle and session.agent is None:
                    try:
                        session._init_agent()
                    except Exception:
                        session._use_agent = False
                        st.warning("Agent 初始化失败，已回退到快速模式")

        st.markdown("---")

        if session:
            # ==================== 学习计划进度 ====================
            _render_plan_progress(session)

            # ==================== 知识树点亮 ====================
            _render_knowledge_tree_section(session)

            # ==================== 存档/读档 ====================
            _render_save_load(session)

            # ==================== 切换主题/模式 ====================
            _render_switch_controls(session)

            st.markdown("---")

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
                st.caption(f"AI 提供商：{config.ai.provider}")
                st.caption(f"模型：{config.ai.model}")
            st.caption("知道 v3.0 - 目标驱动学习")


def _render_plan_progress(session):
    """渲染学习计划进度"""
    if session.learning_planner.has_active_plan:
        info = session.learning_planner.get_sidebar_info()
        if info:
            st.markdown(f"### 📅 {info['topic']}")
            st.markdown(f"**Day {info['current_day']}/{info['target_days']}**")

            # 进度条
            pct = info.get("progress_pct", 0)
            st.progress(min(pct / 100, 1.0))
            st.caption(f"完成 {info['completed_nodes']}/{info['total_nodes']} 知识点 ({pct:.0f}%)")

            # 今日任务
            today = info.get("today_plan")
            if today:
                with st.expander("📋 今日任务", expanded=True):
                    for i, name in enumerate(today.get("node_names", [])):
                        nid = today.get("node_ids", [])[i] if i < len(today.get("node_ids", [])) else ""
                        is_done = nid in today.get("completed_ids", [])
                        if is_done:
                            st.markdown(f"  ✅ ~~{name}~~")
                        else:
                            st.markdown(f"  ⬜ {name}")

            st.markdown("---")


def _render_knowledge_tree_section(session):
    """渲染知识树点亮区域"""
    if session.knowledge_tree.nodes:
        stats = session.knowledge_tree.get_stats()
        total = stats["total"]
        lit = stats["lit_count"]

        st.markdown("### 🌳 知识树")
        st.markdown(f"🔥 已点亮 **{lit}/{total}** 知识点")

        # 点亮进度条
        if total > 0:
            st.progress(min(lit / total, 1.0))

        # 查看知识树按钮（列表视图）
        with st.expander("📖 查看知识树"):
            tree_text = session.knowledge_tree.to_summary_text()
            st.markdown(tree_text, unsafe_allow_html=False)

        # 章节徽章
        chapters = session.knowledge_tree.get_chapter_nodes()
        badges = []
        for ch in chapters:
            badge = session.knowledge_tree.get_chapter_badge(ch.id)
            if badge:
                badges.append(f"{badge} {ch.name}")
        if badges:
            st.markdown("**🏅 章节徽章**")
            for b in badges:
                st.markdown(f"  {b}")

        st.markdown("---")
    else:
        # 如果没有知识树，显示生成按钮
        if st.button("🌳 生成知识树", key="gen_tree_btn", use_container_width=True):
            with st.spinner("正在拆解知识树..."):
                success = session.generate_knowledge_tree()
                if success:
                    st.success("知识树已生成！")
                    st.rerun()
                else:
                    st.warning("知识树生成失败，请稍后重试")


def _render_save_load(session):
    """渲染存档/读档控件"""
    col1, col2 = st.columns(2)

    with col1:
        if st.button("💾 存档", key="save_btn", use_container_width=True):
            save_id = session.save_progress()
            st.success(f"已保存！")

    with col2:
        if st.button("📂 读档", key="load_btn", use_container_width=True):
            st.session_state["show_saves"] = True

    # 显示存档列表
    if st.session_state.get("show_saves"):
        saves = session.list_saves()
        if saves:
            st.markdown("**📂 存档列表**")
            for save in saves[:5]:  # 显示最近5个
                col_info, col_load = st.columns([3, 1])
                with col_info:
                    st.caption(save.summary_text())
                with col_load:
                    if st.button("恢复", key=f"load_{save.save_id}", use_container_width=True):
                        success = session.load_progress(save.save_id)
                        if success:
                            st.session_state["show_saves"] = False
                            st.success("已恢复！")
                            st.rerun()
                        else:
                            st.error("恢复失败")
        else:
            st.info("暂无存档")

        if st.button("关闭", key="close_saves"):
            st.session_state["show_saves"] = False
            st.rerun()


def _render_switch_controls(session):
    """渲染切换主题/模式控件"""
    with st.expander("🔄 切换主题/模式"):
        # 切换模式
        new_mode = st.selectbox(
            "学习模式",
            ["学科攻克", "领域探索"],
            index=0 if session.mode == "academic" else 1,
            key="mode_selector",
        )
        mode_map = {"学科攻克": "academic", "领域探索": "explore"}
        if mode_map[new_mode] != session.mode:
            if st.button("确认切换模式", key="switch_mode_btn"):
                session.switch_mode(mode_map[new_mode])
                st.success(f"已切换到 {new_mode} 模式")
                st.rerun()

        # 切换主题
        new_topic = st.text_input(
            "切换学习主题",
            placeholder="输入新的学习主题...",
            key="new_topic_input",
        )
        if new_topic and new_topic != session.topic:
            if st.button("确认切换主题", key="switch_topic_btn"):
                session.switch_topic(new_topic)
                st.success(f"已切换到「{new_topic}」")
                st.rerun()


def _render_cognitive_level(session):
    """渲染认知水平"""
    score_summary = session.scoring_engine.get_score_summary()
    level = score_summary["current_level"]
    score = score_summary["current_score"]
    trend = score_summary.get("trend", "stable")

    trend_icon = {"improving": "📈", "declining": "📉", "stable": "➡️"}.get(trend, "➡️")

    st.markdown("### 📊 认知水平")
    st.markdown(f"**{level}** ({score:.0f}/100) {trend_icon}")
    st.progress(min(score / 100, 1.0))


def _render_kb_status(session):
    """渲染教材知识库状态"""
    kb_stats = session.knowledge_base.get_stats()
    if kb_stats["total_chunks"] > 0:
        st.markdown(f"📚 教材已加载：**{len(kb_stats['files'])}** 个文件 / **{kb_stats['total_chunks']}** 个片段")
    else:
        st.caption("📚 未加载教材（将使用 AI 通用知识）")


def _render_personality(session):
    """渲染性格画像"""
    profile = session.personality_engine.profile
    with st.expander("👤 性格画像"):
        cols = {"耐心": profile.patience, "自信": profile.confidence,
                "主动": profile.initiative, "投入": profile.engagement_level}
        for name, val in cols.items():
            st.markdown(f"**{name}**")
            st.progress(min(val, 1.0))
