"""
app.py - 「知道」自适应智能学习助手 主入口

v3.0 - 目标驱动学习 + 知识树点亮 + 存档/读档
"""

import streamlit as st
from utils.config import load_config
from core.ai_client import AIClient
from core.learning_session import LearningSession
from database.supabase_client import DatabaseClient
from ui.components.onboarding import render_onboarding, render_config_warning
from ui.components.chat import render_chat_messages, render_chat_input
from ui.components.sidebar import render_sidebar
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
    /* 主体字体 */
    .stApp { font-family: "PingFang SC", "Microsoft YaHei", sans-serif; }

    /* 聊天气泡 */
    .stChatMessage { border-radius: 12px; margin: 4px 0; }

    /* 进度条颜色 */
    .stProgress > div > div > div { background-color: #4CAF50; }

    /* 按钮样式 */
    .stButton > button { border-radius: 8px; }

    /* 侧边栏宽度 */
    section[data-testid="stSidebar"] { width: 320px; }

    /* 知识点卡片 */
    .stAlert { border-radius: 8px; }

    /* LaTeX 公式 */
    .katex { font-size: 1.1em; }
</style>
""", unsafe_allow_html=True)


# ==================== 状态初始化 ====================

def init_session_state():
    """初始化 session state"""
    if "phase" not in st.session_state:
        st.session_state.phase = "onboarding"  # onboarding / learning / summary
    if "messages_display" not in st.session_state:
        st.session_state.messages_display = []
    if "user_id" not in st.session_state:
        from utils.helpers import generate_session_id
        st.session_state.user_id = generate_session_id()
    if "show_saves" not in st.session_state:
        st.session_state.show_saves = False


def get_config():
    """获取配置（每次重新加载以支持临时表单输入）"""
    st.session_state.config = load_config()
    return st.session_state.config


# ==================== 核心流程 ====================

def start_learning(role: str, topic: str, mode: str):
    """开始学习"""
    config = get_config()

    # 创建 AI 客户端
    ai_client = AIClient(config)
    db_client = DatabaseClient(config)

    # 获取自定义教材路径
    kb_dir = config.knowledge_base_dir if config.knowledge_base_dir else None

    # 创建学习会话
    session = LearningSession(
        ai_client=ai_client,
        db_client=db_client,
        user_id=st.session_state.user_id,
        topic=topic,
        mode=mode,
        role=role,
        knowledge_base_dir=kb_dir,
    )

    # 获取 AI 开场白
    with st.spinner("🧠 正在准备学习环境..."):
        opening = session.start()

    # 保存到 session state
    st.session_state.session = session
    st.session_state.phase = "learning"
    st.session_state.messages_display = [
        {"role": "assistant", "content": opening}
    ]

    st.rerun()


def handle_user_input(user_input: str):
    """处理用户输入"""
    session: LearningSession = st.session_state.session

    # 添加用户消息到显示列表
    st.session_state.messages_display.append(
        {"role": "user", "content": user_input}
    )

    # 获取 AI 回复
    with st.spinner("🧠 思考中..."):
        response = session.process_user_message(user_input)

    # 添加 AI 回复到显示列表
    st.session_state.messages_display.append(
        {"role": "assistant", "content": response}
    )

    st.rerun()


def end_learning():
    """结束学习"""
    session: LearningSession = st.session_state.session

    with st.spinner("📊 正在生成学习总结..."):
        summary = session.generate_session_summary()

    st.session_state.summary = summary
    st.session_state.phase = "summary"
    st.rerun()


def restart_learning():
    """重新开始"""
    for key in ["session", "summary", "messages_display", "show_saves"]:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state.phase = "onboarding"
    st.session_state.messages_display = []
    st.rerun()


# ==================== 主渲染 ====================

def main():
    init_session_state()
    config = get_config()

    # 检查配置
    from utils.config import validate_config
    missing = validate_config(config)
    if missing:
        render_config_warning(missing)
        return

    # 渲染侧边栏
    session = st.session_state.get("session")
    render_sidebar(session=session, config=config)

    # 主内容区
    phase = st.session_state.phase

    if phase == "onboarding":
        result = render_onboarding()
        if result:
            role, topic, mode = result
            start_learning(role, topic, mode)

    elif phase == "learning":
        if not session:
            restart_learning()
            return

        # 渲染聊天消息
        render_chat_messages(st.session_state.messages_display)

        # 底部操作栏
        col1, col2 = st.columns([6, 1])
        with col2:
            if st.button("📊 结束学习", key="end_btn", use_container_width=True):
                end_learning()

        # 聊天输入
        render_chat_input(handle_user_input)

    elif phase == "summary":
        summary = st.session_state.get("summary", {})
        render_session_summary(summary)

        if st.button("🔄 重新开始", type="primary", use_container_width=True):
            restart_learning()


if __name__ == "__main__":
    main()
