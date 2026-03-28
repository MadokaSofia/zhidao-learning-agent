"""
ui/components/sidebar.py - 侧边栏组件
显示学习状态、性格画像、认知水平等信息
"""

import streamlit as st


def render_sidebar(session=None):
    """渲染侧边栏"""
    with st.sidebar:
        st.markdown("## 🧠 知道")
        st.markdown("*自适应智能学习助手*")
        st.divider()

        if session:
            _render_session_info(session)
        else:
            _render_welcome_info()

        st.divider()
        _render_settings()


def _render_welcome_info():
    """渲染欢迎信息"""
    st.markdown("""
    ### 👋 欢迎使用「知道」

    选择你的身份，输入想学的主题，
    我会通过对话帮你快速掌握新知识。

    **核心特点**：
    - 🤔 苏格拉底追问，引导主动思考
    - 🎭 智能感知你的性格，自动调节节奏
    - 📊 实时追踪认知水平
    - 📌 官方知识点收尾，确保应试能力
    """)


def _render_session_info(session):
    """渲染学习会话信息"""
    # 学习主题
    st.markdown(f"### 📖 {session.topic}")
    st.caption(f"模式：{'学科攻克' if session.mode == 'academic' else '领域探索'}")

    # 认知水平
    score_summary = session.scoring_engine.get_score_summary()
    score = score_summary["current_score"]
    level = score_summary["current_level"]
    trend = score_summary.get("trend", "stable")

    trend_icon = {"improving": "📈", "declining": "📉", "stable": "➡️"}.get(trend, "➡️")

    st.markdown("### 📊 认知水平")
    st.progress(min(score / 100, 1.0))

    col1, col2 = st.columns(2)
    with col1:
        st.metric("等级", level, delta=None)
    with col2:
        st.metric("分数", f"{score:.0f}", delta=None)

    st.caption(f"趋势 {trend_icon}")

    # 性格画像
    personality = session.personality_engine.profile
    if personality.rounds_observed >= 2:
        st.markdown("### 🎭 性格画像")
        st.caption(personality.describe())

        # 用进度条显示各维度
        st.markdown("**耐心**")
        st.progress(personality.patience)
        st.markdown("**自信**")
        st.progress(personality.confidence)
        st.markdown("**主动性**")
        st.progress(personality.initiative)
        st.markdown("**投入度**")
        st.progress(personality.engagement_level)

    # 学习轮数
    st.markdown(f"### 🔄 对话轮数：{session.round_count}")

    # 知识点高亮数
    if session.knowledge_highlights:
        st.markdown(f"### 📌 知识点：{len(session.knowledge_highlights)} 个")


def _render_settings():
    """渲染设置区域"""
    with st.expander("⚙️ 设置", expanded=False):
        st.markdown("**AI 模型**")
        provider = st.selectbox(
            "选择模型",
            ["deepseek", "tongyi", "zhipu"],
            index=0,
            key="ai_provider_select",
            label_visibility="collapsed",
        )

        st.markdown("---")
        st.markdown("**关于「知道」**")
        st.caption(
            "自适应智能学习助手 v1.0\n"
            "苏格拉底追问 × 性格感知 × 认知评估"
        )
