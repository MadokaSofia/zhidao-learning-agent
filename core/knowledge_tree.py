"""
core/knowledge_tree.py - 知识树管理器
底层自动拆解学科知识树，支持点亮激励系统

功能：
- 根据教材/AI 自动拆解学科知识点结构
- 追踪每个知识点的掌握状态（点亮系统）
- 生成 Mermaid 可视化知识树
- 提供知识汇总（列表视图）
- 章节徽章激励机制

知识点状态：
- unlearned: 未学习（灰色）
- learning: 学习中（黄色）
- mastered: 已掌握 ≥80%（绿色 ✅）
- reviewing: 需巩固 50-80%（橙色 🟠）
- weak: 薄弱 <50%（红色 🔴）
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


# ==================== 数据结构 ====================

@dataclass
class KnowledgeNode:
    """知识点节点"""
    id: str                         # 唯一标识（如 "ch1.s1.p1"）
    name: str                       # 知识点名称
    parent_id: str = ""             # 父节点 ID
    level: int = 0                  # 层级：0=学科, 1=章节, 2=知识点, 3=子知识点
    status: str = "unlearned"       # unlearned/learning/mastered/reviewing/weak
    score: float = 0.0              # 掌握分数 0-100
    exam_weight: float = 0.5        # 考试权重 0-1
    difficulty: float = 0.5         # 难度 0-1
    children: list = field(default_factory=list)  # 子节点 ID 列表
    last_studied: str = ""          # 最后学习时间
    study_count: int = 0            # 学习次数

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "level": self.level,
            "status": self.status,
            "score": self.score,
            "exam_weight": self.exam_weight,
            "difficulty": self.difficulty,
            "children": self.children,
            "last_studied": self.last_studied,
            "study_count": self.study_count,
        }

    @staticmethod
    def from_dict(data: dict) -> "KnowledgeNode":
        return KnowledgeNode(
            id=data.get("id", ""),
            name=data.get("name", ""),
            parent_id=data.get("parent_id", ""),
            level=data.get("level", 0),
            status=data.get("status", "unlearned"),
            score=data.get("score", 0.0),
            exam_weight=data.get("exam_weight", 0.5),
            difficulty=data.get("difficulty", 0.5),
            children=data.get("children", []),
            last_studied=data.get("last_studied", ""),
            study_count=data.get("study_count", 0),
        )


# ==================== 知识树管理器 ====================

class KnowledgeTree:
    """
    知识树管理器

    负责：
    - 通过 AI 拆解学科知识树
    - 追踪每个知识点的掌握状态
    - 生成可视化（Mermaid 图 + 列表视图）
    - 提供知识点推荐顺序
    """

    SAVE_DIR = ".knowledge_trees"

    def __init__(self):
        self.nodes: dict[str, KnowledgeNode] = {}
        self.root_id: str = ""
        self.topic: str = ""
        self.created_at: str = ""
        self._loaded = False

    # ==================== 构建知识树 ====================

    def build_from_ai_response(self, topic: str, ai_tree_data: dict):
        """
        根据 AI 返回的知识树结构构建

        AI 返回的格式：
        {
            "topic": "初中物理",
            "chapters": [
                {
                    "name": "力学",
                    "exam_weight": 0.3,
                    "sections": [
                        {
                            "name": "力的概念",
                            "exam_weight": 0.4,
                            "difficulty": 0.3,
                            "sub_points": ["力的定义", "力的三要素", "力的分类"]
                        }
                    ]
                }
            ]
        }
        """
        self.topic = topic
        self.created_at = datetime.now().isoformat()
        self.nodes = {}

        # 创建根节点
        root = KnowledgeNode(
            id="root",
            name=ai_tree_data.get("topic", topic),
            level=0,
        )
        self.root_id = "root"
        self.nodes["root"] = root

        chapters = ai_tree_data.get("chapters", [])
        for ci, chapter in enumerate(chapters):
            ch_id = f"ch{ci+1}"
            ch_node = KnowledgeNode(
                id=ch_id,
                name=chapter.get("name", f"第{ci+1}章"),
                parent_id="root",
                level=1,
                exam_weight=chapter.get("exam_weight", 0.5),
            )
            root.children.append(ch_id)
            self.nodes[ch_id] = ch_node

            sections = chapter.get("sections", [])
            for si, section in enumerate(sections):
                sec_id = f"{ch_id}.s{si+1}"
                sec_node = KnowledgeNode(
                    id=sec_id,
                    name=section.get("name", f"知识点{si+1}"),
                    parent_id=ch_id,
                    level=2,
                    exam_weight=section.get("exam_weight", 0.5),
                    difficulty=section.get("difficulty", 0.5),
                )
                ch_node.children.append(sec_id)
                self.nodes[sec_id] = sec_node

                sub_points = section.get("sub_points", [])
                for pi, point in enumerate(sub_points):
                    pt_id = f"{sec_id}.p{pi+1}"
                    pt_name = point if isinstance(point, str) else point.get("name", "")
                    pt_node = KnowledgeNode(
                        id=pt_id,
                        name=pt_name,
                        parent_id=sec_id,
                        level=3,
                        exam_weight=section.get("exam_weight", 0.5),
                        difficulty=section.get("difficulty", 0.5),
                    )
                    sec_node.children.append(pt_id)
                    self.nodes[pt_id] = pt_node

        self._loaded = True

    # ==================== 状态更新 ====================

    def update_node_score(self, node_id: str, score: float):
        """
        更新知识点分数和状态

        Args:
            node_id: 知识点 ID
            score: 新分数 0-100
        """
        node = self.nodes.get(node_id)
        if not node:
            return

        # 移动平均更新分数
        if node.study_count > 0:
            alpha = 0.4
            node.score = (1 - alpha) * node.score + alpha * score
        else:
            node.score = score

        node.study_count += 1
        node.last_studied = datetime.now().isoformat()

        # 更新状态
        if node.score >= 80:
            node.status = "mastered"
        elif node.score >= 50:
            node.status = "reviewing"
        else:
            node.status = "weak"

        # 递归更新父节点
        self._update_parent_status(node.parent_id)

    def set_node_learning(self, node_id: str):
        """将节点标记为正在学习"""
        node = self.nodes.get(node_id)
        if node and node.status == "unlearned":
            node.status = "learning"

    def _update_parent_status(self, parent_id: str):
        """根据子节点状态更新父节点"""
        parent = self.nodes.get(parent_id)
        if not parent or not parent.children:
            return

        child_scores = []
        for cid in parent.children:
            child = self.nodes.get(cid)
            if child:
                child_scores.append(child.score)

        if child_scores:
            parent.score = sum(child_scores) / len(child_scores)
            if parent.score >= 80:
                parent.status = "mastered"
            elif parent.score >= 50:
                parent.status = "reviewing"
            elif any(self.nodes.get(cid, KnowledgeNode(id="")).status != "unlearned"
                     for cid in parent.children):
                parent.status = "learning"

        # 继续向上更新
        if parent.parent_id:
            self._update_parent_status(parent.parent_id)

    # ==================== 查找知识点 ====================

    def find_node_by_name(self, name: str) -> Optional[KnowledgeNode]:
        """按名称模糊查找知识点"""
        name_lower = name.lower()
        best_match = None
        best_score = 0

        for node in self.nodes.values():
            node_name_lower = node.name.lower()
            if name_lower == node_name_lower:
                return node
            if name_lower in node_name_lower or node_name_lower in name_lower:
                match_score = len(name_lower) / max(len(node_name_lower), 1)
                if match_score > best_score:
                    best_score = match_score
                    best_match = node

        return best_match

    def get_leaf_nodes(self) -> list[KnowledgeNode]:
        """获取所有叶子节点（最细粒度的知识点）"""
        return [n for n in self.nodes.values() if not n.children and n.level >= 2]

    def get_weak_nodes(self) -> list[KnowledgeNode]:
        """获取所有薄弱知识点"""
        return [n for n in self.nodes.values() if n.status == "weak" and n.level >= 2]

    def get_unlearned_nodes(self) -> list[KnowledgeNode]:
        """获取所有未学习的知识点"""
        return [n for n in self.nodes.values() if n.status == "unlearned" and n.level >= 2]

    def get_chapter_nodes(self) -> list[KnowledgeNode]:
        """获取所有章节节点"""
        return [n for n in self.nodes.values() if n.level == 1]

    # ==================== 统计 ====================

    def get_stats(self) -> dict:
        """获取知识树统计信息"""
        leaves = self.get_leaf_nodes()
        total = len(leaves)
        if total == 0:
            return {
                "total": 0, "mastered": 0, "reviewing": 0,
                "weak": 0, "learning": 0, "unlearned": 0,
                "progress_pct": 0, "lit_count": 0,
            }

        mastered = len([n for n in leaves if n.status == "mastered"])
        reviewing = len([n for n in leaves if n.status == "reviewing"])
        weak = len([n for n in leaves if n.status == "weak"])
        learning = len([n for n in leaves if n.status == "learning"])
        unlearned = len([n for n in leaves if n.status == "unlearned"])
        lit_count = mastered + reviewing  # 点亮 = 掌握 + 巩固中

        return {
            "total": total,
            "mastered": mastered,
            "reviewing": reviewing,
            "weak": weak,
            "learning": learning,
            "unlearned": unlearned,
            "progress_pct": round((mastered + reviewing * 0.5) / total * 100, 1),
            "lit_count": lit_count,
        }

    def get_chapter_badge(self, chapter_id: str) -> Optional[str]:
        """检查章节是否获得徽章"""
        chapter = self.nodes.get(chapter_id)
        if not chapter:
            return None

        # 递归检查所有子孙节点
        all_descendants = self._get_all_descendants(chapter_id)
        leaves = [n for n in all_descendants if not n.children]

        if not leaves:
            return None

        if all(n.status == "mastered" for n in leaves):
            return "🏅"  # 金牌 - 全部掌握
        if all(n.status in ("mastered", "reviewing") for n in leaves):
            return "🥈"  # 银牌 - 全部点亮
        return None

    def _get_all_descendants(self, node_id: str) -> list[KnowledgeNode]:
        """获取所有子孙节点"""
        result = []
        node = self.nodes.get(node_id)
        if not node:
            return result

        for cid in node.children:
            child = self.nodes.get(cid)
            if child:
                result.append(child)
                result.extend(self._get_all_descendants(cid))
        return result

    # ==================== 可视化 ====================

    def to_summary_text(self) -> str:
        """生成知识汇总文本（列表视图）"""
        if not self.nodes:
            return "知识树尚未生成。"

        stats = self.get_stats()
        lines = [
            f"📖 {self.topic} · 知识树",
            f"已点亮 {stats['lit_count']}/{stats['total']} 个知识点\n",
        ]

        root = self.nodes.get(self.root_id)
        if not root:
            return "\n".join(lines)

        for ch_id in root.children:
            chapter = self.nodes.get(ch_id)
            if not chapter:
                continue

            badge = self.get_chapter_badge(ch_id) or ""
            lines.append(f"**{chapter.name}** {badge}")

            for sec_id in chapter.children:
                section = self.nodes.get(sec_id)
                if not section:
                    continue

                status_icon = self._status_icon(section.status)
                score_str = f"{section.score:.0f}%" if section.score > 0 else ""
                status_label = self._status_label(section.status)
                lines.append(f"  {status_icon} {section.name} ··· {status_label} {score_str}")

                # 子知识点
                for pt_id in section.children:
                    point = self.nodes.get(pt_id)
                    if not point:
                        continue
                    pt_icon = self._status_icon(point.status)
                    lines.append(f"    {pt_icon} {point.name}")

            lines.append("")  # 章节间空行

        return "\n".join(lines)

    def to_mermaid(self) -> str:
        """生成 Mermaid 思维导图代码"""
        if not self.nodes:
            return ""

        root = self.nodes.get(self.root_id)
        if not root:
            return ""

        lines = ["```mermaid", "mindmap", f"  root(({root.name}))"]

        for ch_id in root.children:
            chapter = self.nodes.get(ch_id)
            if not chapter:
                continue
            badge = self.get_chapter_badge(ch_id) or ""
            lines.append(f"    {chapter.name} {badge}")

            for sec_id in chapter.children:
                section = self.nodes.get(sec_id)
                if not section:
                    continue
                icon = self._status_icon(section.status)
                lines.append(f"      {icon} {section.name}")

        lines.append("```")
        return "\n".join(lines)

    def to_progress_sidebar(self, plan_info: dict = None) -> str:
        """生成侧边栏进度显示文本"""
        stats = self.get_stats()
        total = stats["total"]
        lit = stats["lit_count"]
        pct = stats["progress_pct"]

        text = f"🔥 已点亮 {lit}/{total} 知识点"

        if plan_info:
            day = plan_info.get("current_day", 1)
            total_days = plan_info.get("total_days", 7)
            text += f" | Day {day}/{total_days}"

        return text

    # ==================== 持久化 ====================

    def save(self, user_id: str):
        """保存知识树到本地文件"""
        os.makedirs(self.SAVE_DIR, exist_ok=True)
        filepath = os.path.join(self.SAVE_DIR, f"{user_id}_{self.topic}.json")

        data = {
            "topic": self.topic,
            "root_id": self.root_id,
            "created_at": self.created_at,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, user_id: str, topic: str) -> bool:
        """从本地文件加载知识树"""
        filepath = os.path.join(self.SAVE_DIR, f"{user_id}_{topic}.json")
        if not os.path.exists(filepath):
            return False

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.topic = data.get("topic", topic)
            self.root_id = data.get("root_id", "root")
            self.created_at = data.get("created_at", "")
            self.nodes = {
                nid: KnowledgeNode.from_dict(ndata)
                for nid, ndata in data.get("nodes", {}).items()
            }
            self._loaded = True
            return True
        except Exception:
            return False

    # ==================== 辅助方法 ====================

    @staticmethod
    def _status_icon(status: str) -> str:
        return {
            "unlearned": "⬛",
            "learning": "🟡",
            "mastered": "✅",
            "reviewing": "🟠",
            "weak": "🔴",
        }.get(status, "⬛")

    @staticmethod
    def _status_label(status: str) -> str:
        return {
            "unlearned": "未学习",
            "learning": "学习中",
            "mastered": "掌握",
            "reviewing": "巩固",
            "weak": "薄弱",
        }.get(status, "未学习")
