"""
ui/components/summary.py - 学习总结组件
展示知识图谱、笔记、知识点合集、知识树等
"""

import streamlit as st


def render_session_summary(summary: dict):
    """
    渲染学习会话总结

    v3.0: 新增知识树可视化和 Mermaid 图表展示

    Args:
        summary: {
            "notes": str,
            "knowledge_map": str,
            "highlights": list[str],
            "score_summary": dict,
            "personality": str,
            "knowledge_tree_summary": str (可选),
            "knowledge_tree_mermaid": str (可选),
        }
    """
    st.markdown("---")
    st.markdown("## 📊 本次学习总结")

    # 根据是否有知识树决定 Tab 数量
    has_tree = bool(summary.get("knowledge_tree_summary"))

    if has_tree:
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📝 学习笔记",
            "🌳 知识树",
            "🗺️ 知识图谱",
            "📌 知识点合集",
            "📈 学习数据",
        ])
    else:
        tab1, tab2, tab3, tab4 = st.tabs([
            "📝 学习笔记",
            "🗺️ 知识图谱",
            "📌 知识点合集",
            "📈 学习数据",
        ])

    with tab1:
        _render_notes(summary.get("notes", "暂无笔记"))

    if has_tree:
        with tab2:
            _render_knowledge_tree(
                summary.get("knowledge_tree_summary", ""),
                summary.get("knowledge_tree_mermaid", ""),
            )
        with tab3:
            _render_knowledge_map(summary.get("knowledge_map", ""))
        with tab4:
            _render_highlights(summary.get("highlights", []))
        with tab5:
            _render_learning_data(
                summary.get("score_summary", {}),
                summary.get("personality", ""),
            )
    else:
        with tab2:
            _render_knowledge_map(summary.get("knowledge_map", ""))
        with tab3:
            _render_highlights(summary.get("highlights", []))
        with tab4:
            _render_learning_data(
                summary.get("score_summary", {}),
                summary.get("personality", ""),
            )


def _render_notes(notes: str):
    """渲染结构化笔记"""
    st.markdown("### 📝 结构化笔记")
    st.markdown(notes)


def _render_knowledge_tree(tree_summary: str, tree_mermaid: str):
    """渲染知识树"""
    st.markdown("### 🌳 知识树掌握情况")

    view = st.radio("视图", ["列表视图", "图形视图"], horizontal=True, key="tree_view")

    if view == "列表视图":
        st.markdown(tree_summary)
    else:
        if tree_mermaid:
            st.markdown(tree_mermaid)
        else:
            st.info("图形视图暂未生成")


def _render_knowledge_map(map_code: str):
    """渲染知识图谱"""
    st.markdown("### 🗺️ 知识图谱")

    if map_code and ("mindmap" in map_code.lower() or "graph" in map_code.lower()):
        clean_code = map_code.strip()
        if clean_code.startswith("```mermaid"):
            clean_code = clean_code[10:]
        if clean_code.startswith("```"):
            clean_code = clean_code[3:]
        if clean_code.endswith("```"):
            clean_code = clean_code[:-3]
        clean_code = clean_code.strip()

        try:
            st.markdown(f"```mermaid\n{clean_code}\n```")
        except Exception:
            st.code(clean_code, language="mermaid")
    elif map_code:
        st.markdown(map_code)
    else:
        st.info("学习更多内容后将自动生成知识图谱 🗺️")


def _render_highlights(highlights: list[str]):
    """渲染知识点合集"""
    st.markdown("### 📌 官方知识点合集")

    if not highlights:
        st.info("本次学习暂未产生知识点高亮")
        return

    st.caption(f"共 {len(highlights)} 个知识点")

    for i, highlight in enumerate(highlights, 1):
        with st.expander(f"知识点 #{i}", expanded=i <= 3):
            st.markdown(highlight)


def _render_learning_data(score_summary: dict, personality: str):
    """渲染学习数据"""
    st.markdown("### 📈 学习数据")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("认知水平", score_summary.get("current_level", "L2"))
    with col2:
        st.metric("认知分数", f"{score_summary.get('current_score', 30):.0f}/100")
    with col3:
        st.metric("对话轮数", score_summary.get("rounds", 0))

    if personality:
        st.markdown("**性格画像**")
        st.markdown(personality)

    latest = score_summary.get("latest_dimensions")
    if latest:
        st.markdown("**五维度评估**")
        dimensions = {
            "概念理解": latest.get("concept_depth", 0),
            "逻辑推理": latest.get("logic_reasoning", 0),
            "关联迁移": latest.get("transfer_ability", 0),
            "举例应用": latest.get("example_ability", 0),
            "追问承接": latest.get("followup_ability", 0),
        }
        for dim_name, dim_score in dimensions.items():
            st.markdown(f"**{dim_name}**")
            st.progress(min(dim_score / 100, 1.0))
            st.caption(f"{dim_score:.0f}/100")
