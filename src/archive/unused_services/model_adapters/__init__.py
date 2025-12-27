"""
Model Adapters for Enhanced Translation Service

This package provides specialized adapters for different LLM providers with 
Phase 2 optimizations and advanced model support.

Key Features:
- GPT-5 family support with Responses API
- o3 model constraints and reasoning optimization
- Provider-specific prompt optimization for Phase 2 contexts
- Advanced error handling and retry logic
- Performance monitoring per model type
"""

from .base_adapter import BaseModelAdapter, ModelResponse, ModelCapabilities
from .openai_adapter import OpenAIAdapter

# Note: Other adapters (GeminiAdapter, AnthropicAdapter, UpstageAdapter) not yet implemented

__all__ = [
    'BaseModelAdapter',
    'ModelResponse',
    'ModelCapabilities',
    'OpenAIAdapter'
]