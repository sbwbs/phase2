"""
Token Optimizer for Phase 2 MVP - Context Builder Component

This module provides accurate token counting and optimization for GPT models using
tiktoken, with dynamic context adjustment to stay under token limits while 
maintaining translation quality.

Key Features:
- Accurate GPT token counting with tiktoken
- Priority-based content inclusion/exclusion
- Dynamic context truncation strategies
- Memory-efficient token estimation
- Model-specific optimization (GPT-4o, GPT-5, o3)
"""

import tiktoken
import logging
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import re


class ContextPriority(Enum):
    """Priority levels for context components"""
    CRITICAL = 1      # Source text (always included)
    HIGH = 2          # Locked terms, key glossary terms
    MEDIUM = 3        # Previous context, additional glossary terms
    LOW = 4           # Extended context, meta information


@dataclass
class ContextComponent:
    """Represents a component of the context with metadata"""
    content: str
    priority: ContextPriority
    token_count: int
    component_type: str  # 'source', 'glossary', 'previous', 'locked', 'instructions'
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class TokenOptimizationResult:
    """Result of token optimization process"""
    optimized_context: str
    total_tokens: int
    components_included: List[ContextComponent]
    components_excluded: List[ContextComponent]
    optimization_strategy: str
    token_reduction_percent: float
    meets_target: bool


