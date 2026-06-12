"""LLM 配置管理 - 从环境变量加载"""

import os
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv


# 加载 .env 文件
load_dotenv()


@dataclass
class LLMConfig:
    """LLM 配置"""
    provider: str
    api_key: str
    base_url: str
    model: str
    temperature: float
    max_tokens: int
    timeout: int
    max_retries: int
    
    @classmethod
    def from_env(cls, provider: str = None) -> "LLMConfig":
        """从环境变量加载配置"""
        if provider is None:
            provider = os.getenv("LLM_PROVIDER", "deepseek")
        
        if provider == "deepseek":
            return cls(
                provider="deepseek",
                api_key=os.getenv("DEEPSEEK_API_KEY", ""),
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0.7")),
                max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "4096")),
                timeout=int(os.getenv("LLM_TIMEOUT", "60")),
                max_retries=int(os.getenv("LLM_MAX_RETRIES", "3"))
            )
        elif provider == "openai":
            return cls(
                provider="openai",
                api_key=os.getenv("OPENAI_API_KEY", ""),
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
                max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "4096")),
                timeout=int(os.getenv("LLM_TIMEOUT", "60")),
                max_retries=int(os.getenv("LLM_MAX_RETRIES", "3"))
            )
        else:
            raise ValueError(f"不支持的 LLM 提供商: {provider}")
    
    def validate(self) -> bool:
        """验证配置是否有效"""
        if not self.api_key:
            print(f"⚠️ 警告: {self.provider} API Key 未设置")
            return False
        return True
    
    def get_openai_kwargs(self) -> dict:
        """获取 OpenAI 客户端参数"""
        return {
            "api_key": self.api_key,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "max_retries": self.max_retries
        }


# 全局配置实例
_default_config: Optional[LLMConfig] = None


def get_llm_config(provider: str = None) -> LLMConfig:
    """获取 LLM 配置（单例）"""
    global _default_config
    if _default_config is None or provider is not None:
        _default_config = LLMConfig.from_env(provider)
    return _default_config


def reload_llm_config():
    """重新加载配置（修改 .env 后调用）"""
    global _default_config
    load_dotenv(override=True)
    _default_config = LLMConfig.from_env()
    print("📝 LLM 配置已重载")