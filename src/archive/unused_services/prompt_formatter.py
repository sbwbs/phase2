"""
Prompt Formatter for Phase 2 MVP - GPT-5 Optimized Clinical Translation

This module formats optimized contexts into structured prompts specifically 
designed for GPT-5 family models (GPT-5, GPT-5 Mini, GPT-5 Nano) in clinical 
trial translation tasks.

Key Features:
- GPT-5 native prompt structure with reasoning integration
- Clinical trial domain-specific formatting
- Consistency enforcement with locked terms
- Quality enhancement through structured instructions
- Token-efficient prompt construction
"""

import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum
import json
import re


class PromptTemplate(Enum):
    """Available prompt templates for different model families"""
    GPT5_REASONING = "gpt5_reasoning"
    GPT5_STANDARD = "gpt5_standard"
    GPT4_OPTIMIZED = "gpt4_optimized"
    O3_COMPATIBLE = "o3_compatible"


@dataclass
class PromptFormatConfig:
    """Configuration for prompt formatting"""
    model_family: str  # 'gpt-5', 'gpt-4o', 'o3'
    template: PromptTemplate
    include_reasoning_instructions: bool = True
    include_consistency_checks: bool = True
    include_quality_criteria: bool = True
    max_examples: int = 3
    domain: str = "clinical_trial"
    output_format: str = "json"  # 'json', 'text', 'structured'


@dataclass
class FormattedPrompt:
    """Formatted prompt ready for LLM API call"""
    prompt: str
    system_message: Optional[str] = None
    user_message: Optional[str] = None
    messages: Optional[List[Dict[str, str]]] = None
    model_specific_params: Dict[str, Any] = None
    estimated_tokens: int = 0
    format_type: str = "messages"  # 'messages', 'single', 'reasoning'


