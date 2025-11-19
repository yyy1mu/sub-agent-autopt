"""LLM配置模块"""
import os
from langchain_openai import ChatOpenAI


def build_llm(model: str | None = None, base_url: str | None = None, api_key: str | None = None) -> ChatOpenAI:
    """
    构建LLM实例
    
    Args:
        model: 模型名称，默认从环境变量OPENAI_MODEL获取，或使用"deepseek-chat"
        base_url: API基础URL，默认从环境变量OPENAI_BASE_URL获取，或使用"https://api.deepseek.com"
        api_key: API密钥，默认从环境变量OPENAI_API_KEY获取
    
    Returns:
        ChatOpenAI实例
    """
    llm_model = model or os.getenv("OPENAI_MODEL", "deepseek-chat")
    llm_base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    llm_api_key = api_key or os.getenv("OPENAI_API_KEY", "sk-3d0640bc0c6f450ba7ba130681c2c9d2")
    
    return ChatOpenAI(model=llm_model, temperature=0.1, base_url=llm_base_url, api_key=llm_api_key)

