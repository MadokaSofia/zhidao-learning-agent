"""
ui/components/chat.py - 对话界面组件
"""

import streamlit as st
from typing import Optional


def render_chat_messages(messages: list[dict]):
    """
    渲染对话消息列表

    Args:
        messages: [{"role": "user/assistant", "content": "..."}]
    """
    for msg in messages:
        if msg["role"] == "system":
            continue

        role = msg["role"]
        content = msg["content"]

        if role == "user":
            with st.chat_message("user", avatar="🧑‍🎓"):
                st.markdown(content)
        elif role == "assistant":
            with st.chat_message("assistant", avatar="🧠"):
                _render_assistant_message(content)


def _render_assistant_message(content: str):
    """
    渲染助手消息，对官方知识点高亮进行特殊处理
    """
    # 分段处理：将知识点卡片用特殊样式展示
    parts = content.split("📌")

    for i, part in enumerate(parts):
        if i == 0:
            # 第一段是普通内容
            if part.strip():
                st.markdown(part)
        else:
            # 知识点卡片部分
            # 找到卡片结束位置
            card_end = part.find("━━━", part.find("━━━") + 1) if "━━━" in part else -1

            if card_end > 0:
                card_content = part[:card_end + 30]
                remaining = part[card_end + 30:]

                # 用 info box 展示知识点卡片
                st.info("📌" + card_content)

                if remaining.strip():
                    st.markdown(remaining)
            else:
                st.info("📌" + part)

    # 处理专业说法提示
    if "📎" in content and "📌" not in content:
        # 如果只有专业说法没有官方知识点
        st.markdown(content)


def render_chat_input(on_submit, disabled: bool = False, placeholder: str = "输入你的回答..."):
    """
    渲染聊天输入框

    Args:
        on_submit: 提交回调函数
        disabled: 是否禁用
        placeholder: 占位文本
    """
    user_input = st.chat_input(placeholder, disabled=disabled)
    if user_input:
        on_submit(user_input)
    return user_input


def render_quick_actions(actions: list[dict]):
    """
    渲染快捷操作按钮

    Args:
        actions: [{"label": "按钮文本", "key": "unique_key"}]
    """
    cols = st.columns(len(actions))
    results = {}
    for col, action in zip(cols, actions):
        with col:
            if st.button(action["label"], key=action["key"], use_container_width=True):
                results[action["key"]] = True
    return results
