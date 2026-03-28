"""
app.py - 「知道」自适应智能学习助手 主入口

一款基于 AI 对话的自适应学习工具：
- 苏格拉底式追问引导主动思考
- 性格感知自动调整教学策略
- 内循环打分实时追踪认知水平
- 先懂后记的讲解闭环

运行方式：streamlit run app.py
"""

import uuid
import streamlit as st

from utils.config import load_config, validate_config, AppConfig
from core.ai_client import AIClient
from core.learning_session import LearningSession
from database.supabase_client import DatabaseClient
from ui.components.onboarding import render_onboarding, render_config_warning
from ui.components.sidebar import render_sidebar
from ui.components.chat import render_chat_messages, render_chat_input
from ui.components.summary import render_session_summary


# ==================== 页面配置 ====================

st.set_page_config(
    page_title="知道 - 自适应智能学习助手",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==================== 自定义样式 ====================

st.markdown("""
<style>
    /* 全局字体 */
    .stApp {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }

    /* 聊天消息样式优化 */
    .stChatMessage {
        padding: 1rem;
        border-radius: 12px;
        margin-bottom: 0.5rem;
    }

    /* 知识点卡片样式 */
    .stAlert {
        border-radius: 12px;
        border-left: 4px solid #4A90D9;
    }

    /* 进度条样式 */
    .stProgress > div > div {
        border-radius: 10px;
    }

    /* 按钮样式 */
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
    }

    /* 侧边栏 */
    section[data-testid="stSidebar"] {
        background-color: #F8F9FB;
    }

    /* 隐藏 Streamlit 默认菜单 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ==================== 初始化 ====================

def init_session_state():
    """初始化 Streamlit session state"""
    defaults = {
        "user_id": str(uuid.uuid4()),
        "config": None,
        "ai_client": None,
        "db_client": None,
        "learning_session": None,
        "messages_display": [],  # 显示用的消息
        "phase": "onboarding",  # onboarding / learning / summary
        "session_summary": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def init_clients(config: AppConfig) -> bool:
    """初始化 AI 和数据库客户端"""
    # 检查临时配置
    if st.session_state.get("temp_ai_key"):
        config.ai.api_key = st.session_state["temp_ai_key"]
    if st.session_state.get("temp_supabase_url"):
        config.supabase.url = st.session_state["temp_supabase_url"]
    if st.session_state.get("temp_supabase_key"):
        config.supabase.key = st.session_state["temp_supabase_key"]

    # 校验配置
    missing = validate_config(config)
    if missing:
        # 如果只是缺 Supabase，允许无数据库模式运行
        critical_missing = [m for m in missing if "API Key" in m]
        if critical_missing:
            return False

    st.session_state["config"] = config
    st.session_state["ai_client"] = AIClient(config)
    st.session_state["db_client"] = DatabaseClient(config)

    return True


# ==================== 主应用逻辑 ====================

def start_learning(role: str, topic: str, mode: str):
    """启动学习会话"""
    session = LearningSession(
        ai_client=st.session_state["ai_client"],
        db_client=st.session_state["db_client"],
        user_id=st.session_state["user_id"],
        topic=topic,
        mode=mode,
        role=role,
    )

    # 获取开场白
    with st.spinner("🧠 正在准备你的学习之旅..."):
        opening = session.start()

    st.session_state["learning_session"] = session
    st.session_state["messages_display"] = [
        {"role": "assistant", "content": opening}
    ]
    st.session_state["phase"] = "learning"
    st.rerun()


def handle_user_input(user_message: str):
    """处理用户输入"""
    session = st.session_state["learning_session"]
    if not session:
        return

    # 添加用户消息到显示列表
    st.session_state["messages_display"].append(
        {"role": "user", "content": user_message}
    )

    # 处理消息获取回复
    response = session.process_user_message(user_message)

    # 添加 AI 回复到显示列表
    st.session_state["messages_display"].append(
        {"role": "assistant", "content": response}
    )

    st.rerun()


def end_learning():
    """结束学习，生成总结"""
    session = st.session_state["learning_session"]
    if session:
        with st.spinner("📊 正在生成学习总结..."):
            summary = session.generate_session_summary()
        st.session_state["session_summary"] = summary
        st.session_state["phase"] = "summary"
        st.rerun()


def restart_learning():
    """重新开始"""
    keys_to_clear = [
        "learning_session", "messages_display", "phase",
        "session_summary", "selected_role", "topic_input",
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state["phase"] = "onboarding"
    st.rerun()


# ==================== 主函数 ====================

def main():
    """主函数"""
    init_session_state()

    # 加载配置
    config = load_config()
    clients_ready = init_clients(config)

    # 渲染侧边栏
    render_sidebar(st.session_state.get("learning_session"))

    # 侧边栏底部操作
    with st.sidebar:
        if st.session_state["phase"] == "learning":
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📊 结束学习", use_container_width=True):
                    end_learning()
            with col2:
                if st.button("🔄 重新开始", use_container_width=True):
                    restart_learning()

        elif st.session_state["phase"] == "summary":
            st.divider()
            if st.button("🔄 开始新的学习", use_container_width=True):
                restart_learning()

    # ===== 主内容区 =====
    phase = st.session_state["phase"]

    if not clients_ready:
        missing = validate_config(config)
        render_config_warning(missing)
        return

    if phase == "onboarding":
        # 入口引导
        result = render_onboarding()
        if result:
            role, topic, mode = result
            start_learning(role, topic, mode)

    elif phase == "learning":
        # 学习对话
        session = st.session_state.get("learning_session")
        if not session:
            st.error("学习会话未初始化")
            restart_learning()
            return

        # 渲染对话历史
        messages = st.session_state.get("messages_display", [])
        render_chat_messages(messages)

        # 聊天输入
        user_input = st.chat_input("输入你的回答...")
        if user_input:
            handle_user_input(user_input)

    elif phase == "summary":
        # 学习总结
        summary = st.session_state.get("session_summary")
        if summary:
            render_session_summary(summary)
        else:
            st.info("正在生成总结...")

        # 对话历史回顾
        with st.expander("💬 对话回顾", expanded=False):
            messages = st.session_state.get("messages_display", [])
            render_chat_messages(messages)


if __name__ == "__main__":
    main()
