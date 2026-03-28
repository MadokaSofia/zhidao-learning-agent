"""
core/ai_client.py - AI 模型调用客户端
支持 DeepSeek / 通义千问 / 智谱，统一使用 OpenAI 兼容接口
"""

import json
import streamlit as st
from typing import Generator, Optional
from openai import OpenAI
from utils.config import AppConfig


class AIClient:
    """AI 模型客户端，兼容多种国产大模型"""

    def __init__(self, config: AppConfig):
        self.config = config
        self._client = None

    @property
    def client(self) -> OpenAI:
        """懒加载 OpenAI 兼容客户端"""
        if self._client is None:
            self._client = OpenAI(
                api_key=self.config.ai.api_key,
                base_url=self.config.ai.base_url,
            )
        return self._client

    def chat(
        self,
        messages: list[dict],
        temperature: float = None,
        max_tokens: int = None,
        stream: bool = False,
    ) -> str | Generator:
        """
        发送对话请求

        Args:
            messages: 对话消息列表 [{"role": "system/user/assistant", "content": "..."}]
            temperature: 温度参数（None 使用默认）
            max_tokens: 最大 token 数
            stream: 是否流式输出

        Returns:
            str 或 Generator
        """
        params = {
            "model": self.config.ai.model,
            "messages": messages,
            "temperature": temperature or self.config.ai.temperature,
            "max_tokens": max_tokens or self.config.ai.max_tokens,
            "stream": stream,
        }

        try:
            response = self.client.chat.completions.create(**params)

            if stream:
                return self._stream_response(response)
            else:
                return response.choices[0].message.content or ""
        except Exception as e:
            error_msg = f"AI 模型调用出错: {str(e)}"
            st.error(error_msg)
            return error_msg

    def _stream_response(self, response) -> Generator:
        """处理流式响应"""
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def chat_json(
        self,
        messages: list[dict],
        temperature: float = 0.3,
    ) -> dict:
        """
        发送对话请求，期望返回 JSON

        用于内部引擎（打分、性格分析等），需要结构化输出
        """
        # 在系统提示中强调 JSON 输出
        enhanced_messages = messages.copy()
        if enhanced_messages and enhanced_messages[0]["role"] == "system":
            enhanced_messages[0]["content"] += "\n\n请严格以 JSON 格式返回结果，不要包含 markdown 代码块标记。"

        result = self.chat(enhanced_messages, temperature=temperature, stream=False)

        if isinstance(result, str):
            # 尝试提取 JSON
            result = result.strip()
            # 移除可能的 markdown 代码块包裹
            if result.startswith("```json"):
                result = result[7:]
            elif result.startswith("```"):
                result = result[3:]
            if result.endswith("```"):
                result = result[:-3]
            result = result.strip()

            try:
                return json.loads(result)
            except json.JSONDecodeError:
                # 尝试在字符串中查找 JSON
                start = result.find("{")
                end = result.rfind("}") + 1
                if start >= 0 and end > start:
                    try:
                        return json.loads(result[start:end])
                    except json.JSONDecodeError:
                        pass
                return {"error": "JSON 解析失败", "raw": result}
        return {"error": "意外的返回类型"}
