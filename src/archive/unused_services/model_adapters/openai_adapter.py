"""
OpenAI Model Adapter - Enhanced Support for GPT-4, GPT-5, and o3 Models

This adapter provides specialized handling for OpenAI models including:
- GPT-4o and GPT-4.1 standard chat completions
- GPT-5 family with Responses API integration
- o3 model with reasoning constraints and completion tokens
- Provider-specific prompt optimization for Phase 2 contexts
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Union
from openai import OpenAI

from .base_adapter import (
    BaseModelAdapter, ModelResponse, ModelCapabilities,
    ModelFamily, ResponseFormat, extract_korean_text_from_prompt
)


class OpenAIAdapter(BaseModelAdapter):
    """OpenAI model adapter with enhanced GPT-5 and o3 support"""
    
    # Model configurations
    MODEL_CONFIGS = {
        "gpt-4o": {
            "family": ModelFamily.GPT_4,
            "format": ResponseFormat.CHAT_COMPLETION,
            "max_tokens": 4096,
            "rate_limit_rpm": 10000,
            "rate_limit_tpm": 800000,
            "cost_input": 0.005,
            "cost_output": 0.015,
            "supports_temperature": True
        },
        "gpt-4.1": {
            "family": ModelFamily.GPT_4,
            "format": ResponseFormat.CHAT_COMPLETION,
            "max_tokens": 4096,
            "rate_limit_rpm": 10000,
            "rate_limit_tpm": 800000,
            "cost_input": 0.005,
            "cost_output": 0.015,
            "supports_temperature": True
        },
        "o3": {
            "family": ModelFamily.O3,
            "format": ResponseFormat.CHAT_COMPLETION,
            "max_tokens": 2048,
            "rate_limit_rpm": 5000,
            "rate_limit_tpm": 400000,
            "cost_input": 0.06,
            "cost_output": 0.18,
            "supports_temperature": False,  # o3 only supports temperature=1
            "supports_reasoning": True
        },
        "gpt-5": {
            "family": ModelFamily.GPT_5,
            "format": ResponseFormat.RESPONSES_API,
            "max_tokens": 8192,
            "rate_limit_rpm": 8000,
            "rate_limit_tpm": 1000000,
            "cost_input": 0.010,
            "cost_output": 0.030,
            "supports_temperature": True,
            "supports_reasoning": True
        },
        "gpt-5-mini": {
            "family": ModelFamily.GPT_5,
            "format": ResponseFormat.RESPONSES_API,
            "max_tokens": 4096,
            "rate_limit_rpm": 15000,
            "rate_limit_tpm": 2000000,
            "cost_input": 0.002,
            "cost_output": 0.008,
            "supports_temperature": True,
            "supports_reasoning": True
        },
        "gpt-5-nano": {
            "family": ModelFamily.GPT_5,
            "format": ResponseFormat.RESPONSES_API,
            "max_tokens": 2048,
            "rate_limit_rpm": 20000,
            "rate_limit_tpm": 3000000,
            "cost_input": 0.001,
            "cost_output": 0.003,
            "supports_temperature": True,
            "supports_reasoning": False
        }
    }
    
    def __init__(self, model_id: str, api_key: str):
        """
        Initialize OpenAI adapter
        
        Args:
            model_id: OpenAI model identifier
            api_key: OpenAI API key
        """
        # Get model configuration
        config = self.MODEL_CONFIGS.get(model_id)
        if not config:
            raise ValueError(f"Unsupported OpenAI model: {model_id}")
        
        # Create capabilities
        capabilities = ModelCapabilities(
            model_family=config["family"],
            response_format=config["format"],
            max_tokens=config["max_tokens"],
            supports_reasoning=config.get("supports_reasoning", False),
            supports_temperature=config["supports_temperature"],
            rate_limit_rpm=config.get("rate_limit_rpm"),
            rate_limit_tpm=config.get("rate_limit_tpm"),
            cost_per_input_token=config["cost_input"] / 1000000,
            cost_per_output_token=config["cost_output"] / 1000000
        )
        
        super().__init__(model_id, api_key, capabilities)
        
        # Initialize OpenAI client
        self.client = OpenAI(api_key=api_key)
        
        # Model-specific settings
        self.config = config
        self.is_gpt5_family = config["family"] == ModelFamily.GPT_5
        self.is_o3_model = config["family"] == ModelFamily.O3
        
        self.logger.info(f"OpenAI adapter initialized for {model_id} ({config['family'].value})")
    
    async def translate(self,
                       prompt: str,
                       max_tokens: Optional[int] = None,
                       temperature: Optional[float] = None,
                       **kwargs) -> ModelResponse:
        """Translate using OpenAI model"""
        
        start_time = time.time()
        
        # Check rate limits
        wait_time = self._check_rate_limits()
        if wait_time:
            await self._wait_for_rate_limit(wait_time)
        
        # Validate parameters
        params = self._validate_parameters(max_tokens, temperature)
        
        try:
            if self.is_gpt5_family:
                response = await self._translate_gpt5(prompt, params, **kwargs)
            elif self.is_o3_model:
                response = await self._translate_o3(prompt, params, **kwargs)
            else:
                response = await self._translate_standard(prompt, params, **kwargs)
            
            response.processing_time_ms = (time.time() - start_time) * 1000
            self._record_request(response)
            
            return response
            
        except Exception as e:
            error_response = ModelResponse(
                content="",
                model_used=self.model_id,
                error=str(e),
                processing_time_ms=(time.time() - start_time) * 1000
            )
            self._record_request(error_response)
            return error_response
    
    async def _translate_standard(self, prompt: str, params: Dict[str, Any], **kwargs) -> ModelResponse:
        """Translate using standard GPT-4 models"""
        
        response = self.client.chat.completions.create(
            model=self.model_id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=params.get('max_tokens', 500),
            temperature=params.get('temperature', 0.3)
        )
        
        content = response.choices[0].message.content.strip()
        tokens_used = response.usage.total_tokens
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        
        # Calculate cost
        cost = (input_tokens * self.capabilities.cost_per_input_token + 
                output_tokens * self.capabilities.cost_per_output_token)
        
        return ModelResponse(
            content=content,
            model_used=self.model_id,
            tokens_used=tokens_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason=response.choices[0].finish_reason
        )
    
    async def _translate_o3(self, prompt: str, params: Dict[str, Any], **kwargs) -> ModelResponse:
        """Translate using o3 model with reasoning constraints"""
        
        # o3 uses max_completion_tokens instead of max_tokens and only supports temperature=1
        response = self.client.chat.completions.create(
            model=self.model_id,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=min(params.get('max_tokens', 500), 2048)
            # Note: o3 only supports temperature=1, so we don't set it
        )
        
        content = response.choices[0].message.content.strip()
        tokens_used = response.usage.total_tokens
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        
        # o3 includes reasoning in response
        reasoning_content = getattr(response.choices[0], 'reasoning', None)
        
        # Calculate cost
        cost = (input_tokens * self.capabilities.cost_per_input_token + 
                output_tokens * self.capabilities.cost_per_output_token)
        
        return ModelResponse(
            content=content,
            model_used=self.model_id,
            tokens_used=tokens_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_content=reasoning_content,
            finish_reason=response.choices[0].finish_reason
        )
    
    async def _translate_gpt5(self, prompt: str, params: Dict[str, Any], **kwargs) -> ModelResponse:
        """Translate using GPT-5 family with Responses API"""
        
        # GPT-5 OWL specific optimizations for medical translation
        verbosity = "medium"  # Optimal for medical terminology precision
        reasoning_effort = "minimal"  # Cost-optimized while maintaining quality
        
        # Enhanced error handling for Responses API
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                # Use Responses API for GPT-5 family
                response = self.client.responses.create(
                    model=self.model_id,
                    input=[{"role": "user", "content": prompt}],
                    text={"verbosity": verbosity},
                    reasoning={"effort": reasoning_effort}
                )
                
                # Successful response - break retry loop
                break
                
            except Exception as e:
                if attempt == max_retries - 1:
                    # Final attempt failed
                    raise e
                
                # Handle specific GPT-5 errors
                if "rate_limit" in str(e).lower():
                    await asyncio.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                    continue
                elif "invalid_request" in str(e).lower():
                    # Don't retry invalid requests
                    raise e
                else:
                    await asyncio.sleep(retry_delay)
                    continue
        
        # Extract content from Responses API response
        content = self._extract_text_from_responses_api(response)
        
        # Try to extract token usage
        tokens_used = None
        input_tokens = None
        output_tokens = None
        reasoning_content = None
        
        try:
            if hasattr(response, "usage"):
                usage = response.usage
                tokens_used = getattr(usage, "total_tokens", None)
                input_tokens = getattr(usage, "input_tokens", None)
                output_tokens = getattr(usage, "output_tokens", None)
            
            # Extract reasoning if available
            if hasattr(response, "reasoning"):
                reasoning_content = str(response.reasoning)
        except Exception:
            pass
        
        return ModelResponse(
            content=content,
            model_used=self.model_id,
            tokens_used=tokens_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_content=reasoning_content
        )
    
    def _extract_text_from_responses_api(self, response) -> str:
        """Extract text content from OpenAI Responses API response"""
        try:
            # Try different possible response structures
            if hasattr(response, "output_text") and response.output_text:
                return str(response.output_text).strip()
            
            output = getattr(response, "output", None)
            if isinstance(output, str):
                return output.strip()
            elif output is not None:
                return str(output).strip()
            
            # Fallback for different response shapes
            if hasattr(response, "choices") and response.choices:
                return response.choices[0].message.content.strip()
                
        except Exception as e:
            self.logger.warning(f"Failed to extract text from Responses API: {e}")
        
        return ""
    
    async def translate_batch(self,
                            prompts: List[str],
                            max_tokens: Optional[int] = None,
                            temperature: Optional[float] = None,
                            **kwargs) -> List[ModelResponse]:
        """Translate multiple prompts"""
        
        # OpenAI doesn't have native batch API for chat completions
        # Process sequentially with controlled concurrency
        max_concurrent = kwargs.get('max_concurrent', 5)
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def translate_with_semaphore(prompt):
            async with semaphore:
                return await self.translate(prompt, max_tokens, temperature, **kwargs)
        
        tasks = [translate_with_semaphore(prompt) for prompt in prompts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_response = ModelResponse(
                    content="",
                    model_used=self.model_id,
                    error=str(result)
                )
                final_results.append(error_response)
            else:
                final_results.append(result)
        
        return final_results
    
    def optimize_prompt_for_model(self,
                                base_prompt: str,
                                korean_text: str,
                                context_type: str = "phase2") -> str:
        """Optimize prompt for OpenAI models"""
        
        if context_type == "phase2":
            # Phase 2 optimized prompt for OpenAI models
            return self._create_phase2_optimized_prompt(base_prompt, korean_text)
        else:
            # Phase 1 compatibility
            return base_prompt
    
    def _create_phase2_optimized_prompt(self, base_prompt: str, korean_text: str) -> str:
        """Create Phase 2 optimized prompt for OpenAI models"""
        
        if self.is_o3_model:
            # o3 model prompt optimization with reasoning focus
            return f"""You are an expert medical device translator specializing in Korean-English translation with reasoning capabilities.

