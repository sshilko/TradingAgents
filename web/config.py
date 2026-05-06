"""Web interface configuration and safe config serialization."""

import os
from typing import Dict, Any, List, Optional
from tradingagents.default_config import DEFAULT_CONFIG


# Fields to exclude from safe config (contain secrets)
SECRET_FIELDS = {
    "alpha_vantage_api_key",
    "openai_api_key",
    "anthropic_api_key",
    "google_api_key",
    "xai_api_key",
    "deepseek_api_key",
    "qwen_api_key",
    "glm_api_key",
    "openrouter_api_key",
    "azure_api_key",
    "azure_api_version",
    "passkey",
}


def get_safe_config() -> Dict[str, Any]:
    """Return a sanitized version of DEFAULT_CONFIG (no secrets)."""
    return {
        k: v for k, v in DEFAULT_CONFIG.items()
        if k not in SECRET_FIELDS
    }


def apply_web_config(user_config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply user-provided config values to DEFAULT_CONFIG.
    
    Merges user values with defaults, preserving secrets from environment.
    """
    config = DEFAULT_CONFIG.copy()
    
    # Apply user values
    for key, value in user_config.items():
        if key in SECRET_FIELDS:
            # Use environment variable for secrets
            config[key] = os.getenv(key, value)
        elif key in config:
            config[key] = value
    
    return config


# Default analyst options
ANALYST_OPTIONS = [
    {"value": "market", "label": "Market Analyst", "description": "Stock price and volume analysis"},
    {"value": "social", "label": "Social Media Analyst", "description": "Social media sentiment analysis"},
    {"value": "news", "label": "News Analyst", "description": "News and insider transactions analysis"},
    {"value": "fundamentals", "label": "Fundamentals Analyst", "description": "Financial fundamentals analysis"},
]

# LLM provider options
LLM_PROVIDER_OPTIONS = [
    {"value": "openai", "label": "OpenAI"},
    {"value": "anthropic", "label": "Anthropic"},
    {"value": "google", "label": "Google"},
    {"value": "xai", "label": "xAI (Grok)"},
    {"value": "deepseek", "label": "DeepSeek"},
    {"value": "qwen", "label": "Qwen (Alibaba)"},
    {"value": "glm", "label": "GLM (Zhipu)"},
    {"value": "openrouter", "label": "OpenRouter"},
    {"value": "azure", "label": "Azure OpenAI"},
    {"value": "ollama", "label": "Ollama (Local)"},
]

# Server settings
SERVER_HOST = os.getenv("WEB_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("WEB_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
