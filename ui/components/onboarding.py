"""
ui/components/onboarding.py - 入口引导组件
身份选择 + 主题输入
"""

import streamlit as st
from typing import Optional, Tuple


def render_onboarding() -> Optional[Tuple[str, str, str]]:
    """
    渲染入口引导界面

    Returns:
        (role, topic, mode) 或 None（用户未完成选择）
    """
    st.markdown(
        """
        <div style="text-align: center; padding: 2rem 0;">
            <h1 style="font-size: 3rem;">🧠 知道</h1>
            <p style="font-size: 1.3rem; color: #666;">自适应智能学习助手</p>
            <p style="color: #999;">苏格拉底追问 × 性格感知 × 认知评估</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # Step 1: 身份选择
    st.markdown("### 👤 你是谁？")
    st.caption("选择身份帮助我更好地适配教学策略")

    col1, col2, col3 = st.columns(3)

    role = None
    with col1:
        if st.button(
            "🎒 我是学生",
            key="role_student",
            use_container_width=True,
            help="针对考试的学科知识，有标准答案和公式",
        ):
            st.session_state["selected_role"] = "student"

    with col2:
        if st.button(
            "💼 我是职场人",
            key="role_professional",
            use_container_width=True,
            help="了解新行业、新领域的底层逻辑",
        ):
            st.session_state["selected_role"] = "professional"

    with col3:
        if st.button(
            "🌟 我是好奇宝宝",
            key="role_curious",
            use_container_width=True,
            help="纯粹对某个话题感兴趣，想深入了解",
        ):
            st.session_state["selected_role"] = "curious"

    role = st.session_state.get("selected_role")

    if role:
        role_display = {
            "student": "🎒 学生",
            "professional": "💼 职场人",
            "curious": "🌟 好奇宝宝",
        }
        st.success(f"已选择：{role_display[role]}")

        # 根据身份自动确定模式
        mode = "academic" if role == "student" else "explore"

        mode_display = "学科攻克模式 📚" if mode == "academic" else "领域探索模式 🌍"
        st.caption(f"将进入 → {mode_display}")

        st.markdown("---")

        # Step 2: 主题输入
        st.markdown("### 📚 你想学什么？")

        # 示例主题
        if role == "student":
            st.caption("例如：初中物理-力学、高中生物-遗传、大学线性代数...")
            examples = ["初中物理-力学", "高中生物-遗传", "初中数学-函数", "高中化学-有机"]
        elif role == "professional":
            st.caption("例如：AI Agent、大健康行业、新能源赛道、产品设计方法论...")
            examples = ["AI Agent", "大健康行业", "新能源赛道", "产品设计方法论"]
        else:
            st.caption("例如：量子力学入门、古希腊哲学、宇宙大爆炸、博弈论...")
            examples = ["量子力学入门", "古希腊哲学", "宇宙大爆炸", "博弈论"]

        # 快捷选择
        st.markdown("**热门主题**")
        example_cols = st.columns(len(examples))
        for col, example in zip(example_cols, examples):
            with col:
                if st.button(example, key=f"example_{example}", use_container_width=True):
                    st.session_state["topic_input"] = example

        # 自定义输入
        topic = st.text_input(
            "输入学习主题",
            value=st.session_state.get("topic_input", ""),
            placeholder="输入你想学的主题...",
            key="topic_field",
        )

        if topic:
            st.markdown("---")

            # 确认开始
            if st.button("🚀 开始学习！", type="primary", use_container_width=True):
                return (role, topic, mode)

    return None


def render_config_warning(missing_items: list[str]):
    """渲染配置缺失警告"""
    st.warning("⚠️ 配置不完整")
    st.markdown("请在 `.streamlit/secrets.toml` 中配置以下内容：")
    for item in missing_items:
        st.markdown(f"- ❌ `{item}`")

    st.markdown("---")
    st.markdown("""
    ### 🔧 快速配置指南

    1. 复制 `.streamlit/secrets.toml.example` 为 `.streamlit/secrets.toml`
    2. 填入你的 API 密钥

    **获取密钥**：
    - [DeepSeek API](https://platform.deepseek.com/) - 注册后获取 API Key
    - [Supabase](https://supabase.com/) - 创建项目后获取 URL 和 Key
    """)

    # 提供直接输入密钥的方式（方便测试）
    st.markdown("---")
    st.markdown("### 🔑 或者直接输入密钥（临时使用）")

    with st.form("config_form"):
        ai_key = st.text_input("AI API Key (DeepSeek)", type="password")
        supabase_url = st.text_input("Supabase URL")
        supabase_key = st.text_input("Supabase Key", type="password")

        submitted = st.form_submit_button("保存配置")
        if submitted and ai_key:
            st.session_state["temp_ai_key"] = ai_key
            st.session_state["temp_supabase_url"] = supabase_url
            st.session_state["temp_supabase_key"] = supabase_key
            st.rerun()