CONTEXT (use for terminology and style consistency):
{self._extract_context_from_prompt(base_prompt)}

TASK: Translate the following Korean text to professional English medical device documentation.

REASONING APPROACH:
1. Analyze the Korean text for medical terminology and context
2. Identify key technical terms that require precise translation
3. Consider regulatory compliance requirements
4. Ensure consistency with provided context

KOREAN TEXT: {korean_text}

Provide a precise, professional translation suitable for medical device documentation."""
            
        elif self.is_gpt5_family:
            # GPT-5 OWL optimized prompt for medical translation with reasoning
            context_content = self._extract_context_from_prompt(base_prompt)
            
            return f"""# Medical Device Translation: Korean → English

## Terminology Context
{context_content}

## Translation Guidelines
- Maintain consistency with established terminology above
- Ensure regulatory compliance for medical device documentation  
- Preserve technical precision and professional tone
- Use locked terms exactly as specified
- Apply medical device industry standards

## Source Text (Korean)
{korean_text}

## Required Output
Provide only the professional English translation without explanations or notes."""
        
        else:
            # Standard GPT-4 prompt optimization
            return f"""Translate the following Korean medical device text to English with high precision.

Context for terminology consistency:
{self._extract_context_from_prompt(base_prompt)}

Korean text: {korean_text}