class TokenOptimizer:
    """Advanced token optimization engine for GPT models"""
    
    # Model-specific token limits (leaving buffer for response)
    MODEL_LIMITS = {
        'gpt-4o': 120000,      # 128k context, leave buffer
        'gpt-4.1': 32000,      # 32k context
        'o3': 120000,          # 128k context
        'gpt-5': 512000,       # 1M context (future)
        'gpt-5-mini': 128000,  # 256k context
        'gpt-5-nano': 64000,   # 128k context
        'default': 32000
    }
    
    def __init__(self, 
                 model_name: str = "gpt-4o",
                 target_token_limit: int = 500,
                 response_buffer: int = 200,
                 min_glossary_terms: int = 3,
                 enable_aggressive_optimization: bool = True):
        """
        Initialize token optimizer
        
        Args:
            model_name: GPT model name for token encoding
            target_token_limit: Target context token limit (default 500)
            response_buffer: Tokens reserved for response
            min_glossary_terms: Minimum glossary terms to include
            enable_aggressive_optimization: Enable aggressive truncation if needed
        """
        self.model_name = model_name
        self.target_limit = target_token_limit
        self.response_buffer = response_buffer
        self.min_glossary_terms = min_glossary_terms
        self.aggressive_optimization = enable_aggressive_optimization
        
        # Initialize tiktoken encoder
        try:
            self.encoding = tiktoken.encoding_for_model(self._get_tiktoken_model_name(model_name))
        except KeyError:
            # Fallback to cl100k_base for unknown models
            self.encoding = tiktoken.get_encoding("cl100k_base")
            logging.warning(f"Unknown model {model_name}, using cl100k_base encoding")
        
        self.logger = logging.getLogger(__name__)
        
        # Cache for token counts to avoid re-encoding
        self._token_cache: Dict[str, int] = {}
        
        self.logger.info(f"TokenOptimizer initialized for {model_name} "
                        f"with {target_token_limit} token target")
    
    def _get_tiktoken_model_name(self, model_name: str) -> str:
        """Map internal model names to tiktoken model names"""
        model_mapping = {
            'gpt-4o': 'gpt-4o',
            'gpt-4.1': 'gpt-4-turbo',
            'o3': 'gpt-4o',  # Use gpt-4o encoding for o3
            'gpt-5': 'gpt-4o',  # Future model, use gpt-4o encoding
            'gpt-5-mini': 'gpt-4o',
            'gpt-5-nano': 'gpt-4o'
        }
        return model_mapping.get(model_name, 'gpt-4o')
    
    def count_tokens(self, text: str, use_cache: bool = True) -> int:
        """
        Count tokens in text using tiktoken
        
        Args:
            text: Text to count tokens for
            use_cache: Whether to use cached results
            
        Returns:
            Number of tokens
        """
        if not text:
            return 0
        
        # Check cache first
        if use_cache and text in self._token_cache:
            return self._token_cache[text]
        
        try:
            token_count = len(self.encoding.encode(text))
            
            # Cache result if using cache
            if use_cache:
                self._token_cache[text] = token_count
            
            return token_count
            
        except Exception as e:
            self.logger.error(f"Token counting failed: {e}")
            # Fallback to simple estimation (4 chars per token average)
            return len(text) // 4
    
    def estimate_tokens_batch(self, texts: List[str]) -> List[int]:
        """
        Efficiently count tokens for multiple texts
        
        Args:
            texts: List of texts to count
            
        Returns:
            List of token counts
        """
        token_counts = []
        for text in texts:
            token_counts.append(self.count_tokens(text))
        return token_counts
    
    def create_context_component(self, 
                                content: str,
                                priority: ContextPriority,
                                component_type: str,
                                metadata: Optional[Dict[str, Any]] = None) -> ContextComponent:
        """
        Create a context component with token counting
        
        Args:
            content: Component content
            priority: Priority level
            component_type: Type of component
            metadata: Optional metadata
            
        Returns:
            ContextComponent object
        """
        token_count = self.count_tokens(content)
        
        return ContextComponent(
            content=content,
            priority=priority,
            token_count=token_count,
            component_type=component_type,
            metadata=metadata or {}
        )
    
    def optimize_context(self, 
                        components: List[ContextComponent],
                        target_limit: Optional[int] = None) -> TokenOptimizationResult:
        """
        Optimize context by selecting components that fit within token limit
        
        Args:
            components: List of context components
            target_limit: Override default target limit
            
        Returns:
            TokenOptimizationResult with optimization details
        """
        if target_limit is None:
            target_limit = self.target_limit
        
        # Calculate total tokens before optimization
        total_tokens_before = sum(comp.token_count for comp in components)
        
        # Sort components by priority (critical first)
        sorted_components = sorted(components, key=lambda x: (x.priority.value, -x.token_count))
        
        # Start with critical components (always include)
        included = []
        excluded = []
        current_tokens = 0
        
        # First pass: include all critical components
        for component in sorted_components:
            if component.priority == ContextPriority.CRITICAL:
                included.append(component)
                current_tokens += component.token_count
        
        # Second pass: add high priority components
        for component in sorted_components:
            if component.priority == ContextPriority.HIGH:
                if current_tokens + component.token_count <= target_limit:
                    included.append(component)
                    current_tokens += component.token_count
                else:
                    # Try to fit by truncating if aggressive optimization enabled
                    if self.aggressive_optimization:
                        available_tokens = target_limit - current_tokens
                        if available_tokens > 20:  # Minimum viable size
                            truncated_component = self._truncate_component(component, available_tokens)
                            if truncated_component:
                                included.append(truncated_component)
                                current_tokens += truncated_component.token_count
                            else:
                                excluded.append(component)
                        else:
                            excluded.append(component)
                    else:
                        excluded.append(component)
        
        # Third pass: add medium priority components if space allows
        for component in sorted_components:
            if component.priority == ContextPriority.MEDIUM:
                if current_tokens + component.token_count <= target_limit:
                    included.append(component)
                    current_tokens += component.token_count
                else:
                    excluded.append(component)
        
        # Fourth pass: add low priority components if space allows
        for component in sorted_components:
            if component.priority == ContextPriority.LOW:
                if current_tokens + component.token_count <= target_limit:
                    included.append(component)
                    current_tokens += component.token_count
                else:
                    excluded.append(component)
        
        # Build optimized context
        optimized_context = self._build_context_from_components(included)
        
        # Calculate metrics
        meets_target = current_tokens <= target_limit
        token_reduction = ((total_tokens_before - current_tokens) / total_tokens_before * 100 
                          if total_tokens_before > 0 else 0)
        
        # Determine optimization strategy used
        strategy = self._determine_optimization_strategy(included, excluded, meets_target)
        
        return TokenOptimizationResult(
            optimized_context=optimized_context,
            total_tokens=current_tokens,
            components_included=included,
            components_excluded=excluded,
            optimization_strategy=strategy,
            token_reduction_percent=token_reduction,
            meets_target=meets_target
        )
    
    def _truncate_component(self, 
                           component: ContextComponent, 
                           max_tokens: int) -> Optional[ContextComponent]:
        """
        Truncate a component to fit within token limit
        
        Args:
            component: Component to truncate
            max_tokens: Maximum tokens allowed
            
        Returns:
            Truncated component or None if not viable
        """
        if max_tokens < 10:  # Too small to be useful
            return None
        
        # For glossary terms, try to keep complete terms
        if component.component_type == 'glossary':
            return self._truncate_glossary_component(component, max_tokens)
        
        # For other components, use simple truncation
        return self._truncate_text_component(component, max_tokens)
    
    def _truncate_glossary_component(self, 
                                   component: ContextComponent, 
                                   max_tokens: int) -> Optional[ContextComponent]:
        """Truncate glossary component while preserving complete terms"""
        lines = component.content.split('\n')
        truncated_lines = []
        current_tokens = 0
        
        for line in lines:
            line_tokens = self.count_tokens(line + '\n')
            if current_tokens + line_tokens <= max_tokens:
                truncated_lines.append(line)
                current_tokens += line_tokens
            else:
                break
        
        if len(truncated_lines) >= self.min_glossary_terms:
            truncated_content = '\n'.join(truncated_lines)
            return ContextComponent(
                content=truncated_content,
                priority=component.priority,
                token_count=self.count_tokens(truncated_content),
                component_type=component.component_type,
                metadata={**component.metadata, 'truncated': True}
            )
        
        return None
    
    def _truncate_text_component(self, 
                                component: ContextComponent, 
                                max_tokens: int) -> Optional[ContextComponent]:
        """Truncate text component by sentences/words"""
        # Try to truncate by sentences first
        sentences = re.split(r'[.!?]+', component.content)
        truncated_sentences = []
        current_tokens = 0
        
        for sentence in sentences:
            if not sentence.strip():
                continue
                
            sentence_tokens = self.count_tokens(sentence + '. ')
            if current_tokens + sentence_tokens <= max_tokens:
                truncated_sentences.append(sentence.strip())
                current_tokens += sentence_tokens
            else:
                break
        
        if truncated_sentences:
            truncated_content = '. '.join(truncated_sentences) + '.'
            return ContextComponent(
                content=truncated_content,
                priority=component.priority,
                token_count=self.count_tokens(truncated_content),
                component_type=component.component_type,
                metadata={**component.metadata, 'truncated': True}
            )
        
        return None
    
    def _build_context_from_components(self, components: List[ContextComponent]) -> str:
        """Build final context string from selected components"""
        # Group components by type for better organization
        component_groups = {
            'source': [],
            'instructions': [],
            'locked': [],
            'glossary': [],
            'previous': [],
            'other': []
        }
        
        for comp in components:
            group = component_groups.get(comp.component_type, component_groups['other'])
            group.append(comp)
        
        # Build context in logical order
        context_parts = []
        
        # Add instructions first if present
        if component_groups['instructions']:
            for comp in component_groups['instructions']:
                context_parts.append(comp.content)
        
        # Add source text
        if component_groups['source']:
            for comp in component_groups['source']:
                context_parts.append(comp.content)
        
        # Add locked terms
        if component_groups['locked']:
            for comp in component_groups['locked']:
                context_parts.append(comp.content)
        
        # Add glossary terms
        if component_groups['glossary']:
            for comp in component_groups['glossary']:
                context_parts.append(comp.content)
        
        # Add previous context
        if component_groups['previous']:
            for comp in component_groups['previous']:
                context_parts.append(comp.content)
        
        # Add other components
        if component_groups['other']:
            for comp in component_groups['other']:
                context_parts.append(comp.content)
        
        return '\n\n'.join(context_parts)
    
    def _determine_optimization_strategy(self, 
                                       included: List[ContextComponent],
                                       excluded: List[ContextComponent],
                                       meets_target: bool) -> str:
        """Determine what optimization strategy was used"""
        if not excluded:
            return "no_optimization_needed"
        
        if not meets_target:
            return "aggressive_truncation_failed"
        
        excluded_types = [comp.component_type for comp in excluded]
        
        if 'glossary' in excluded_types:
            return "glossary_truncation"
        elif 'previous' in excluded_types:
            return "previous_context_removed"
        elif any(comp.metadata.get('truncated', False) for comp in included):
            return "component_truncation"
        else:
            return "priority_based_exclusion"
    
    def analyze_context_composition(self, 
                                  components: List[ContextComponent]) -> Dict[str, Any]:
        """
        Analyze context composition and provide optimization recommendations
        
        Args:
            components: List of context components
            
        Returns:
            Analysis results with recommendations
        """
        total_tokens = sum(comp.token_count for comp in components)
        
        # Group by priority and type
        priority_breakdown = {}
        type_breakdown = {}
        
        for comp in components:
            priority_name = comp.priority.name
            if priority_name not in priority_breakdown:
                priority_breakdown[priority_name] = {'count': 0, 'tokens': 0}
            priority_breakdown[priority_name]['count'] += 1
            priority_breakdown[priority_name]['tokens'] += comp.token_count
            
            if comp.component_type not in type_breakdown:
                type_breakdown[comp.component_type] = {'count': 0, 'tokens': 0}
            type_breakdown[comp.component_type]['count'] += 1
            type_breakdown[comp.component_type]['tokens'] += comp.token_count
        
        # Generate recommendations
        recommendations = []
        
        if total_tokens > self.target_limit:
            excess_tokens = total_tokens - self.target_limit
            recommendations.append(f"Context exceeds target by {excess_tokens} tokens")
            
            # Suggest specific optimizations
            if type_breakdown.get('glossary', {}).get('tokens', 0) > 200:
                recommendations.append("Consider reducing glossary terms or using more specific search")
            
            if type_breakdown.get('previous', {}).get('tokens', 0) > 100:
                recommendations.append("Previous context is large, consider truncating")
        
        return {
            'total_tokens': total_tokens,
            'target_limit': self.target_limit,
            'exceeds_limit': total_tokens > self.target_limit,
            'priority_breakdown': priority_breakdown,
            'type_breakdown': type_breakdown,
            'recommendations': recommendations
        }
    
    def clear_cache(self) -> int:
        """Clear token counting cache and return number of entries cleared"""
        cache_size = len(self._token_cache)
        self._token_cache.clear()
        self.logger.info(f"Cleared token cache ({cache_size} entries)")
        return cache_size
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get token cache statistics"""
        total_chars = sum(len(text) for text in self._token_cache.keys())
        return {
            'cache_entries': len(self._token_cache),
            'total_cached_characters': total_chars,
            'memory_estimate_mb': total_chars / (1024 * 1024)
        }


# Utility functions for common optimization patterns

def create_source_component(korean_text: str, segment_id: str = None) -> ContextComponent:
    """Create a source text component (always critical priority)"""
    optimizer = TokenOptimizer()
    return optimizer.create_context_component(
        content=f"Source text: {korean_text}",
        priority=ContextPriority.CRITICAL,
        component_type='source',
        metadata={'segment_id': segment_id}
    )


def create_glossary_component(glossary_terms: List[str], 
                            relevance_scores: List[float] = None) -> ContextComponent:
    """Create a glossary terms component"""
    optimizer = TokenOptimizer()
    
    # Format glossary terms
    if relevance_scores:
        term_lines = []
        for i, term in enumerate(glossary_terms):
            score = relevance_scores[i] if i < len(relevance_scores) else 0.0
            term_lines.append(f"- {term} (relevance: {score:.2f})")
        content = "Relevant glossary terms:\n" + "\n".join(term_lines)
    else:
        content = "Relevant glossary terms:\n" + "\n".join(f"- {term}" for term in glossary_terms)
    
    return optimizer.create_context_component(
        content=content,
        priority=ContextPriority.HIGH,
        component_type='glossary',
        metadata={'term_count': len(glossary_terms)}
    )


def create_locked_terms_component(locked_terms: Dict[str, str]) -> ContextComponent:
    """Create a locked terms component (high priority for consistency)"""
    optimizer = TokenOptimizer()
    
    if not locked_terms:
        return None
    
    term_lines = []
    for korean, english in locked_terms.items():
        term_lines.append(f"- {korean} → {english}")
    
    content = "Previously locked terms (use these translations consistently):\n" + "\n".join(term_lines)
    
    return optimizer.create_context_component(
        content=content,
        priority=ContextPriority.HIGH,
        component_type='locked',
        metadata={'locked_count': len(locked_terms)}
    )


def create_previous_context_component(previous_segments: List[Tuple[str, str]], 
                                    max_segments: int = 2) -> ContextComponent:
    """Create previous context component"""
    optimizer = TokenOptimizer()
    
    if not previous_segments:
        return None
    
    # Limit to most recent segments
    recent_segments = previous_segments[-max_segments:]
    
    context_lines = []
    for korean, english in recent_segments:
        context_lines.append(f"Korean: {korean}")
        context_lines.append(f"English: {english}")
        context_lines.append("")  # Empty line for separation
    
    content = "Previous translation context:\n" + "\n".join(context_lines)
    
    return optimizer.create_context_component(
        content=content,
        priority=ContextPriority.MEDIUM,
        component_type='previous',
        metadata={'segment_count': len(recent_segments)}
    )


def create_instructions_component(domain: str = "clinical_trial") -> ContextComponent:
    """Create translation instructions component"""
    optimizer = TokenOptimizer()
    
    if domain == "clinical_trial":
        content = ("Translate the Korean text to English for clinical trial documentation. "
                  "Maintain medical accuracy, use consistent terminology, and follow "
                  "regulatory translation standards.")
    else:
        content = ("Translate the Korean text to English accurately, "
                  "maintaining the original meaning and tone.")
    
    return optimizer.create_context_component(
        content=content,
        priority=ContextPriority.LOW,
        component_type='instructions',
        metadata={'domain': domain}
    )