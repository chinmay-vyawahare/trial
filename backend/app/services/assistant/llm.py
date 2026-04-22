"""
Shared LLM client configuration for the assistant nodes.

Uses ChatOpenAI (langchain) pointed at the Nokia LLM gateway
with standard OpenAI base URL.
"""

import os
from langchain_openai import ChatOpenAI
from openai import OpenAI

# LLM config — Nokia gateway structure with OpenAI base URL
LLM_BASE_URL = "https://api.openai.com/v1"
LLM_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-nano")
LLM_API_KEY = os.getenv("OPENAI_API_KEY", "NONE")
LLM_HEADERS = {
    "api-key": LLM_API_KEY,
    "workspacename": "VR1857RolloutAgentDevSpace",
}


def get_chat_llm(temperature: float = 0, max_tokens: int | None = None) -> ChatOpenAI:
    """Return a ChatOpenAI instance configured with Nokia gateway structure."""
    kwargs = {
        "api_key": LLM_API_KEY,
        "model": LLM_MODEL,
        "base_url": LLM_BASE_URL,
        "default_headers": LLM_HEADERS,
        "temperature": temperature,
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    return ChatOpenAI(**kwargs)


def get_openai_client() -> OpenAI:
    """Return a raw OpenAI client for tool-calling (scheduler node)."""
    return OpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        default_headers=LLM_HEADERS,
    )