English translation:"""
    
    def _extract_context_from_prompt(self, prompt: str) -> str:
        """Extract relevant context from base prompt"""
        lines = prompt.split('\n')
        context_lines = []
        
        in_context_section = False
        for line in lines:
            if any(keyword in line.upper() for keyword in ['GLOSSARY', 'KEY TERMS', 'CONTEXT']):
                in_context_section = True
            elif in_context_section and any(keyword in line.upper() for keyword in ['KOREAN TEXT', 'TRANSLATE', 'TASK']):
                break
            elif in_context_section and line.strip():
                context_lines.append(line.strip())
        
        return '\n'.join(context_lines[:10])  # Limit context size
    
    def _validate_parameters(self, 
                           max_tokens: Optional[int] = None,
                           temperature: Optional[float] = None) -> Dict[str, Any]:
        """Validate parameters for OpenAI models"""
        params = super()._validate_parameters(max_tokens, temperature)
        
        # Special handling for o3 model
        if self.is_o3_model:
            # o3 only supports temperature=1, so remove temperature parameter
            if 'temperature' in params:
                del params['temperature']
            # o3 uses max_completion_tokens
            if 'max_tokens' in params:
                params['max_completion_tokens'] = params.pop('max_tokens')
        
        return params
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get OpenAI-specific performance statistics"""
        base_stats = super().get_performance_stats()
        
        # Add OpenAI-specific information
        base_stats['openai_specific'] = {
            'model_family': self.config['family'].value,
            'response_format': self.config['format'].value,
            'supports_reasoning': self.capabilities.supports_reasoning,
            'is_gpt5_family': self.is_gpt5_family,
            'is_o3_model': self.is_o3_model,
            'estimated_cost_per_request': self._estimate_cost_per_request()
        }
        
        return base_stats
    
    def _estimate_cost_per_request(self) -> float:
        """Estimate average cost per request"""
        if self.request_count == 0:
            return 0.0
        
        return self.total_cost_usd / self.request_count
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform OpenAI-specific health check"""
        base_health = await super().health_check()
        
        # Add OpenAI-specific health information
        base_health['openai_specific'] = {
            'client_initialized': self.client is not None,
            'model_configuration': self.config['family'].value,
            'api_format': self.config['format'].value
        }
        
        return base_health