class PromptFormatter:
    """Advanced prompt formatter for clinical translation tasks"""
    
    # Domain-specific instructions
    CLINICAL_TRIAL_INSTRUCTIONS = {
        "accuracy": "Maintain precise medical accuracy and regulatory compliance",
        "terminology": "Use consistent medical terminology throughout the document",
        "format": "Preserve document structure and formatting requirements",
        "regulatory": "Follow clinical trial documentation standards (ICH-GCP)",
        "consistency": "Ensure terminology consistency within the document session"
    }
    
    # Quality criteria for clinical translations
    QUALITY_CRITERIA = [
        "Medical accuracy and terminology precision",
        "Regulatory compliance for clinical documentation",
        "Consistency with previously translated terms",
        "Natural fluency in target language",
        "Preservation of technical meaning and context"
    ]
    
    def __init__(self, 
                 default_config: Optional[PromptFormatConfig] = None,
                 enable_prompt_caching: bool = True):
        """
        Initialize prompt formatter
        
        Args:
            default_config: Default formatting configuration
            enable_prompt_caching: Enable caching of formatted prompts
        """
        self.default_config = default_config or PromptFormatConfig(
            model_family="gpt-5",
            template=PromptTemplate.GPT5_REASONING,
            domain="clinical_trial"
        )
        
        self.enable_caching = enable_prompt_caching
        self.prompt_cache: Dict[str, FormattedPrompt] = {}
        
        self.logger = logging.getLogger(__name__)
        
        self.logger.info(f"PromptFormatter initialized with {self.default_config.model_family} "
                        f"template: {self.default_config.template.value}")
    
    def format_translation_prompt(self,
                                optimized_context: str,
                                source_text: str,
                                target_language: str = "English",
                                config: Optional[PromptFormatConfig] = None) -> FormattedPrompt:
        """
        Format optimized context into a structured translation prompt
        
        Args:
            optimized_context: Context from ContextBuilder
            source_text: Source text to translate
            target_language: Target language name
            config: Optional formatting configuration
            
        Returns:
            FormattedPrompt ready for API call
        """
        config = config or self.default_config
        
        # Check cache first
        if self.enable_caching:
            cache_key = self._generate_cache_key(optimized_context, source_text, config)
            if cache_key in self.prompt_cache:
                return self.prompt_cache[cache_key]
        
        # Route to appropriate formatter based on template
        if config.template == PromptTemplate.GPT5_REASONING:
            formatted_prompt = self._format_gpt5_reasoning_prompt(
                optimized_context, source_text, target_language, config
            )
        elif config.template == PromptTemplate.GPT5_STANDARD:
            formatted_prompt = self._format_gpt5_standard_prompt(
                optimized_context, source_text, target_language, config
            )
        elif config.template == PromptTemplate.GPT4_OPTIMIZED:
            formatted_prompt = self._format_gpt4_optimized_prompt(
                optimized_context, source_text, target_language, config
            )
        elif config.template == PromptTemplate.O3_COMPATIBLE:
            formatted_prompt = self._format_o3_compatible_prompt(
                optimized_context, source_text, target_language, config
            )
        else:
            # Fallback to GPT-5 standard
            formatted_prompt = self._format_gpt5_standard_prompt(
                optimized_context, source_text, target_language, config
            )
        
        # Cache result
        if self.enable_caching:
            self.prompt_cache[cache_key] = formatted_prompt
        
        self.logger.debug(f"Formatted prompt using {config.template.value} template "
                         f"({formatted_prompt.estimated_tokens} tokens)")
        
        return formatted_prompt
    
    def _format_gpt5_reasoning_prompt(self,
                                    context: str,
                                    source_text: str,
                                    target_language: str,
                                    config: PromptFormatConfig) -> FormattedPrompt:
        """Format prompt for GPT-5 with reasoning capabilities"""
        
        # System message with reasoning instructions
        system_message = self._build_system_message(config, include_reasoning=True)
        
        # User message with structured context and task
        user_message = f"""
TRANSLATION TASK:
Translate the following Korean clinical trial text to {target_language} with high accuracy and consistency.

CONTEXT INFORMATION:
{context}

SOURCE TEXT TO TRANSLATE:
{source_text}

REASONING PROCESS:
1. Analyze the source text for medical terminology and context
2. Identify any terms that match the provided glossary or locked terms
3. Ensure consistency with previously translated segments
4. Apply clinical trial documentation standards

RESPONSE FORMAT:
Please provide your translation in this JSON format:
{{
    "reasoning": "Brief explanation of translation decisions and terminology choices",
    "translation": "The final {target_language} translation",
    "terminology_used": ["list", "of", "key", "terms", "applied"],
    "confidence": 0.95
}}

Remember: Maintain medical accuracy, regulatory compliance, and terminology consistency.
""".strip()
        
        # Model-specific parameters for GPT-5
        model_params = {
            "reasoning": {"effort": "medium"},
            "text": {"verbosity": "medium"},
            "temperature": 0.2,
            "max_completion_tokens": 500
        }
        
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
        
        return FormattedPrompt(
            prompt=user_message,
            system_message=system_message,
            user_message=user_message,
            messages=messages,
            model_specific_params=model_params,
            estimated_tokens=self._estimate_prompt_tokens(system_message + user_message),
            format_type="reasoning"
        )
    
    def _format_gpt5_standard_prompt(self,
                                   context: str,
                                   source_text: str,
                                   target_language: str,
                                   config: PromptFormatConfig) -> FormattedPrompt:
        """Format standard prompt for GPT-5 models"""
        
        system_message = self._build_system_message(config, include_reasoning=False)
        
        user_message = f"""
Context:
{context}

Task: Translate this Korean clinical trial text to {target_language}:
{source_text}

Requirements:
- Maintain medical accuracy and regulatory compliance
- Use consistent terminology as specified in the context
- Follow clinical trial documentation standards
- Provide natural, fluent translation

Translation:
""".strip()
        
        model_params = {
            "temperature": 0.2,
            "max_completion_tokens": 300,
            "text": {"verbosity": "medium"}
        }
        
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
        
        return FormattedPrompt(
            prompt=user_message,
            system_message=system_message,
            user_message=user_message,
            messages=messages,
            model_specific_params=model_params,
            estimated_tokens=self._estimate_prompt_tokens(system_message + user_message),
            format_type="messages"
        )
    
    def _format_gpt4_optimized_prompt(self,
                                    context: str,
                                    source_text: str,
                                    target_language: str,
                                    config: PromptFormatConfig) -> FormattedPrompt:
        """Format prompt optimized for GPT-4o models"""
        
        system_message = f"""You are an expert medical translator specializing in clinical trial documentation. 
Translate Korean clinical trial texts to {target_language} with high accuracy, maintaining medical terminology consistency and regulatory compliance."""
        
        user_message = f"""
Please translate the following Korean clinical trial text to {target_language}.

Context:
{context}

Source text:
{source_text}

Instructions:
- Use the provided glossary terms for consistency
- Maintain medical accuracy and regulatory standards
- Follow the terminology patterns from locked terms
- Provide clear, professional translation

Translation:
""".strip()
        
        model_params = {
            "temperature": 0.1,
            "max_tokens": 300
        }
        
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
        
        return FormattedPrompt(
            prompt=user_message,
            system_message=system_message,
            user_message=user_message,
            messages=messages,
            model_specific_params=model_params,
            estimated_tokens=self._estimate_prompt_tokens(system_message + user_message),
            format_type="messages"
        )
    
    def _format_o3_compatible_prompt(self,
                                   context: str,
                                   source_text: str,
                                   target_language: str,
                                   config: PromptFormatConfig) -> FormattedPrompt:
        """Format prompt compatible with O3 model constraints"""
        
        # O3 has specific requirements - simpler structure
        combined_prompt = f"""
{context}

Translate this Korean clinical trial text to {target_language}:
{source_text}

Requirements: Medical accuracy, terminology consistency, regulatory compliance.

Translation:
""".strip()
        
        model_params = {
            "max_completion_tokens": 500,
            "temperature": 1.0  # O3 only supports temperature=1
        }
        
        return FormattedPrompt(
            prompt=combined_prompt,
            system_message=None,
            user_message=combined_prompt,
            messages=[{"role": "user", "content": combined_prompt}],
            model_specific_params=model_params,
            estimated_tokens=self._estimate_prompt_tokens(combined_prompt),
            format_type="single"
        )
    
    def _build_system_message(self, 
                            config: PromptFormatConfig, 
                            include_reasoning: bool = False) -> str:
        """Build comprehensive system message based on configuration"""
        
        system_parts = []
        
        # Base role definition
        if config.domain == "clinical_trial":
            system_parts.append(
                "You are a specialist medical translator with expertise in clinical trial "
                "documentation, regulatory requirements, and medical terminology consistency."
            )
        else:
            system_parts.append(
                "You are a professional translator specializing in accurate, "
                "contextually appropriate translations."
            )
        
        # Domain-specific instructions
        if config.domain == "clinical_trial":
            system_parts.append("Key Requirements:")
            for key, instruction in self.CLINICAL_TRIAL_INSTRUCTIONS.items():
                system_parts.append(f"- {instruction}")
        
        # Quality criteria
        if config.include_quality_criteria:
            system_parts.append("Quality Standards:")
            for criterion in self.QUALITY_CRITERIA:
                system_parts.append(f"- {criterion}")
        
        # Reasoning instructions for GPT-5
        if include_reasoning and config.include_reasoning_instructions:
            system_parts.append(
                "Reasoning Process: Analyze terminology, consider context, ensure consistency, "
                "apply domain knowledge, and verify accuracy before providing the final translation."
            )
        
        # Consistency enforcement
        if config.include_consistency_checks:
            system_parts.append(
                "Consistency Rule: Always use the locked terms and glossary translations provided "
                "in the context. These terms have been established for this document session."
            )
        
        return "\n\n".join(system_parts)
    
    def format_batch_translation_prompt(self,
                                      contexts_and_texts: List[Tuple[str, str]],
                                      target_language: str = "English",
                                      config: Optional[PromptFormatConfig] = None) -> FormattedPrompt:
        """
        Format prompt for batch translation of multiple segments
        
        Args:
            contexts_and_texts: List of (context, source_text) tuples
            target_language: Target language name
            config: Optional formatting configuration
            
        Returns:
            FormattedPrompt for batch processing
        """
        config = config or self.default_config
        
        # Build batch prompt
        system_message = self._build_system_message(config)
        
        # Format multiple translation tasks
        batch_tasks = []
        for i, (context, source_text) in enumerate(contexts_and_texts, 1):
            task = f"""
SEGMENT {i}:
Context: {context}
Source: {source_text}
""".strip()
            batch_tasks.append(task)
        
        user_message = f"""
Translate the following Korean clinical trial segments to {target_language}. 
Each segment has its own context with relevant glossary terms and consistency requirements.

{chr(10).join(batch_tasks)}

Provide translations in this format:
SEGMENT 1: [translation]
SEGMENT 2: [translation]
... and so on.

Requirements:
- Use context-specific terminology for each segment
- Maintain consistency within each segment's established terms
- Follow clinical trial documentation standards
""".strip()
        
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
        
        model_params = {
            "temperature": 0.2,
            "max_completion_tokens": 200 * len(contexts_and_texts)
        }
        
        return FormattedPrompt(
            prompt=user_message,
            system_message=system_message,
            user_message=user_message,
            messages=messages,
            model_specific_params=model_params,
            estimated_tokens=self._estimate_prompt_tokens(system_message + user_message),
            format_type="batch"
        )
    
    def extract_translation_from_response(self,
                                        response: str,
                                        response_format: str = "auto") -> Dict[str, Any]:
        """
        Extract translation from LLM response based on expected format
        
        Args:
            response: Raw LLM response
            response_format: Expected format ('json', 'text', 'auto')
            
        Returns:
            Dictionary with extracted translation and metadata
        """
        # Try to detect format automatically
        if response_format == "auto":
            if response.strip().startswith('{') and response.strip().endswith('}'):
                response_format = "json"
            else:
                response_format = "text"
        
        if response_format == "json":
            return self._extract_json_translation(response)
        else:
            return self._extract_text_translation(response)
    
    def _extract_json_translation(self, response: str) -> Dict[str, Any]:
        """Extract translation from JSON-formatted response"""
        try:
            # Try to parse as JSON
            parsed = json.loads(response.strip())
            
            return {
                "translation": parsed.get("translation", ""),
                "reasoning": parsed.get("reasoning", ""),
                "terminology_used": parsed.get("terminology_used", []),
                "confidence": parsed.get("confidence", 0.9),
                "format": "json",
                "raw_response": response
            }
            
        except json.JSONDecodeError:
            # Fallback to text extraction
            return self._extract_text_translation(response)
    
    def _extract_text_translation(self, response: str) -> Dict[str, Any]:
        """Extract translation from text-formatted response"""
        lines = response.strip().split('\n')
        
        # Look for translation after "Translation:" or similar patterns
        translation = ""
        for line in lines:
            line = line.strip()
            if line.startswith("Translation:"):
                translation = line[12:].strip()
                break
            elif line and not line.startswith(("Context:", "Source:", "Requirements:")):
                # Assume it's the translation if no explicit marker
                if not translation:
                    translation = line
        
        # If no clear translation found, use the entire response
        if not translation:
            translation = response.strip()
        
        return {
            "translation": translation,
            "reasoning": "",
            "terminology_used": [],
            "confidence": 0.85,
            "format": "text",
            "raw_response": response
        }
    
    def _estimate_prompt_tokens(self, text: str) -> int:
        """Estimate token count for prompt (simple approximation)"""
        # Simple estimation: 4 characters per token on average
        return len(text) // 4
    
    def _generate_cache_key(self,
                          context: str,
                          source_text: str,
                          config: PromptFormatConfig) -> str:
        """Generate cache key for prompt"""
        import hashlib
        
        key_components = [
            context,
            source_text,
            config.model_family,
            config.template.value,
            str(config.include_reasoning_instructions),
            config.domain
        ]
        
        key_string = "|".join(key_components)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def clear_cache(self) -> int:
        """Clear prompt cache and return number of entries cleared"""
        cache_size = len(self.prompt_cache)
        self.prompt_cache.clear()
        self.logger.info(f"Cleared prompt cache ({cache_size} entries)")
        return cache_size
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get prompt cache statistics"""
        return {
            "cache_entries": len(self.prompt_cache),
            "cache_enabled": self.enable_caching,
            "memory_estimate_mb": sum(
                len(prompt.prompt) for prompt in self.prompt_cache.values()
            ) / (1024 * 1024)
        }


# Utility functions for creating common prompt configurations

def create_gpt5_config(domain: str = "clinical_trial", 
                      include_reasoning: bool = True) -> PromptFormatConfig:
    """Create GPT-5 optimized configuration"""
    return PromptFormatConfig(
        model_family="gpt-5",
        template=PromptTemplate.GPT5_REASONING if include_reasoning else PromptTemplate.GPT5_STANDARD,
        include_reasoning_instructions=include_reasoning,
        include_consistency_checks=True,
        include_quality_criteria=True,
        domain=domain,
        output_format="json" if include_reasoning else "text"
    )


def create_gpt4_config(domain: str = "clinical_trial") -> PromptFormatConfig:
    """Create GPT-4o optimized configuration"""
    return PromptFormatConfig(
        model_family="gpt-4o",
        template=PromptTemplate.GPT4_OPTIMIZED,
        include_reasoning_instructions=False,
        include_consistency_checks=True,
        include_quality_criteria=True,
        domain=domain,
        output_format="text"
    )


def create_o3_config(domain: str = "clinical_trial") -> PromptFormatConfig:
    """Create O3 compatible configuration"""
    return PromptFormatConfig(
        model_family="o3",
        template=PromptTemplate.O3_COMPATIBLE,
        include_reasoning_instructions=False,
        include_consistency_checks=True,
        include_quality_criteria=False,  # Keep it simple for O3
        domain=domain,
        output_format="text"
    )


def create_model_specific_formatter(model_name: str, domain: str = "clinical_trial") -> PromptFormatter:
    """
    Create a prompt formatter configured for specific model
    
    Args:
        model_name: Model name (e.g., 'gpt-5', 'gpt-4o', 'o3')
        domain: Domain for specialized formatting
        
    Returns:
        Configured PromptFormatter
    """
    if model_name.startswith("gpt-5"):
        config = create_gpt5_config(domain)
    elif model_name in ["gpt-4o", "gpt-4.1"]:
        config = create_gpt4_config(domain)
    elif model_name == "o3":
        config = create_o3_config(domain)
    else:
        # Default to GPT-4 configuration
        config = create_gpt4_config(domain)
    
    return PromptFormatter(default_config=config)