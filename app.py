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
        # 优先从 URL 参数恢复 user_id，保证刷新后不丢失
        params = st.query_params
        uid_from_url = params.get("uid", "")
        if uid_from_url:
            st.session_state.user_id = uid_from_url
        else:
            from utils.helpers import generate_session_id
            new_uid = generate_session_id()
            st.session_state.user_id = new_uid
            st.query_params["uid"] = new_uid
    else:
        # 确保 URL 参数始终和 session_state 同步
        current_uid = st.session_state.user_id
        if st.query_params.get("uid", "") != current_uid:
            st.query_params["uid"] = current_uid
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

    # 自动存档，防止刷新丢失
    _autosave(session)

    st.rerun()


def handle_user_input(user_input: str):
    """处理用户输入"""
    session: LearningSession = st.session_state.session

    # 检测用户是否请求知识点总结
    summary_keywords = ["/总结", "总结一下", "知识总结", "知识点总结", "帮我总结", "学习总结"]
    user_input_lower = user_input.strip().lower()
    is_summary_request = any(keyword in user_input_lower for keyword in summary_keywords)

    if is_summary_request:
        # 添加用户消息到显示列表
        st.session_state.messages_display.append(
            {"role": "user", "content": user_input}
        )

        # 生成阶段性知识点总结
        with st.spinner("📚 正在生成知识点总结..."):
            try:
                summary = session.generate_summary()

                # 构建总结回复
                response_parts = ["## 📚 阶段性知识点总结\n"]

                if summary.get("notes"):
                    response_parts.append(f"### 📝 学习笔记\n{summary['notes']}\n")

                if summary.get("highlights"):
                    response_parts.append("### 📌 关键知识点\n")
                    for highlight in summary["highlights"]:
                        response_parts.append(f"- {highlight}")
                    response_parts.append("")

                if summary.get("score_summary"):
                    score = summary["score_summary"]
                    response_parts.append(f"### 📊 认知评估\n")
                    response_parts.append(f"- 当前水平：**{score.get('current_level', '未知')}**")
                    response_parts.append(f"- 认知分数：**{score.get('current_score', 0):.0f}/100**\n")

                response_parts.append("---")
                response_parts.append("💡 **提示**：总结已完成，你可以继续学习，或输入新的问题深入探讨！")

                response = "\n".join(response_parts)

            except Exception as e:
                response = f"生成总结时出错：{str(e)}。请继续学习后再试。"

        # 添加 AI 回复到显示列表
        st.session_state.messages_display.append(
            {"role": "assistant", "content": response}
        )

        # 自动存档
        _autosave(session)
        st.rerun()
        return

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

    # 每轮对话后自动存档，防止刷新丢失
    _autosave(session)

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
    # 清除自动存档
    _clear_autosave()
    for key in ["session", "summary", "messages_display", "show_saves",
                "selected_role", "topic_input", "topic_field"]:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state.phase = "onboarding"
    st.session_state.messages_display = []
    st.rerun()


# ==================== 自动存档（防刷新丢失） ====================

def _autosave(session):
    """自动存档当前对话到 Supabase（覆盖写，使用固定 save_id）"""
    try:
        from core.session_store import SessionStore
        scoring_data = session.scoring_engine.get_score_summary()
        scoring_data["history"] = [r.to_dict() for r in session.scoring_engine.history]
        personality_data = session.personality_engine.profile.to_dict()

        kt_data = {}
        if session.knowledge_tree.nodes:
            kt_data = {
                "topic": session.knowledge_tree.topic,
                "root_id": session.knowledge_tree.root_id,
                "created_at": session.knowledge_tree.created_at,
                "nodes": {nid: n.to_dict() for nid, n in session.knowledge_tree.nodes.items()},
            }

        session.session_store.save_session(
            user_id=session.user_id,
            topic=session.topic,
            mode=session.mode,
            role=session.role,
            round_count=session.round_count,
            conversation_history=session.conversation_history,
            messages_display=st.session_state.get("messages_display", []),
            knowledge_highlights=session.knowledge_highlights,
            scoring_data=scoring_data,
            personality_data=personality_data,
            knowledge_tree_data=kt_data,
            planner_data=session.learning_planner.to_dict(),
            description="自动存档",
            save_id=SessionStore.AUTOSAVE_ID,
        )
    except Exception:
        pass


