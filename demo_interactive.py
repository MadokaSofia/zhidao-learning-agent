"""
demo_interactive.py - 完整交互式终端演示
在 Wegent 内网环境调用 API，完整体验「知道」学习助手的核心功能
"""

import json
import sys
from openai import OpenAI

# ==================== Wegent API 配置 ====================
client = OpenAI(
    api_key="sk-wecode-7JAjaovaio34",
    base_url="https://copilot.weibo.com/v1",
    default_headers={
        "wecode-user": "suying6",
        "wecode-action": "wegent",
    },
)
MODEL = "claude-haiku-4-5-20251001"


# ==================== 系统提示词 ====================

SYSTEM_PROMPTS = {
    "academic": """你是「知道」—— 一位自适应智能学习助手。

## 核心身份
你像一个有趣、耐心的大哥哥/大姐姐，通过苏格拉底式追问引导用户主动思考。

## 当前设置
- 学习主题：{topic}
- 模式：学科攻克模式（考试导向）
- 用户身份：学生

## 教学规则

### 苏格拉底追问（最重要！）
- 永远不直接给答案！通过追问引导用户自己想到答案
- 答对时追问「你是怎么想的？」「如果换个条件呢？」
- 答错时不批评，先问「你是怎么思考的？」然后从「为什么」开始引导

### 认知断点讲解
当用户明显不懂时，从最底层的"为什么"开始讲：
- ❌ 不说：「牛顿第二定律是 F=ma」
- ✅ 要说：「你有没有想过，为什么推重的东西比轻的更费劲？想象你推购物车...」

### 📌 官方知识点收尾（每个知识点必须走到这一步）
讲明白之后，必须展示官方知识点卡片：

📌 **官方知识点**
━━━━━━━━━━━━━━━━━━━━━━━━━━━
**【定义】** 标准定义
**【公式】** 公式（如有）
**【关键词】** 考试关键词
**【易错点】** 常见错误
━━━━━━━━━━━━━━━━━━━━━━━━━━━

然后用桥接话术连接：「所以刚才说的大白话，用物理语言说就是...考试写这个就满分！」

### 风格
- 亲切口语化，像聊天不像上课
- 适当用 emoji
- 类比生活场景
- 每次回复不要太长，保持对话节奏

现在开始！先打个招呼，告诉学生我们做几道热身题，然后出第一道选择题。""",

    "explore": """你是「知道」—— 一位自适应智能学习助手。

## 核心身份
你像一个见多识广的朋友，通过聊天式追问帮用户建立对新领域的认知框架。

## 当前设置
- 学习主题：{topic}
- 模式：领域探索模式（认知导向）
- 用户身份：{role_name}

## 教学规则

### 苏格拉底式引导
- 不直接灌输，通过追问让用户暴露认知边界
- 「你觉得为什么会这样？」「这背后的原因是什么？」
- 用户有洞察时深入探讨，有盲区时从「为什么」开始讲

### 认知断点讲解
- ❌ 不说：「大健康行业分为医疗、保健、健康管理三大板块」
- ✅ 要说：「我们先想一个根本问题——人为什么要花钱在健康上？」

### 📎 专业说法提示
在关键概念处插入行业术语：
📎 **专业说法**：行业里管这个叫「XXX」
💡 和别人聊的时候用这个词，显得你很懂行 😉

### 风格
- 轻松随和，像朋友聊天
- 多用案例和类比
- 适当用 emoji
- 推荐延伸话题：「基于咱们聊的，你可能还想了解 XX」

现在开始！先和用户自然地打个招呼，然后通过对话了解TA对这个领域知道多少。"""
}


def choose_role():
    """身份选择"""
    print()
    print("┌─────────────────────────────────────┐")
    print("│     🧠 「知道」自适应智能学习助手       │")
    print("│                                      │")
    print("│  苏格拉底追问 × 性格感知 × 认知评估    │")
    print("└─────────────────────────────────────┘")
    print()
    print("👤 你是谁？")
    print()
    print("  1. 🎒 我是学生       → 学科攻克模式（有标准答案和公式）")
    print("  2. 💼 我是职场人     → 领域探索模式（了解行业底层逻辑）")
    print("  3. 🌟 我是好奇宝宝   → 领域探索模式（纯兴趣探索）")
    print()

    while True:
        choice = input("输入数字选择 (1/2/3): ").strip()
        if choice in ("1", "2", "3"):
            return choice
        print("请输入 1、2 或 3")


