"""
demo.py - 终端模拟演示
直接调用 Wegent API 模拟「知道」学习助手的对话效果
"""

import json
from openai import OpenAI

# Wegent API 配置
client = OpenAI(
    api_key="sk-wecode-7JAjaovaio34",
    base_url="https://copilot.weibo.com/v1",
    default_headers={
        "wecode-user": "suying6",
        "wecode-action": "wegent",
    },
)

MODEL = "claude-haiku-4-5-20251001"

# 系统提示词（精简版）
SYSTEM_PROMPT = """你是「知道」—— 一位自适应智能学习助手。你的核心能力是通过苏格拉底式追问引导用户主动思考，用最接地气的方式把复杂知识讲明白。

当前学习主题：初中物理-力学
当前模式：学科攻克模式
用户身份：学生
用户认知水平：L2（30/100）

## 教学策略
- 使用苏格拉底式追问，引导用户自己思考答案
- 答对时追问「你是怎么想的？」，挖掘理解深度
- 答错时不直接给答案，从「为什么」开始接地气讲解
- 每个知识点讲完，必须用 📌 官方知识点 Highlight 收尾
- 桥接确认：把大白话和官方表述连起来
- 语气亲切，像一个有趣的大哥哥/大姐姐在聊天
- 适当使用 emoji

## 📌 官方知识点格式
讲完后展示：
📌 **官方知识点**
━━━━━━━━━━━━━━━━━━━━━━━━━━━
**【定义】** [标准定义]
**【公式】** [如有]
**【关键词】** [考试关键词]
**【易错点】** [常见错误]
━━━━━━━━━━━━━━━━━━━━━━━━━━━

现在开始摸底诊断。先和用户打个招呼，告诉TA我们先做几道小题热热身，然后出第一道题（选择题，亲切轻松的语气）。"""


def demo():
    print("=" * 60)
    print("🧠 「知道」自适应智能学习助手 — 终端演示")
    print("   主题：初中物理-力学 | 模式：学科攻克")
    print("=" * 60)
    print()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # 获取开场白
    print("⏳ 正在连接 AI...")
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=1024,
    )
    assistant_msg = response.choices[0].message.content
    messages.append({"role": "assistant", "content": assistant_msg})

    print(f"\n🤖 知道：\n{assistant_msg}\n")

    # 模拟用户对话
    simulated_user_inputs = [
        "A",
        "嗯...因为力气大？",
        "哦，就像推购物车一样，越重越难推？",
    ]

    for i, user_input in enumerate(simulated_user_inputs):
        print(f"{'─' * 50}")
        print(f"👤 用户：{user_input}\n")

        messages.append({"role": "user", "content": user_input})

        print("⏳ 思考中...")
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )
        assistant_msg = response.choices[0].message.content
        messages.append({"role": "assistant", "content": assistant_msg})

        print(f"\n🤖 知道：\n{assistant_msg}\n")

    print("=" * 60)
    print("✅ 演示完成！以上就是「知道」的教学对话效果")
    print("=" * 60)


if __name__ == "__main__":
    demo()