def _try_restore_autosave(config):
    """刷新页面时尝试从自动存档恢复当前对话"""
    user_id = st.session_state.get("user_id", "")
    if not user_id:
        return False

    try:
        from core.session_store import SessionStore
        db_client = DatabaseClient(config)
        store = SessionStore(db_client=db_client)
        save = store.load_session(user_id, SessionStore.AUTOSAVE_ID)

        if not save or not save.messages_display:
            return False

        # 用存档数据创建新的 LearningSession
        ai_client = AIClient(config)
        kb_dir = config.knowledge_base_dir if config.knowledge_base_dir else None

        session = LearningSession(
            ai_client=ai_client,
            db_client=db_client,
            user_id=user_id,
            topic=save.topic,
            mode=save.mode,
            role=save.role,
            knowledge_base_dir=kb_dir,
        )

        # 恢复状态
        session.round_count = save.round_count
        session.conversation_history = save.conversation_history or []
        session.knowledge_highlights = save.knowledge_highlights or []
        session.scoring_engine.current_score = save.cognitive_score
        session.scoring_engine.current_level = save.cognitive_level

        if save.personality_data:
            session.personality_engine.load_from_profile_data(save.personality_data)

        if save.knowledge_tree_data and save.knowledge_tree_data.get("nodes"):
            from core.knowledge_tree import KnowledgeNode
            session.knowledge_tree.topic = save.knowledge_tree_data.get("topic", save.topic)
            session.knowledge_tree.root_id = save.knowledge_tree_data.get("root_id", "root")
            session.knowledge_tree.created_at = save.knowledge_tree_data.get("created_at", "")
            session.knowledge_tree.nodes = {
                nid: KnowledgeNode.from_dict(ndata)
                for nid, ndata in save.knowledge_tree_data.get("nodes", {}).items()
            }

        if save.planner_data:
            session.learning_planner.load_from_dict(save.planner_data)
            session.learning_planner.knowledge_tree = session.knowledge_tree

        # 重新初始化 Agent
        if session._use_agent:
            try:
                session._init_agent()
            except Exception:
                session._use_agent = False

        # 恢复到 session state
        st.session_state.session = session
        st.session_state.phase = "learning"
        st.session_state.messages_display = save.messages_display
        return True

    except Exception:
        return False


def _clear_autosave():
    """清除自动存档（新对话/重新开始时调用）"""
    try:
        from core.session_store import SessionStore
        user_id = st.session_state.get("user_id", "")
        if user_id:
            config = get_config()
            db_client = DatabaseClient(config)
            store = SessionStore(db_client=db_client)
            store.delete_save(user_id, SessionStore.AUTOSAVE_ID)
    except Exception:
        pass


def _handle_loading_phase(config):
    """处理从存档加载对话的流程"""
    save_id = st.session_state.pop("pending_load_save_id", None)
    user_id = st.session_state.pop("pending_load_user_id", None)

    if not save_id or not user_id:
        st.session_state.phase = "onboarding"
        st.rerun()
        return

    with st.spinner("📂 正在加载存档..."):
        from core.session_store import SessionStore
        db_client = DatabaseClient(config)
        store = SessionStore(db_client=db_client)
        save = store.load_session(user_id, save_id)

        if not save:
            st.error("⚠️ 存档加载失败")
            st.session_state.phase = "onboarding"
            st.rerun()
            return

        # 用存档数据创建新的 LearningSession
        ai_client = AIClient(config)
        db_client = DatabaseClient(config)
        kb_dir = config.knowledge_base_dir if config.knowledge_base_dir else None

        session = LearningSession(
            ai_client=ai_client,
            db_client=db_client,
            user_id=user_id,
            topic=save.topic,
            mode=save.mode,
            role=save.role,
            knowledge_base_dir=kb_dir,
        )

        # 恢复状态
        session.round_count = save.round_count
        session.conversation_history = save.conversation_history or []
        session.knowledge_highlights = save.knowledge_highlights or []
        session.scoring_engine.current_score = save.cognitive_score
        session.scoring_engine.current_level = save.cognitive_level

        if save.personality_data:
            session.personality_engine.load_from_profile_data(save.personality_data)

        if save.knowledge_tree_data and save.knowledge_tree_data.get("nodes"):
            from core.knowledge_tree import KnowledgeNode
            session.knowledge_tree.topic = save.knowledge_tree_data.get("topic", save.topic)
            session.knowledge_tree.root_id = save.knowledge_tree_data.get("root_id", "root")
            session.knowledge_tree.created_at = save.knowledge_tree_data.get("created_at", "")
            session.knowledge_tree.nodes = {
                nid: KnowledgeNode.from_dict(ndata)
                for nid, ndata in save.knowledge_tree_data.get("nodes", {}).items()
            }

        if save.planner_data:
            session.learning_planner.load_from_dict(save.planner_data)
            session.learning_planner.knowledge_tree = session.knowledge_tree

        # 重新初始化 Agent
        if session._use_agent:
            try:
                session._init_agent()
            except Exception:
                session._use_agent = False

        # 保存到 session state
        st.session_state.session = session
        st.session_state.phase = "learning"
        if save.messages_display:
            st.session_state.messages_display = save.messages_display

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
        # 刷新后尝试从自动存档恢复（session 不存在说明是刷新）
        if not session and _try_restore_autosave(config):
            st.rerun()
            return
        result = render_onboarding()
        if result:
            role, topic, mode = result
            start_learning(role, topic, mode)

    elif phase == "loading":
        # 从存档加载对话（由侧边栏 _load_chat 触发）
        _handle_loading_phase(config)

    elif phase == "learning":
        if not session:
            # 刷新后 session 丢失，尝试从自动存档恢复
            if _try_restore_autosave(config):
                st.rerun()
                return
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
