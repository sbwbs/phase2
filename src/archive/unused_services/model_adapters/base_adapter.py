"""
Base Model Adapter - Abstract Interface for LLM Providers

This module defines the base interface for all model adapters with standardized
methods for translation, prompt optimization, and performance monitoring.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum


class ModelFamily(Enum):
    """Model family classifications"""
    GPT_4 = "gpt-4"
    GPT_5 = "gpt-5"
    O3 = "o3"
    GEMINI = "gemini"
    CLAUDE = "claude"
    SOLAR = "solar"


class ResponseFormat(Enum):
    """Response format types"""
    CHAT_COMPLETION = "chat_completion"
    RESPONSES_API = "responses_api"
    GENERATE_CONTENT = "generate_content"
    MESSAGES = "messages"


@dataclass
class ModelCapabilities:
    """Model capabilities and constraints"""
    model_family: ModelFamily
    response_format: ResponseFormat
    max_tokens: int
    supports_reasoning: bool = False
    supports_temperature: bool = True
    supports_streaming: bool = False
    rate_limit_rpm: Optional[int] = None
    rate_limit_tpm: Optional[int] = None
    context_window: int = 128000
    cost_per_input_token: float = 0.0
    cost_per_output_token: float = 0.0


@dataclass
class ModelResponse:
    """Standardized model response"""
    content: str
    model_used: str
    tokens_used: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    processing_time_ms: float = 0.0
    reasoning_content: Optional[str] = None
    finish_reason: Optional[str] = None
    error: Optional[str] = None
    
    @property
    def cost_usd(self) -> Optional[float]:
        """Calculate cost in USD if token counts and pricing available"""
        if self.input_tokens and self.output_tokens:
            # Will be calculated by specific adapters with their pricing
            return None
        return None


class BaseModelAdapter(ABC):
    """Abstract base class for all model adapters"""
    
    def __init__(self,
                 model_id: str,
                 api_key: str,
                 capabilities: ModelCapabilities,
                 enable_performance_tracking: bool = True):
        """
        Initialize base model adapter
        
        Args:
            model_id: Model identifier
            api_key: API key for authentication
            capabilities: Model capabilities
            enable_performance_tracking: Enable performance monitoring
        """
        self.model_id = model_id
        self.api_key = api_key
        self.capabilities = capabilities
        self.enable_performance_tracking = enable_performance_tracking
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Performance tracking
        self.request_count = 0
        self.total_tokens_used = 0
        self.total_cost_usd = 0.0
        self.total_processing_time_ms = 0.0
        self.error_count = 0
        self.rate_limit_errors = 0
        
        # Rate limiting
        self.last_request_time = 0.0
        self.request_timestamps: List[float] = []
        
        self.logger.info(f"Initialized {self.__class__.__name__} for model {model_id}")
    
    @abstractmethod
    async def translate(self,
                       prompt: str,
                       max_tokens: Optional[int] = None,
                       temperature: Optional[float] = None,
                       **kwargs) -> ModelResponse:
        """
        Translate using the model
        
        Args:
            prompt: Translation prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional model-specific parameters
            
        Returns:
            ModelResponse with translation result
        """
        pass
    
    @abstractmethod
    async def translate_batch(self,
                            prompts: List[str],
                            max_tokens: Optional[int] = None,
                            temperature: Optional[float] = None,
                            **kwargs) -> List[ModelResponse]:
        """
        Translate multiple prompts in batch
        
        Args:
            prompts: List of translation prompts
            max_tokens: Maximum tokens per translation
            temperature: Sampling temperature
            **kwargs: Additional model-specific parameters
            
        Returns:
            List of ModelResponse objects
        """
        pass
    
    @abstractmethod
    def optimize_prompt_for_model(self, 
                                base_prompt: str,
                                korean_text: str,
                                context_type: str = "phase2") -> str:
        """
        Optimize prompt for specific model
        
        Args:
            base_prompt: Base translation prompt
            korean_text: Korean text to translate
            context_type: Type of context (phase1/phase2)
            
        Returns:
            Optimized prompt for this model
        """
        pass
    
    def _check_rate_limits(self) -> Optional[float]:
        """
        Check rate limits and return wait time if needed
        
        Returns:
            Wait time in seconds, or None if no wait needed
        """
        if not self.capabilities.rate_limit_rpm:
            return None
        
        now = time.time()
        
        # Clean old requests (older than 1 minute)
        cutoff = now - 60
        self.request_timestamps = [t for t in self.request_timestamps if t > cutoff]
        
        # Check if we need to wait
        if len(self.request_timestamps) >= self.capabilities.rate_limit_rpm:
            oldest_request = min(self.request_timestamps)
            wait_time = 60 - (now - oldest_request)
            if wait_time > 0:
                return wait_time
        
        return None
    
    async def _wait_for_rate_limit(self, wait_time: float):
        """Wait for rate limit with jitter"""
        jitter = min(wait_time * 0.1, 2.0)  # Up to 10% jitter, max 2 seconds
        actual_wait = wait_time + (jitter * (0.5 - asyncio.get_event_loop().time() % 1))
        
        self.logger.info(f"Rate limit hit, waiting {actual_wait:.2f}s")
        await asyncio.sleep(actual_wait)
    
    def _record_request(self, response: ModelResponse):
        """Record request for performance tracking"""
        if not self.enable_performance_tracking:
            return
        
        self.request_count += 1
        self.request_timestamps.append(time.time())
        
        if response.tokens_used:
            self.total_tokens_used += response.tokens_used
        
        if response.processing_time_ms:
            self.total_processing_time_ms += response.processing_time_ms
        
        if response.error:
            self.error_count += 1
            if "rate limit" in response.error.lower():
                self.rate_limit_errors += 1
        
        # Calculate cost if possible
        cost = response.cost_usd
        if cost:
            self.total_cost_usd += cost
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation"""
        # Simple approximation: ~4 characters per token for mixed languages
        return len(text) // 4
    
    def _validate_parameters(self, 
                           max_tokens: Optional[int] = None,
                           temperature: Optional[float] = None) -> Dict[str, Any]:
        """Validate and adjust parameters for model"""
        params = {}
        
        # Validate max_tokens
        if max_tokens is not None:
            params['max_tokens'] = min(max_tokens, self.capabilities.max_tokens)
        else:
            params['max_tokens'] = min(500, self.capabilities.max_tokens)
        
        # Validate temperature
        if self.capabilities.supports_temperature:
            if temperature is not None:
                params['temperature'] = max(0.0, min(2.0, temperature))
            else:
                params['temperature'] = 0.3  # Default for translation
        
        return params
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        avg_processing_time = (self.total_processing_time_ms / max(self.request_count, 1))
        avg_tokens_per_request = (self.total_tokens_used / max(self.request_count, 1))
        error_rate = (self.error_count / max(self.request_count, 1)) * 100
        
        return {
            'model_info': {
                'model_id': self.model_id,
                'model_family': self.capabilities.model_family.value,
                'response_format': self.capabilities.response_format.value
            },
            'usage_stats': {
                'total_requests': self.request_count,
                'total_tokens_used': self.total_tokens_used,
                'total_cost_usd': self.total_cost_usd,
                'average_tokens_per_request': avg_tokens_per_request,
                'average_processing_time_ms': avg_processing_time
            },
            'error_stats': {
                'total_errors': self.error_count,
                'rate_limit_errors': self.rate_limit_errors,
                'error_rate_percent': error_rate
            },
            'rate_limiting': {
                'requests_per_minute_limit': self.capabilities.rate_limit_rpm,
                'tokens_per_minute_limit': self.capabilities.rate_limit_tpm,
                'recent_requests': len(self.request_timestamps)
            }
        }
    
    def reset_performance_stats(self):
        """Reset performance tracking"""
        self.request_count = 0
        self.total_tokens_used = 0
        self.total_cost_usd = 0.0
        self.total_processing_time_ms = 0.0
        self.error_count = 0
        self.rate_limit_errors = 0
        self.request_timestamps.clear()
        
        self.logger.info(f"Performance stats reset for {self.model_id}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check"""
        try:
            # Simple test translation
            test_response = await self.translate(
                "테스트",  # "test" in Korean
                max_tokens=50,
                temperature=0.0
            )
            
            return {
                'status': 'healthy' if not test_response.error else 'degraded',
                'model_id': self.model_id,
                'test_successful': not bool(test_response.error),
                'test_tokens_used': test_response.tokens_used,
                'test_processing_time_ms': test_response.processing_time_ms,
                'error': test_response.error
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'model_id': self.model_id,
                'test_successful': False,
                'error': str(e)
            }
    
    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.model_id})"
    
    def __repr__(self) -> str:
        return (f"{self.__class__.__name__}(model_id='{self.model_id}', "
                f"family={self.capabilities.model_family.value})")


# Utility functions for prompt optimization

def extract_korean_text_from_prompt(prompt: str) -> str:
    """Extract Korean text from translation prompt"""
    lines = prompt.split('\n')
    
    for i, line in enumerate(lines):
        line = line.strip()
        if line == "KOREAN TEXT TO TRANSLATE:" and i + 1 < len(lines):
            return lines[i + 1].strip()
        elif line.startswith("Korean:") and len(line) > 8:
            return line[7:].strip()
        elif "translate:" in line.lower() and i + 1 < len(lines):
            korean_line = lines[i + 1].strip()
            if any('\u3131' <= c <= '\u3163' or '\uac00' <= c <= '\ud7a3' for c in korean_line):
                return korean_line
    
    # Fallback: find line with Korean characters
    for line in lines:
        if any('\u3131' <= c <= '\u3163' or '\uac00' <= c <= '\ud7a3' for c in line):
            return line.strip()
    
    return "Korean text not found"


def count_korean_characters(text: str) -> int:
    """Count Korean characters in text"""
    return len([c for c in text if '\u3131' <= c <= '\u3163' or '\uac00' <= c <= '\ud7a3'])


def is_korean_text(text: str) -> bool:
    """Check if text contains Korean characters"""
    return count_korean_characters(text) > 0