def choose_topic(role_choice):
    """主题选择"""
    print()
    print("📚 你想学什么？")
    print()

    if role_choice == "1":
        examples = ["初中物理-力学", "高中生物-遗传", "初中数学-函数", "高中化学-有机"]
        print("  热门主题：")
        for i, ex in enumerate(examples, 1):
            print(f"    {i}. {ex}")
    elif role_choice == "2":
        examples = ["AI Agent", "大健康行业", "新能源赛道", "产品设计方法论"]
        print("  热门主题：")
        for i, ex in enumerate(examples, 1):
            print(f"    {i}. {ex}")
    else:
        examples = ["量子力学入门", "古希腊哲学", "宇宙大爆炸", "博弈论"]
        print("  热门主题：")
        for i, ex in enumerate(examples, 1):
            print(f"    {i}. {ex}")

    print()
    topic = input("输入主题（或输入数字选热门）: ").strip()

    if topic.isdigit() and 1 <= int(topic) <= len(examples):
        topic = examples[int(topic) - 1]

    return topic


def chat_with_ai(messages):
    """调用 AI"""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=1500,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ AI 调用出错: {e}"


def main():
    # Step 1: 选身份
    role_choice = choose_role()
    role_map = {"1": ("student", "学生"), "2": ("professional", "职场人"), "3": ("curious", "好奇宝宝")}
    role, role_name = role_map[role_choice]
    mode = "academic" if role == "student" else "explore"

    print(f"\n✅ 已选择：{role_name} → {'学科攻克模式 📚' if mode == 'academic' else '领域探索模式 🌍'}")

    # Step 2: 选主题
    topic = choose_topic(role_choice)
    print(f"\n✅ 学习主题：{topic}")

    # Step 3: 构建系统提示
    system_prompt = SYSTEM_PROMPTS[mode].format(topic=topic, role_name=role_name)
    messages = [{"role": "system", "content": system_prompt}]

    # Step 4: 获取开场白
    print()
    print("=" * 55)
    print(f"  🧠 开始学习「{topic}」")
    print(f"  输入你的回答即可对话，输入 q 退出")
    print("=" * 55)
    print()
    print("⏳ 正在准备...")

    opening = chat_with_ai(messages)
    messages.append({"role": "assistant", "content": opening})
    print(f"\n🤖 知道：\n{opening}\n")

    # Step 5: 对话循环
    round_count = 0
    while True:
        print("─" * 50)
        user_input = input("👤 你：").strip()

        if not user_input:
            continue
        if user_input.lower() in ("q", "quit", "exit", "退出", "结束"):
            break

        round_count += 1
        messages.append({"role": "user", "content": user_input})

        print("\n⏳ 思考中...")
        response = chat_with_ai(messages)
        messages.append({"role": "assistant", "content": response})
        print(f"\n🤖 知道：\n{response}\n")

    # Step 6: 结束总结
    print()
    print("=" * 55)
    print(f"  📊 本次学习小结")
    print(f"  主题：{topic}")
    print(f"  对话轮数：{round_count}")
    print("=" * 55)

    if round_count >= 2:
        print("\n⏳ 正在生成学习总结...")
        summary_prompt = f"""请根据刚才的对话，用 3-5 条要点总结本次学习内容，格式：
1. 📋 本次学习了什么
2. ✅ 掌握了哪些知识点
3. ❌ 还需要加强的地方
4. 📌 官方知识点回顾（列出本次出现的关键定义/公式）
5. 🎯 下次建议学什么"""
        messages.append({"role": "user", "content": summary_prompt})
        summary = chat_with_ai(messages)
        print(f"\n{summary}")

    print("\n👋 下次见！继续加油！")


if __name__ == "__main__":
    main()
